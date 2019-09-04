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
from subiquitycore.lsb_release import lsb_release
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


GENERAL_HELP = _("""
Welcome to the Ubuntu Server Installer!

The most popular server Linux in the cloud and data centre, you can
rely on Ubuntu Server and its five years of guaranteed free upgrades.

The installer will guide you through installing Ubuntu Server
{release}.

The installer only requires the up and down arrow keys, space (or
return) and the occasional bit of typing.""")


def rewrap(text):
    paras = text.split("\n\n")
    return "\n\n".join([p.replace('\n', ' ') for p in paras]).strip()

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
                ('pack', Text(rewrap(GLOBAL_KEY_HELP))),
                ('pack', Text("")),
                ('pack', table),
                ]),
            Text(""),
            button_pile([close_btn]),
            ]
        super().__init__(_("Global hot keys"), widgets, 0, 2)


class GeneralHelpStretchy(Stretchy):
    def __init__(self, parent):
        close_btn = other_btn(_("Close"), on_press=lambda sender:parent.remove_overlay())
        widgets = [
            Text(rewrap(GENERAL_HELP.format(**lsb_release()))),
            Text(""),
                button_pile([close_btn]),
            ]
        super().__init__(_("General help"), widgets, 0, 2)

class LocalHelpStretchy(Stretchy):
    pass


class HelpStretchy(Stretchy):

    def __init__(self, app, parent):
        general_help_btn = other_btn(_("General Help"), on_press=lambda sender:parent.show_stretchy_overlay(GeneralHelpStretchy(parent)))
        global_keys_btn = other_btn(_("Global Hot Keys"), on_press=lambda sender:parent.show_stretchy_overlay(GlobalKeyHelpStretchy(app, parent)))
        close_btn = other_btn(_("Close"), on_press=lambda sender:parent.remove_overlay())
        btns = button_pile([general_help_btn, global_keys_btn, close_btn])
        btns.base_widget.focus_position = len(btns.base_widget.contents) - 1
        widgets = [
            Text(_("Select the topic you would like help on:")),
            Text(""),
            btns,
            ]
        super().__init__(_("Help"), widgets, 2, 2)
