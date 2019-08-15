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

from urwid import Text

from subiquitycore.ui.buttons import _stylized_button
from subiquitycore.ui.container import (
    Pile,
    )
from subiquitycore.ui.frame import SubiquityCoreUI
from subiquitycore.ui.table import (
    ColSpec,
    TablePile,
    TableRow,
    )


log = logging.getLogger('subiquitycore.ui.frame')

GLOBAL_HELP = _("""\
GLOBAL HOT KEYS

The following keys can be used at any time:""")

GLOBAL_KEYS = (
    (_('Control-S'), _('drop to a shell session')),
    (_('F1'),        _('open this help dialog')),
    (_("ESC"),       _('close current dialog or menu or go to previous screen if none')),
    )


class SubiquityUI(SubiquityCoreUI):

    def __init__(self, app):
        self.right_icon = _stylized_button("[", "]", 'xx')(
            _("Help"), on_press=lambda sender:app.show_help())
        self.right_icon.attr_map = {}
        self.right_icon.focus_map = {None: 'progress_incomplete'}
        super().__init__()

    def global_help(self):
        rows = []
        for key, text in GLOBAL_KEYS:
            rows.append(TableRow([Text(_(key)), Text(_(text))]))
        table = TablePile(rows, spacing=2, colspecs={1:ColSpec(can_shrink=True)})
        return Pile([
            ('pack', Text(GLOBAL_HELP.strip())),
            ('pack', Text("")),
            ('pack', table),
            ])
