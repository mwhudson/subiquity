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

""" View policy

Contains some default key navigations
"""

import logging
import os

from urwid import Overlay, Text

from subiquitycore.ui.container import (
    Columns,
    Pile,
    WidgetWrap,
    )
from subiquitycore.ui.stretchy import StretchyOverlay
from subiquitycore.ui.utils import disabled


log = logging.getLogger("subiquitycore.view")

class BaseView(WidgetWrap):

    footer = ""

    def show_overlay(self, overlay_widget, **kw):
        args = dict(
            align='center',
            width=('relative', 60),
            min_width=80,
            valign='middle',
            height='pack'
            )
        PADDING = 3
        # Don't expect callers to account for the padding if
        # they pass a fixed width.
        if 'width' in kw:
            if isinstance(kw['width'], int):
                kw['width'] += 2*PADDING
        args.update(kw)
        top = Pile([
            ('pack', Text("")),
            Columns([
                (PADDING, Text("")),
                overlay_widget,
                (PADDING, Text(""))
                ]),
            ('pack', Text("")),
            ])
        self._w = Overlay(top_w=top, bottom_w=disabled(self._w), **args)

    def show_stretchy_overlay(self, stretchy):
        self._w = StretchyOverlay(disabled(self._w), stretchy)

    def remove_overlay(self):
        # disabled() wraps a widget in two decorations.
        self._w = self._w.bottom_w.original_widget.original_widget

    def cancel(self):
        pass

    def keypress(self, size, key):
        if key in ['ctrl x']:
            self.controller.signal.emit_signal('control-x-quit')
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
            self.controller.loop.stop()
            print("Welcome to your debug shell")
            os.system("dash")
            self.controller.loop.start()
            self.controller.loop.screen.tty_signal_keys(stop="undefined")
            # Should re-scan block, network devices here somehow?
            return None
        return key
