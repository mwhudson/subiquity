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

""" UI utilities """

from functools import partialmethod
import logging

from subiquitycore.ui.container import ListBox, Pile

from urwid import (
    AttrMap,
    Button,
    Padding as _Padding,
    Text,
    WidgetDecoration,
    WidgetDisable,
    delegate_to_widget_mixin,
    )


log = logging.getLogger("subiquitycore.ui.utils")


def apply_padders(cls):
    """ Decorator for generating useful padding methods

    Loops through and generates methods like:

      Padding.push_1(Widget)

      Sets the left padding attribute by 1

      Padding.pull_24(Widget)

      Sets right padding attribute by 24.

      Padding.center_50(Widget)

      Provides center padding with a relative width of 50
    """
    padding_count = 100

    for i in range(1, padding_count):
        setattr(cls, 'push_{}'.format(i), partialmethod(_Padding, left=i))
        setattr(cls, 'pull_{}'.format(i), partialmethod(_Padding, right=i))
        setattr(cls, 'fixed_{}'.format(i),
                partialmethod(_Padding, align='center',
                              width=i, min_width=i))
        setattr(cls, 'center_{}'.format(i),
                partialmethod(_Padding, align='center',
                              width=('relative', i)))
        setattr(cls, 'left_{}'.format(i),
                partialmethod(_Padding, align='left',
                              width=('relative', i)))
        setattr(cls, 'right_{}'.format(i),
                partialmethod(_Padding, align='right',
                              width=('relative', i)))
    return cls


@apply_padders
class Padding:
    """ Padding methods

    .. py:meth:: push_X(:class:`urwid.Widget`)

       This method supports padding the left side of the widget
       from 1-99, for example:

       .. code::

          Padding.push_20(Text("This will be indented 20 columns")

    .. py:meth:: pull_X(:class:`urwid.Widget`)

       This method supports padding the right side of the widget
       from 1-99, for example:

       .. code::

          Padding.pull_20(Text("This will be right indented 20 columns")

    .. py:meth:: fixed_X(:class:`urwid.Widget`)

       This method supports padding the widget to a fixed size and
       centering it.
       from 1-99, for example:

       .. code::

          Padding.fixed_20(Text("This will be centered and fixed sized
                                 of 20 columns"))

    .. py:meth:: center_X(:class:`urwid.Widget`)

       This method centers a widget with X being the relative width of
       the widget.

       .. code::

          Padding.center_10(Text("This will be centered with a "
                                 "width of 10 columns"))

    .. py:meth:: left_X(:class:`urwid.Widget`)

       This method aligns a widget left with X being the relative width of
       the widget.

       .. code::

          Padding.left_10(Text("This will be left aligned with a "
                               "width of 10 columns"))

    .. py:meth:: right_X(:class:`urwid.Widget`)

       This method right aligns a widget with X being the relative width of
       the widget.

       .. code::

          Padding.right_10(Text("This will be right aligned with a "
                                "width of 10 columns"))

    """
    line_break = partialmethod(Text)


# This makes assumptions about the style names defined by both
# subiquity and console_conf. The fix is to stop using the Color class
# below, I think.
STYLE_NAMES = set([
    'body',
    'danger_button focus',
    'danger_button',
    'done_button focus',
    'done_button',
    'frame_footer',
    'frame_header',
    'info_error',
    'info_minor',
    'info_primary',
    'menu_button focus',
    'menu_button',
    'other_button focus',
    'other_button',
    'progress_complete',
    'progress_incomplete',
    'scrollbar focus',
    'scrollbar',
    'string_input focus',
    'string_input',
])


def apply_style_map(cls):
    """ Applies AttrMap attributes to Color class

    Eg:

      Color.frame_header(Text("I'm text in the Orange frame header"))
      Color.body(Text("Im text in wrapped with the body color"))
    """
    for k in STYLE_NAMES:
        kf = k + ' focus'
        if kf in STYLE_NAMES:
            setattr(cls, k, partialmethod(AttrMap, attr_map=k, focus_map=kf))
        else:
            setattr(cls, k, partialmethod(AttrMap, attr_map=k))
    return cls


@apply_style_map
class Color:
    """ Partial methods for :class:`~subiquity.palette.STYLES`

    .. py:meth:: frame_header(:class:`urwid.Widget`)

       This method colors widget based on the style map used.

       .. code::

          Color.frame_header(Text("This will use foreground and background "
                                  "defined from the STYLES attribute"))

    """
    pass


_disable_everything_map = {k: 'info_minor' for k in STYLE_NAMES | set([None])}


def disabled(w):
    return WidgetDisable(AttrMap(w, _disable_everything_map))


class Toggleable(delegate_to_widget_mixin('_original_widget'),
                 WidgetDecoration):

    def __init__(self, original):
        self.original = original
        self.enabled = False
        self.enable()

    def enable(self):
        if not self.enabled:
            self.original_widget = self.original
            self.enabled = True

    def disable(self):
        if self.enabled:
            self.original_widget = disabled(self.original)
            self.enabled = False


def button_pile(buttons):
    max_label = 10
    for button in buttons:
        button = button.base_widget
        if not isinstance(button, Button):
            raise RuntimeError("button_pile takes a list of buttons, not %s",
                               button)
        max_label = max(len(button.label), max_label)
    width = max_label + 4
    return _Padding(Pile(buttons), min_width=width,
                    width=width, align='center')


def screen(rows, buttons, focus_buttons=True, excerpt=None, narrow_rows=False):
    """Helper to create a common screen layout.

    The commonest screen layout in subiquity is:

        [ 1 line padding (optional) ]
        excerpt (optional)
        [ 1 line padding ]
        Box widget (usually a ListBox)
        [ 1 line padding ]
        a button_pile
        [ 1 line padding ]

    This helper makes creating this a 1-liner.
    """
    if isinstance(rows, list):
        rows = ListBox(rows)
    if narrow_rows:
        rows = Padding.center_63(rows)
    if buttons is None:
        focus_buttons = False
    elif isinstance(buttons, list):
        buttons = button_pile(buttons)
    excerpt_rows = []
    if excerpt is not None:
        excerpt_rows = [
            ('pack', Text("")),
            ('pack', Text(excerpt)),
            ]
    body = [
        ('pack', Text("")),
        rows,
        ('pack', Text("")),
    ]
    if buttons is not None:
        body.extend([
            ('pack', buttons),
            ('pack', Text("")),
        ])
    pile = Pile(excerpt_rows + body)
    if focus_buttons:
        pile.focus_position = len(excerpt_rows) + 3
    return Padding.center_79(pile)
