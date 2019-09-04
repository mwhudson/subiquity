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

import logging

from urwid import Text

from subiquitycore.ui.buttons import other_btn
from subiquitycore.ui.container import Pile
from subiquitycore.ui.stretchy import Stretchy
from subiquitycore.ui.table import (
    ColSpec,
    TablePile,
    TableRow,
    )
from subiquitycore.ui.utils import button_pile

log = logging.getLogger('subiquity.ui.view.help')


GLOBAL_KEY_HELP = _("""\
The following keys can be used at any time:""")

GLOBAL_KEYS = (
    (_('Control-S'), _('open a shell session')),
    (_('F1'),        _('help')),
    (_("ESC"),       _('go back')),
    )

DRY_RUN_KEYS = (
    (_('Control-X'), _('quit (dry-run only)')),
    )

class GlobalKeyHelpStretchy(Stretchy):

    def __init__(self, app, parent):
        close_btn = other_btn(_("Close"), on_press=lambda sender:parent.remove_overlay())
        rows = []
        for key, text in GLOBAL_KEYS:
            rows.append(TableRow([Text(_(key)), Text(_(text))]))
        if app.opts.dry_run:
            for key, text in DRY_RUN_KEYS:
                rows.append(TableRow([Text(_(key)), Text(_(text))]))
        table = TablePile(rows, spacing=2, colspecs={1:ColSpec(can_shrink=True)})
        widgets = [
            Pile([
                ('pack', Text(GLOBAL_KEY_HELP.strip())),
                ('pack', Text("")),
                ('pack', table),
                ]),
            Text(""),
            button_pile([close_btn]),
            ]
        super().__init__(_("Global hot keys"), widgets, 0, 2)


class GlobalHelpStretchy(Stretchy):
    pass

class LocalHelpStretchy(Stretchy):
    pass


class HelpStretchy(Stretchy):

    def __init__(self, app, parent):
        global_keys_btn = other_btn(_("Global Hot Keys"), on_press=lambda sender:parent.show_stretchy_overlay(GlobalKeyHelpStretchy(app, parent)))
        close_btn = other_btn(_("Close"), on_press=lambda sender:parent.remove_overlay())
        btns = button_pile([global_keys_btn, close_btn])
        btns.base_widget.focus_position = 1
        widgets = [
            Text("yo"),
            Text(""),
            btns,
            ]
        super().__init__(_("Help"), widgets, 2, 2)
