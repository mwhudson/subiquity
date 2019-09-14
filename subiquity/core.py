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

import apport.hookutils

import urwid

from subiquitycore.core import Application
from subiquitycore.ui.stretchy import StretchyOverlay

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

    def make_apport_report(self, thing, exc_info=None, extra_data=None,
                               *, interrupt=True):
        log.debug("generating crash report")
        apport_files = self._apport_files[:]
        apport_data = self._apport_data.copy()
        if extra_data is not None:
            extra_data = extra_data.copy()

        def _bg_attach_hook():
            # Attach any stuff other parts of the code think we should know
            # about.
            for key, path in apport_files:
                apport.hookutils.attach_file_if_exists(report.pr, path, key)
            for key, value in apport_data:
                report.pr[key] = value
            if extra_data:
                for key, value in extra_data.items():
                    report.pr[key] = value

        report = self.error_controller.create_report(_bg_attach_hook)

        if exc_info is not None:
            report.pr["Title"] = "{} crashed with {}".format(
                thing, exc_info[0].__name__)
            report.pr['Traceback'] = "".join(
                traceback.format_exception(*exc_info))
        else:
            report.pr["Title"] = thing
        report.add_info()
        if interrupt:
            error_list = None
            w = self.ui.body._w
            from subiquity.ui.views.error import (
                ErrorReportListStretchy,
                )
            while isinstance(w, StretchyOverlay):
                if isinstance(w.stretchy, ErrorReportListStretchy):
                    error_list = w.stretchy
                    break
                w = w.bottom_w.original_widget.original_widget
            if error_list is None:
                error_list = ErrorReportListStretchy(self, self.ui.body)
                self.ui.body.show_stretchy_overlay(error_list)
            error_list.focus_report(report)
            error_list.open_report(None, report)
