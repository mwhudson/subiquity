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

import logging
import os
import platform
import shlex
import sys
import traceback

import urwid

import apport
import apport.hookutils
import apport.fileutils

from subiquitycore.core import Application

from subiquity.controllers.error import ErrorController
from subiquity.models.subiquity import SubiquityModel
from subiquity.snapd import (
    FakeSnapdConnection,
    SnapdConnection,
    )
from subiquity.ui.frame import SubiquityUI


log = logging.getLogger('subiquity.core')

DEBUG_SHELL_INTRO = _("""\
Installer shell session activated.

This shell session is running inside the installer environment.  You
will be returned to the installer when this shell is exited, for
example by typing Control-D or 'exit'.

Be aware that this is an ephemeral environment.  Changes to this
environment will not survive a reboot. If the install has started, the
installed system will be mounted at /target.""")


class Subiquity(Application):

    snapd_socket_path = '/run/snapd.socket'

    from subiquity.palette import COLORS, STYLES, STYLES_MONO

    project = "subiquity"
    showing_global_extra = False

    def make_model(self):
        root = '/'
        if self.opts.dry_run:
            root = os.path.abspath('.subiquity')
        return SubiquityModel(root, self.opts.sources)

    def make_ui(self):
        return SubiquityUI(self)

    controllers = [
            "Welcome",
            "Refresh",
            "Keyboard",
            "Zdev",
            "Network",
            "Proxy",
            "Mirror",
            "Refresh",
            "Filesystem",
            "Identity",
            "SSH",
            "SnapList",
            "InstallProgress",
    ]

    def __init__(self, opts, block_log_dir):
        self.controllers = self.controllers[:]
        if not opts.bootloader == 'none' and platform.machine() != 's390x':
            self.controllers.remove("Zdev")

        super().__init__(opts)
        self.ui.progress_completion += 1
        self.block_log_dir = block_log_dir
        if opts.snaps_from_examples:
            connection = FakeSnapdConnection(
                os.path.join(
                    os.path.dirname(
                        os.path.dirname(__file__)),
                    "examples", "snaps"))
        else:
            connection = SnapdConnection(self.root, self.snapd_socket_path)
        self.snapd_connection = connection
        self.signal.connect_signals([
            ('network-proxy-set', self._proxy_set),
            ('network-change', self._network_change),
            ])
        self._apport_data = []
        self._apport_files = []

    def run(self):
        try:
            super().run()
        except Exception:
            print("generating crash report")
            self.make_apport_report("Installer UI", sys.exc_info())
            raise

    def load_controllers(self):
        super().load_controllers()
        self.error_controller = ErrorController(self)

    def start_controllers(self):
        super().start_controllers()
        self.error_controller.start()

    def _network_change(self):
        self.signal.emit_signal('snapd-network-change')

    def _proxy_set(self):
        self.run_in_bg(
            lambda: self.snapd_connection.configure_proxy(
                self.base_model.proxy),
            lambda fut: (
                fut.result(), self.signal.emit_signal('snapd-network-change')),
            )

    def unhandled_input(self, key):
        if key == 'ctrl s':
            self.debug_shell()
        elif self.opts.dry_run and key == 'ctrl e':
            def _bg():
                try:
                    1/0
                except ZeroDivisionError:
                    self.make_apport_report("example", sys.exc_info())
            self.run_in_bg(_bg, lambda fut: None)
        elif key in ['ctrl h', 'f1']:
            self.show_global_extra()
        else:
            super().unhandled_input(key)

    def debug_shell(self):
        self.run_command_in_foreground(
            "clear && echo {} && bash".format(shlex.quote(DEBUG_SHELL_INTRO)),
            shell=True)

    def show_global_extra(self):
        if self.showing_global_extra:
            return
        self.showing_global_extra = True
        from subiquity.ui.views.global_extra import GlobalExtraStretchy

        fp = self.ui.pile.focus_position
        self.ui.pile.focus_position = 1
        self.ui.right_icon.base_widget._label._selectable = False

        def restore_focus():
            self.showing_global_extra = False
            self.ui.pile.focus_position = fp
            self.ui.right_icon.base_widget._label._selectable = True

        extra = GlobalExtraStretchy(self, self.ui.body)

        urwid.connect_signal(extra, 'closed', restore_focus)

        self.ui.body.show_stretchy_overlay(extra)

    def note_file_for_apport(self, key, path):
        self._apport_files.append((key, path))

    def note_data_for_apport(self, key, value):
        self._apport_data.append((key, value))

    def make_apport_report(self, thing, exc_info=None, extra_data=None):
        log.debug("generating crash report")
        i = 0
        crash_dir = os.path.join(self.base_model.root, 'var/crash')
        os.makedirs(crash_dir, exist_ok=True)
        while 1:
            try:
                crash_path = os.path.join(crash_dir, "installer.{}.crash".format(i))
                f = open(crash_path, 'xb')
            except FileExistsError:
                i += 1
                continue
            else:
                break
        with f:
            pr = apport.Report('Bug')

            # Add basic info to report.
            pr.add_proc_info()
            pr.add_os_info()
            pr.add_hooks_info(None)
            apport.hookutils.attach_hardware(pr)

            if exc_info is not None:
                pr['Title'] = "{} crashed with {}".format(thing, exc_info[0].__name__)
                pr['Traceback'] = "".join(traceback.format_exception(*exc_info))
            else:
                pr['Title'] = thing

            pr['Path'] = crash_path

            # Attach any stuff other parts of the code think we should know about.
            for key, path in self._apport_files:
                apport.hookutils.attach_file_if_exists(pr, path, key)
            for key, value in self._apport_data:
                pr[key] = value
            if extra_data:
                for key, value in extra_data.items():
                    pr[key] = value

            # Because apport-cli will in general be run on a different
            # machine, we make some slightly obscure alterations to the
            # report to make this go better.

            # If ExecutableTimestamp is present, apport-cli will try to check that
            # ExecutablePath hasn't changed. But it won't be there.
            del pr['ExecutableTimestamp']
            # apport-cli gets upset at the probert C extensions it sees in here.
            # /proc/maps is very unlikely to be interesting for us anyway.
            del pr['ProcMaps']

            # apport-cli gets upset if neither of these are present.
            pr['Package'] = 'subiquity'
            pr['SourcePackage'] = 'subiquity'

            # Report to the subiquity project on Launchpad.
            crashdb = {
                'impl': 'launchpad',
                'project': 'subiquity',
                }
            if self.opts.dry_run:
                crashdb['launchpad_instance'] = 'staging'
            pr['CrashDB'] = repr(crashdb)

            pr.write(f)
        return crash_path
