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
import tty


import urwid

from subiquitycore.core import Application

from subiquity.models.subiquity import SubiquityModel
from subiquity.snapd import (
    FakeSnapdConnection,
    SnapdConnection,
    )
from subiquity.ui.frame import SubiquityUI


log = logging.getLogger('subiquity.core')


class Subiquity(Application):

    snapd_socket_path = '/run/snapd.socket'

    from subiquity.palette import COLORS, STYLES, STYLES_MONO

    project = "subiquity"
    showing_help = False
    
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
        elif key in ['ctrl h', 'f1']:
            if not self.showing_help:
                self.show_help()
        else:
            super().unhandled_input(key)

    def debug_shell(self):
        self.run_command_in_foreground(
            "clear && echo 'Welcome to your debug shell' && bash", shell=True)

    def show_help(self):
        self.showing_help = True
        self.ui.body.show_help(self.ui.global_help())
        fp = self.ui.frame.focus_position
        self.ui.frame.focus_position = 1
        attr_map = self.ui.right_icon.attr_map
        self.ui.right_icon.attr_map = self.ui.right_icon.focus_map
        self.ui.right_icon.base_widget._label._selectable = False

        def restore_focus(sender):
            self.showing_help = False
            self.ui.frame.focus_position = fp
            self.ui.right_icon.base_widget._label._selectable = True
            self.ui.right_icon.attr_map = attr_map
        urwid.connect_signal(self.ui.body._w, 'closed', restore_focus)
