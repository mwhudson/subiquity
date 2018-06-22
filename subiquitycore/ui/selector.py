# Copyright 2017 Canonical, Ltd.
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

from urwid import (
    ACTIVATE,
    AttrMap,
    AttrWrap,
    CompositeCanvas,
    connect_signal,
    LineBox,
    PopUpLauncher,
    SelectableIcon,
    Text,
    WidgetDecoration,
    )

from subiquitycore.ui.container import (
    ListBox,
    WidgetWrap,
    )
from subiquitycore.ui.table import (
    ColSpec,
    TableListBox,
    TablePile,
    TableRow,
    )


class _PopUpButton(SelectableIcon):
    """It looks a bit like a radio button, but it just emits
       'click' on activation.
    """
    signals = ['click']

    states = {
        True: "",
        False: "",
        }

    def __init__(self, option, state):
        p = self.states[state]
        super().__init__(p + option, len(p))

    def keypress(self, size, key):
        if self._command_map[key] != ACTIVATE:
            return key
        self._emit('click')


class _PopUpSelectDialog(WidgetWrap):
    """A list of PopUpButtons with a box around them."""

    def __init__(self, parent, cur_index):
        self.parent = parent
        group = []
        for i, option in enumerate(self.parent._options):
            if option.enabled:
                if i == cur_index:
                    icon = _PopUpButton(" ◂ ", False)
                else:
                    icon = _PopUpButton("   ", False)
                connect_signal(icon, 'click', self.click, i)
                group.append(CursorOverride(AttrWrap(TableRow([Text(" " + option.label), icon]), 'menu_button', 'menu_button focus'), 1))
            else:
                btn = Text(" " + option.label)
                group.append(AttrWrap(TableRow([btn]), 'info_minor'))
        list_box = TableListBox(group)
        list_box.focus_position = cur_index
        super().__init__(LineBox(list_box))

    def click(self, btn, index):
        self.parent.index = index
        self.parent.close_pop_up()

    def keypress(self, size, key):
        if key == 'esc':
            self.parent.close_pop_up()
        else:
            return super().keypress(size, key)


class SelectorError(Exception):
    pass


class Option:

    def __init__(self, val):
        if not isinstance(val, tuple):
            if not isinstance(val, str):
                raise SelectorError("invalid option %r", val)
            self.label = val
            self.enabled = True
            self.value = val
        elif len(val) == 1:
            self.label = val[0]
            self.enabled = True
            self.value = val[0]
        elif len(val) == 2:
            self.label = val[0]
            self.enabled = val[1]
            self.value = val[0]
        elif len(val) == 3:
            self.label = val[0]
            self.enabled = val[1]
            self.value = val[2]
        else:
            raise SelectorError("invalid option %r", val)


class _PopUpLauncher(PopUpLauncher):

    def __init__(self, parent, content):
        self.parent = parent
        super().__init__(content)

    def create_pop_up(self):
        return self.parent.create_pop_up()

    def get_pop_up_parameters(self):
        return self.parent.get_pop_up_parameters()


class CursorOverride(WidgetDecoration):
    """Decoration to override where the cursor goes when a widget is focused.
    """

    def __init__(self, w, cursor_x=0):
        super().__init__(w)
        self.cursor_x = cursor_x

    def get_cursor_coords(self, size):
        return self.cursor_x, 0

    def rows(self, size, focus):
        return self._original_widget.rows(size, focus)

    def keypress(self, size, focus):
        return self._original_widget.keypress(size, focus)

    def render(self, size, focus=False):
        c = self._original_widget.render(size, focus)
        if focus:
            # create a new canvas so we can add a cursor
            c = CompositeCanvas(c)
            c.cursor = self.get_cursor_coords(size)
        return c


class Selector(WidgetWrap):
    """A widget that allows the user to chose between options by popping
       up a list of options.

    (A bit like <select> in an HTML form).
    """

    _prefix = "(+) "

    signals = ['select']

    def __init__(self, opts, index=0):
        options = []
        for opt in opts:
            if not isinstance(opt, Option):
                opt = Option(opt)
            options.append(opt)
        self._options = options
        self._set_index(index)
        super().__init__(_PopUpLauncher(self, self.ts[index]))

    @property
    def _options(self):
        return self.__options

    @_options.setter
    def _options(self, val):
        self.__options = val
        if not val:
            return
        colspecs = {0: ColSpec(can_shrink=True)}
        opt = val[0]
        ts = []
        icon = SelectableIcon(" ▾ ")
        for opt in val:
            t = TablePile([AttrMap(CursorOverride(TableRow([Text(opt.label), icon])), 'string_input', 'string_input focus')], colspecs=colspecs)
            ts.append(t)
        t0 = ts[0]
        for t in ts[1:]:
            t0.bind(t)
        self.ts = ts

    def keypress(self, size, key):
        if self._command_map[key] != ACTIVATE:
            return key
        self._w.open_pop_up()

    def _set_index(self, val):
        self._w = _PopUpLauncher(self, self.ts[val])
        self._index = val

    @property
    def index(self):
        return self._index

    @index.setter
    def index(self, val):
        self._emit('select', self._options[val].value)
        self._set_index(val)

    def option_by_label(self, label):
        for opt in self._options:
            if opt.label == label:
                return opt

    def option_by_value(self, value):
        for opt in self._options:
            if opt.value == value:
                return opt

    def option_by_index(self, index):
        return self._options[index]

    @property
    def value(self):
        return self._options[self._index].value

    @value.setter
    def value(self, val):
        for i, opt in enumerate(self._options):
            if opt.value == val:
                self.index = i
                return
        raise AttributeError("cannot set value to %r", val)

    def create_pop_up(self):
        return _PopUpSelectDialog(self, self.index)

    def get_pop_up_parameters(self):
        # line on left, space, line on right
        width = (max([len(o.label) for o in self._options]) +
                 len(self._prefix) + 4)
        return {'left': -2, 'top': -self.index - 1,
                'overlay_width': width,
                'overlay_height': len(self._options) + 2}

    def close_pop_up(self):
        self._w.close_pop_up()
