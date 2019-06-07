# Copyright 2019 Canonical, Ltd.
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

""" zdev

Provides device activation and configuration on s390x

"""
import logging

from urwid import (
    connect_signal,
    Text,
    )

from subiquitycore.ui.actionmenu import (
    ActionMenu,
    )
from subiquitycore.ui.buttons import (
    back_btn,
    done_btn,
    )
from subiquitycore.ui.container import (
    Pile,
    )
from subiquitycore.ui.table import (
    TableListBox,
    TablePile,
    TableRow,
    )
from subiquitycore.ui.utils import (
    Color,
    make_action_menu_row,
    screen,
    )
from subiquitycore.view import BaseView

log = logging.getLogger('subiquity.ui.zdev')


class ZdevView(BaseView):
    title = _("Zdev setup")
    footer = _("Activate and configure Z devices")

    def __init__(self, controller):
        log.debug('FileSystemView init start()')
        self.controller = controller

        header = TablePile([
            TableRow([
                Color.info_minor(heading) for heading in [
                    Text(_("ID")),
                    Text(_("ONLINE")),
                    Text(_("TYPE")),
                    Text(_("NAMES")),
                ]])])

        self.lb = TableListBox(self._make_zdev_rows())
        self.lb.bind(header)

        pile = Pile([
            ('pack', header),
            self.lb,
            ])

        frame = screen(
            pile, self._build_buttons(),
            focus_buttons=True)
        super().__init__(frame)
        log.debug('ZdevView init complete()')

    def _zdev_action(self, sender, action, user_arg):
        zdevinfo, row = user_arg
        if action in ('disable', 'enable'):
            self.controller.chzdev(action, zdevinfo)
        row.base_widget.cells[1] = (1, zdevinfo.status)
        self.lb.invalidate()

    def _open_zdev(self, action_menu, zdevinfo):
        actions = [(_("Enable"), not zdevinfo.on, 'enable'),
                   (_("Disable"), zdevinfo.on, 'disable')]
        action_menu.set_actions(actions)

    def _make_zdev_row(self, zdevinfo):
        menu = ActionMenu([])
        cells = [
            Text(zdevinfo.id),
            zdevinfo.status,
            Text(zdevinfo.type),
            Text(zdevinfo.names),
            menu,
        ]
        row = make_action_menu_row(
            cells,
            menu,
            attr_map='menu_button',
            focus_map={
                None: 'menu_button focus',
                'info_minor': 'menu_button focus',
            })
        connect_signal(menu, 'action', self._zdev_action, (zdevinfo, row))
        connect_signal(menu, 'open', self._open_zdev, zdevinfo)
        return row

    def _make_zdev_rows(self):
        rows = []
        for zdevinfo in self.controller.get_zdevinfos():
            rows.append(self._make_zdev_row(zdevinfo))
        return rows

    def _build_buttons(self):
        return [
            done_btn(_("Continue"), on_press=self.done),
            back_btn(_("Back"), on_press=self.cancel),
            ]

    def cancel(self, button=None):
        self.controller.cancel()

    def done(self, result):
        self.controller.done()
