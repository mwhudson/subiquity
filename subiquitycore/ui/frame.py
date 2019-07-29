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

""" Base Frame Widget """

import logging
import os

from urwid import (
    Text,
    )
from subiquitycore.ui.anchors import Header, Footer
from subiquitycore.ui.container import (
    ListBox,
    Pile,
    WidgetWrap,
    )
from subiquitycore.ui.utils import Color


log = logging.getLogger('subiquitycore.ui.frame')


class SubiquityUI(WidgetWrap):

    def __init__(self):
        self.header = Header("")
        self.footer = Footer("", 0, 1)
        self.frame = Pile([
            ('pack', self.header),
            ListBox([Text("")]),
            ('pack', self.footer),
            ])
        self.progress_current = 0
        self.progress_completion = 0
        # After the install starts, we want to stop setting the footer
        # from the body view.
        self.auto_footer = True
        super().__init__(Color.body(self.frame))


    def keypress(self, size, key):
        if key in ['ctrl x']:
            self.signal.emit_signal('control-x-quit')
            return None
        key = super().keypress(size, key)
        if key == 'esc':
            if hasattr(self._w, 'bottom_w'):
                self.remove_overlay()
                return None
            else:
                self.cancel()
                return None
        if key in ['ctrl s']:
            self.loop.stop()
            print("Welcome to your debug shell")
            os.system("dash")
            self.loop.start()
            self.loop.screen.tty_signal_keys(stop="undefined")
            # Should re-scan block, network devices here somehow?
            return None
        return key

    def set_header(self, title=None):
        self.frame.contents[0] = (
            Header(title),
            self.frame.options('pack'))

    def set_footer(self, message):
        self.frame.contents[2] = (
            Footer(message, self.progress_current, self.progress_completion),
            self.frame.options('pack'))

    def set_body(self, widget):
        self.set_header(_(widget.title))
        self.frame.contents[1] = (
            widget,
            self.frame.options())
        if self.auto_footer:
            self.set_footer(_(widget.footer))
