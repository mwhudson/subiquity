# Copyright 2015 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from concurrent import futures
import fcntl
from functools import partial
import json
import logging
import os
import struct
import subprocess
import sys
import tty

import urwid
import yaml

from subiquitycore.controller import RepeatedController
from subiquitycore.signals import Signal
from subiquitycore.prober import Prober
from subiquitycore.ui.frame import SubiquityCoreUI

from subiquity.async_helpers import schedule_task

log = logging.getLogger('subiquitycore.core')


class Skip(Exception):
    """Raise this from a controller's default method to skip a screen."""


# From uapi/linux/kd.h:
KDGKBTYPE = 0x4B33  # get keyboard type

GIO_CMAP = 0x4B70  # gets colour palette on VGA+
PIO_CMAP = 0x4B71  # sets colour palette on VGA+
UO_R, UO_G, UO_B = 0xe9, 0x54, 0x20

# /usr/include/linux/kd.h
K_RAW = 0x00
K_XLATE = 0x01
K_MEDIUMRAW = 0x02
K_UNICODE = 0x03
K_OFF = 0x04

KDGKBMODE = 0x4B44  # gets current keyboard mode
KDSKBMODE = 0x4B45  # sets current keyboard mode


class TwentyFourBitScreen(urwid.raw_display.Screen):

    def __init__(self, _urwid_name_to_rgb):
        self._urwid_name_to_rgb = _urwid_name_to_rgb
        super().__init__()

    def _cc(self, color):
        """Return the "SGR" parameter for selecting color.

        See https://en.wikipedia.org/wiki/ANSI_escape_code#SGR for an
        explanation.  We use the basic codes for black/white/default for
        maximum compatibility; they are the only colors used when the
        mono palette is selected.
        """
        if color == 'white':
            return '7'
        elif color == 'black':
            return '0'
        elif color == 'default':
            return '9'
        else:
            # This is almost but not quite a ISO 8613-3 code -- that
            # would use colons to separate the rgb values instead. But
            # it's what xterm, and hence everything else, supports.
            return '8;2;{};{};{}'.format(*self._urwid_name_to_rgb[color])

    def _attrspec_to_escape(self, a):
        return '\x1b[0;3{};4{}m'.format(
            self._cc(a.foreground),
            self._cc(a.background))


def is_linux_tty():
    try:
        r = fcntl.ioctl(sys.stdout.fileno(), KDGKBTYPE, ' ')
    except IOError as e:
        log.debug("KDGKBTYPE failed %r", e)
        return False
    log.debug("KDGKBTYPE returned %r, is_linux_tty %s", r, r == b'\x02')
    return r == b'\x02'


urwid_8_names = (
    'black',
    'dark red',
    'dark green',
    'brown',
    'dark blue',
    'dark magenta',
    'dark cyan',
    'light gray',
)


def make_palette(colors, styles, ascii):
    """Return a palette to be passed to MainLoop.

    colors is a list of exactly 8 tuples (name, (r, g, b))

    styles is a list of tuples (stylename, fg_color, bg_color) where
    fg_color and bg_color are defined in 'colors'
    """
    # The part that makes this "fun" is that urwid insists on referring
    # to the basic colors by their "standard" names but we overwrite
    # these colors to mean different things.  So we convert styles into
    # an urwid palette by mapping the names in colors to the standard
    # name.
    if len(colors) != 8:
        raise Exception(
            "make_palette must be passed a list of exactly 8 colors")
    urwid_name = dict(zip([c[0] for c in colors], urwid_8_names))

    urwid_palette = []
    for name, fg, bg in styles:
        urwid_fg, urwid_bg = urwid_name[fg], urwid_name[bg]
        if ascii:
            # 24bit grey on colored background looks good
            # but in 16 colors it's unreadable
            # hence add more contrast
            if urwid_bg != 'black':
                urwid_fg = 'black'
            # Only frame_button doesn't match above rule
            # fix it to be brown-on-black black-on-brown
            if name == 'frame_button focus':
                urwid_fg, urwid_bg = 'brown', 'black'
        urwid_palette.append((name, urwid_fg, urwid_bg))

    return urwid_palette


def extend_dec_special_charmap():
    urwid.escape.DEC_SPECIAL_CHARMAP.update({
        ord('\N{BLACK RIGHT-POINTING SMALL TRIANGLE}'): '>',
        ord('\N{BLACK LEFT-POINTING SMALL TRIANGLE}'): '<',
        ord('\N{BLACK DOWN-POINTING SMALL TRIANGLE}'): 'v',
        ord('\N{BLACK UP-POINTING SMALL TRIANGLE}'): '^',
        ord('\N{check mark}'): '+',
        ord('\N{bullet}'): '*',
        ord('\N{lower half block}'): '=',
        ord('\N{upper half block}'): '=',
        ord('\N{FULL BLOCK}'): urwid.escape.DEC_SPECIAL_CHARMAP[
            ord('\N{BOX DRAWINGS LIGHT VERTICAL}')],
    })


class KeyCodesFilter:
    """input_filter that can pass (medium) raw keycodes to the application

    See http://lct.sourceforge.net/lct/x60.html for terminology.

    Call enter_keycodes_mode()/exit_keycodes_mode() to switch into and
    out of keycodes mode. In keycodes mode, the only events passed to
    the application are "press $N" / "release $N" where $N is the
    keycode the user pressed or released.

    Much of this is cribbed from the source of the "showkeys" utility.
    """

    def __init__(self, app):
        self.app = app
        self.filtering = False

    def enter_keycodes_mode(self):
        fd = self.app.loop.screen._term_input_file.fileno()
        log.debug("enter_keycodes_mode")
        self.filtering = True
        # Read the old keyboard mode (it will proably always be K_UNICODE but
        # well).
        o = bytearray(4)
        fcntl.ioctl(fd, KDGKBMODE, o)
        self._old_mode = struct.unpack('i', o)[0]
        # Set the keyboard mode to K_MEDIUMRAW, which causes the keyboard
        # driver in the kernel to pass us keycodes.
        fcntl.ioctl(fd, KDSKBMODE, K_MEDIUMRAW)

    def exit_keycodes_mode(self):
        fd = self.app.loop.screen._term_input_file.fileno()
        log.debug("exit_keycodes_mode")
        self.filtering = False
        fcntl.ioctl(fd, KDSKBMODE, self._old_mode)

    def filter(self, keys, codes):
        # Luckily urwid passes us the raw results from read() we can
        # turn into keycodes.
        if self.filtering:
            i = 0
            r = []
            n = len(codes)
            while i < len(codes):
                # This is straight from showkeys.c.
                if codes[i] & 0x80:
                    p = 'release '
                else:
                    p = 'press '
                if i + 2 < n and (codes[i] & 0x7f) == 0:
                    if (codes[i + 1] & 0x80) != 0:
                        if (codes[i + 2] & 0x80) != 0:
                            kc = (((codes[i + 1] & 0x7f) << 7) |
                                  (codes[i + 2] & 0x7f))
                            i += 3
                else:
                    kc = codes[i] & 0x7f
                    i += 1
                r.append(p + str(kc))
            return r
        else:
            return keys


class DummyKeycodesFilter:
    # A dummy implementation of the same interface as KeyCodesFilter
    # we can use when not running in a linux tty.

    def enter_keycodes_mode(self):
        pass

    def exit_keycodes_mode(self):
        pass

    def filter(self, keys, codes):
        return keys


class ControllerSet:

    def __init__(self, app, names):
        self.app = app
        self.controller_names = names
        self.index = -1
        self.instances = []

    def load(self):
        controllers_mod = __import__(
            '{}.controllers'.format(self.app.project), None, None, [''])
        for name in self.controller_names:
            log.debug("Importing controller: %s", name)
            klass = getattr(controllers_mod, name+"Controller")
            if hasattr(self, name):
                c = 0
                for instance in self.instances:
                    if isinstance(instance, klass):
                        c += 1
                inst = RepeatedController(getattr(self, name), c)
                name = inst.name
            else:
                inst = klass(self.app)
                if inst.autoinstall_key in self.app.autoinstall_config:
                    inst.load_autoinstall()
            setattr(self, name, inst)
            self.instances.append(inst)

    @property
    def cur(self):
        if self.index >= 0:
            inst = self.instances[self.index]
            while isinstance(inst, RepeatedController):
                inst = inst.orig
            return inst
        else:
            return None

    @property
    def at_end(self):
        return self.index == len(self.instances) - 1

    @property
    def out_of_bounds(self):
        return self.index < 0 or self.index >= len(self.instances)

    @property
    def at_start(self):
        return self.index == 0

    def advance(self):
        self.index += 1
        return self.cur

    def back_up(self):
        self.index -= 1
        return self.cur


class Application:

    # A concrete subclass must set project and controllers attributes, e.g.:
    #
    # project = "subiquity"
    # controllers = [
    #         "Welcome",
    #         "Network",
    #         "Filesystem",
    #         "Identity",
    #         "InstallProgress",
    # ]
    # The 'next-screen' and 'prev-screen' signals move through the list of
    # controllers in order, calling the start_ui method on the controller
    # instance.

    make_ui = SubiquityCoreUI

    def __init__(self, opts):
        prober = Prober(opts)

        self.ui = self.make_ui()
        self.opts = opts
        opts.project = self.project

        self.root = '/'
        if opts.dry_run:
            self.root = '.subiquity'
        self.state_dir = os.path.join(self.root, 'run', self.project)
        os.makedirs(os.path.join(self.state_dir, 'states'), exist_ok=True)

        self.answers = {}
        if opts.answers is not None:
            self.answers = yaml.safe_load(opts.answers.read())
            log.debug("Loaded answers %s", self.answers)
            if not opts.dry_run:
                open('/run/casper-no-prompt', 'w').close()

        self.is_color = False
        self.color_palette = make_palette(self.COLORS, self.STYLES, opts.ascii)

        self.is_linux_tty = is_linux_tty()

        if self.is_linux_tty:
            self.input_filter = KeyCodesFilter(self)
        else:
            self.input_filter = DummyKeycodesFilter()

        self.scale_factor = float(
            os.environ.get('SUBIQUITY_REPLAY_TIMESCALE', "1"))
        self.updated = os.path.exists(os.path.join(self.state_dir, 'updating'))
        self.signal = Signal()
        self.prober = prober
        self.loop = None
        self.pool = futures.ThreadPoolExecutor(10)
        self.controllers = ControllerSet(self, self.controllers)

    def run_in_bg(self, func, callback):
        """Run func() in a thread and call callback on UI thread.

        callback will be passed a concurrent.futures.Future containing
        the result of func(). The result of callback is discarded. An
        exception will crash the process so be careful!
        """
        fut = self.pool.submit(func)

        def in_main_thread(ignored):
            self.loop.remove_watch_pipe(pipe)
            os.close(pipe)
            callback(fut)

        pipe = self.loop.watch_pipe(in_main_thread)

        def in_random_thread(ignored):
            os.write(pipe, b'x')
        fut.add_done_callback(in_random_thread)

    def run_command_in_foreground(self, cmd, before_hook=None, after_hook=None,
                                  **kw):
        screen = self.loop.screen

        # Calling screen.stop() sends the INPUT_DESCRIPTORS_CHANGED
        # signal. This calls _reset_input_descriptors() which calls
        # unhook_event_loop / hook_event_loop on the screen. But this all
        # happens before _started is set to False on the screen and so this
        # does not actually do anything -- we end up attempting to read from
        # stdin while in a background process group, something that gets the
        # kernel upset at us.
        #
        # The cleanest fix seems to be to just send the signal again once
        # stop() has returned which, now that screen._started is False,
        # correctly stops listening from stdin.
        #
        # There is an exactly analagous problem with screen.start() except
        # there the symptom is that we are running in the foreground but not
        # listening to stdin! The fix is the same.

        def run():
            subprocess.run(cmd, **kw)

        def restore(fut):
            screen.start()
            urwid.emit_signal(
                screen, urwid.display_common.INPUT_DESCRIPTORS_CHANGED)
            tty.setraw(0)
            if after_hook is not None:
                after_hook()

        screen.stop()
        urwid.emit_signal(
            screen, urwid.display_common.INPUT_DESCRIPTORS_CHANGED)
        if before_hook is not None:
            before_hook()
        self.run_in_bg(run, restore)

    def _connect_base_signals(self):
        """Connect signals used in the core controller."""
        signals = [
            ('quit', self.exit),
            ('next-screen', self.next_screen),
            ('prev-screen', self.prev_screen),
            ]
        if self.opts.dry_run:
            signals.append(('control-x-quit', self.exit))
        self.signal.connect_signals(signals)

        # Registers signals from each controller
        for controller in self.controllers.instances:
            controller.register_signals()
        log.debug("known signals: %s", self.signal.known_signals)

    def save_state(self):
        cur = self.controllers.cur
        if cur is None:
            return
        state_path = os.path.join(
            self.state_dir, 'states', cur.name)
        with open(state_path, 'w') as fp:
            json.dump(cur.serialize(), fp)

    def start_screen(self, old, new):
        if old is not None:
            old.end_ui()
        log.debug("moving to screen %s", new.name)
        if self.opts.screens and new.name not in self.opts.screens:
            raise Skip
        new.start_ui()
        state_path = os.path.join(self.state_dir, 'last-screen')
        with open(state_path, 'w') as fp:
            fp.write(new.name)

    def _move_screen(self, increment):
        self.save_state()
        old = self.controllers.cur
        if old is not None and old.interactive():
            old.end_ui()
        while True:
            self.controllers.index += increment
            if self.controllers.out_of_bounds:
                self.exit()
            new = self.controllers.cur
            if new.interactive():
                try:
                    new.start_ui()
                except Skip:
                    log.debug("skipping screen %s", new.name)
                    continue
                else:
                    state_path = os.path.join(self.state_dir, 'last-screen')
                    with open(state_path, 'w') as fp:
                        fp.write(new.name)
                    return
            else:
                print("applying config for new", new)
                coro = new.apply_autoinstall_config()
                if coro is not None:
                    task = schedule_task(coro)
                    task.add_done_callback(lambda fut: self._move_screen(increment))
                    return

    def next_screen(self, *args):
        self._move_screen(1)

    def prev_screen(self, *args):
        self._move_screen(-1)

# EventLoop -------------------------------------------------------------------

    def exit(self):
        raise urwid.ExitMainLoop()

    def run_scripts(self, scripts):
        # run_scripts runs (or rather arranges to run, it's all async)
        # a series of python snippets in a helpful namespace. This is
        # all in aid of being able to test some part of the UI without
        # having to click the same buttons over and over again to get
        # the UI to the part you are working on.
        #
        # In the namespace are:
        #  * everything from view_helpers
        #  * wait, delay execution of subsequent scripts for a while
        #  * c, a function that finds a button and clicks it. uses
        #    wait, above to wait for the button to appear in case it
        #    takes a while.
        from subiquitycore.testing import view_helpers

        class ScriptState:
            def __init__(self):
                self.ns = view_helpers.__dict__.copy()
                self.waiting = False
                self.wait_count = 0
                self.scripts = scripts

        ss = ScriptState()

        def _run_script(*args):
            log.debug("running %s", ss.scripts[0])
            exec(ss.scripts[0], ss.ns)
            if ss.waiting:
                return
            ss.scripts = ss.scripts[1:]
            if ss.scripts:
                self.loop.set_alarm_in(0.01, _run_script)

        def c(pat):
            but = view_helpers.find_button_matching(self.ui, '.*' + pat + '.*')
            if not but:
                ss.wait_count += 1
                if ss.wait_count > 10:
                    raise Exception("no button found matching %r after"
                                    "waiting for 10 secs" % pat)
                wait(1, func=lambda: c(pat))
                return
            ss.wait_count = 0
            view_helpers.click(but)

        def wait(delay, func=None):
            ss.waiting = True

            def next(loop, user_data):
                ss.waiting = False
                if func is not None:
                    func()
                if not ss.waiting:
                    ss.scripts = ss.scripts[1:]
                    if ss.scripts:
                        _run_script()
            self.loop.set_alarm_in(delay, next)

        ss.ns['c'] = c
        ss.ns['wait'] = wait
        ss.ns['ui'] = self.ui

        self.loop.set_alarm_in(0.06, _run_script)

    def toggle_color(self):
        if self.is_color:
            new_palette = self.STYLES_MONO
            self.is_color = False
        else:
            new_palette = self.color_palette
            self.is_color = True
        self.loop.screen.register_palette(new_palette)
        self.loop.screen.clear()

    def unhandled_input(self, key):
        if key == 'ctrl x':
            self.signal.emit_signal('control-x-quit')
        elif key == 'f3':
            self.loop.screen.clear()
        elif key in ['ctrl t', 'f4']:
            self.toggle_color()

    def start_controllers(self):
        log.debug("starting controllers")
        for controller in self.controllers.instances:
            controller.start()
        log.debug("controllers started")

    def load_serialized_state(self):
        for controller in self.controllers.instances:
            state_path = os.path.join(
                self.state_dir, 'states', controller.name)
            if not os.path.exists(state_path):
                continue
            with open(state_path) as fp:
                controller.deserialize(json.load(fp))

        last_screen = None
        state_path = os.path.join(self.state_dir, 'last-screen')
        if os.path.exists(state_path):
            with open(state_path) as fp:
                last_screen = fp.read().strip()
        controller_index = 0
        for i, controller in enumerate(self.controllers.instances):
            if controller.name == last_screen:
                controller_index = i
        return controller_index

    def select_initial_screen(self, controller_index):
        self.controllers.index = controller_index - 1
        self.next_screen()

    def make_screen(self):
        """Return a screen to be passed to MainLoop.

        colors is a list of exactly 8 tuples (name, (r, g, b)), the same as
        passed to make_palette.
        """
        # On the linux console, we overwrite the first 8 colors to be those
        # defined by colors. Otherwise, we return a screen that uses ISO
        # 8613-3ish codes to display the colors.
        if len(self.COLORS) != 8:
            raise Exception(
                "make_screen must be passed a list of exactly 8 colors")
        if self.is_linux_tty:
            # Perhaps we ought to return a screen subclass that does this
            # ioctl-ing in .start() and undoes it in .stop() but well.
            curpal = bytearray(16*3)
            fcntl.ioctl(sys.stdout.fileno(), GIO_CMAP, curpal)
            for i in range(8):
                for j in range(3):
                    curpal[i*3+j] = self.COLORS[i][1][j]
            fcntl.ioctl(sys.stdout.fileno(), PIO_CMAP, curpal)
            return urwid.raw_display.Screen()
        elif self.opts.ascii:
            return urwid.raw_display.Screen()
        else:
            _urwid_name_to_rgb = {}
            for i, n in enumerate(urwid_8_names):
                _urwid_name_to_rgb[n] = self.COLORS[i][1]
            return TwentyFourBitScreen(_urwid_name_to_rgb)

    def run(self):
        log.debug("Application.run")

        self.loop = urwid.MainLoop(
            self.ui, palette=self.color_palette, screen=self.make_screen(),
            handle_mouse=False, pop_ups=True,
            input_filter=self.input_filter.filter,
            unhandled_input=self.unhandled_input,
            event_loop=urwid.AsyncioEventLoop())

        if self.opts.ascii:
            urwid.util.set_encoding('ascii')

        extend_dec_special_charmap()

        self.toggle_color()

        self.base_model = self.make_model()
        try:
            if self.opts.scripts:
                self.run_scripts(self.opts.scripts)

            self.controllers.load()

            initial_controller_index = 0

            if self.updated:
                initial_controller_index = self.load_serialized_state()


            def setraw(loop, ud):
                fd = self.loop.screen._term_input_file.fileno()
                if os.isatty(fd):
                    tty.setraw(fd)

            self.loop.set_alarm_in(0.00, setraw)
            self.loop.set_alarm_in(
                0.05, lambda loop, ud: self.select_initial_screen(
                    initial_controller_index))
            self._connect_base_signals()

            self.start_controllers()

            self.loop.run()
        except Exception:
            log.exception("Exception in controller.run():")
            raise
        finally:
            # concurrent.futures.ThreadPoolExecutor tries to join all
            # threads before exiting. We don't want that and this
            # ghastly hack prevents it.
            from concurrent.futures import thread
            thread._threads_queues = {}
