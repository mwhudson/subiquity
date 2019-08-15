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

from urwid import Overlay, Text

from subiquitycore.ui.buttons import other_btn
from subiquitycore.ui.container import (
    Columns,
    Pile,
    WidgetWrap,
    )
from subiquitycore.ui.stretchy import Stretchy, StretchyOverlay
from subiquitycore.ui.utils import button_pile, disabled


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
        if 'closed' in getattr(self._w, 'signals', ()):
            self._w._emit('closed')
        # disabled() wraps a widget in two decorations.
        self._w = self._w.bottom_w.original_widget.original_widget

    def local_help(self):
        return ""

    def show_help(self, global_help):
        close_btn = other_btn("Close", on_press=lambda sender:self.remove_overlay())
        local_help = self.local_help().strip()
        if local_help:
            if isinstance(local_help, str):
                local_help = local_help.split('\n\n')
                local_help = Pile([Text(line.replace('\n', ' ')+"\n") for line in local_help])
            help_text = Pile([('pack', local_help), ('pack', global_help)])
        else:
            help_text = global_help
        self.show_stretchy_overlay(Stretchy(
            "Help",
            [help_text, Text(""), button_pile([close_btn])], 0, 2))

    def cancel(self):
        pass

    def keypress(self, size, key):
        key = super().keypress(size, key)
        if key == 'esc':
            if hasattr(self._w, 'bottom_w'):
                self.remove_overlay()
                return None
            else:
                self.cancel()
                return None
        return key
