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


from urwid import (
    Text,
    ProgressBar,
    )

from subiquitycore.ui.container import (
    Columns,
    Pile,
    WidgetWrap,
    )
from subiquitycore.ui.utils import Padding, Color
from subiquitycore.ui.width import widget_width

log = logging.getLogger('subiquitycore.ui.anchors')


class Header(WidgetWrap):
    """ Header Widget

    This widget uses the style key `frame_header`

    :param str title: Title of Header
    :returns: Header()
    """

    def __init__(self, title):
        if isinstance(title, str):
            title = Text(title)
        title = Padding.center_79(title, min_width=76)
        super().__init__(Color.frame_header(
                Pile(
                    [Text(""), title, Text("")])))


class StepsProgressBar(ProgressBar):

    def get_text(self):
        return "{} / {}".format(self.current, self.done)


class MyColumns(Columns):
    def column_widths(self, size, focus=False):
        maxcol = size[0]
        center = 79*maxcol//100
        if center < 76:
            center = 76
        left = (maxcol - center)//2
        right = widget_width(self.contents[2][0])
        middle = maxcol - left - right
        return [left, middle, right]


class Footer(WidgetWrap):
    """ Footer widget

    Style key: `frame_footer`

    """

    def __init__(self, ui, message, current, complete):
        self.ui = ui
        if isinstance(message, str):
            message = Text(message)
        message = Padding.center_99(message, min_width=76)
        progress_bar = Padding.center_60(
            StepsProgressBar(normal='progress_incomplete',
                             complete='progress_complete',
                             current=current, done=complete))
        status = [
            progress_bar,
            Padding.line_break(""),
            MyColumns([Text(""), message, self.ui.helpbtn]),
        ]
        super().__init__(Color.frame_footer(Pile(status)))
