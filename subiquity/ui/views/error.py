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

from urwid import (
    Text,
    )

from subiquitycore.ui.buttons import other_btn
from subiquitycore.ui.stretchy import Stretchy
from subiquitycore.ui.table import (
    ColSpec,
    TablePile,
    TableRow,
    )
from subiquitycore.ui.utils import (
    button_pile,
    ClickableIcon,
    Color,
    )


log = logging.getLogger('subiquity.ui.error')


def close_btn(parent):
    return other_btn(
        _("Close"), on_press=lambda sender: parent.remove_overlay())


class ErrorReportListStretchy(Stretchy):

    def __init__(self, app, parent):
        self.app = app
        self.parent = parent
        self.ec = app.error_controller
        rows = [
            TableRow([
                Text(""),
                Text(_("SUMMARY")),
                Text(_("KIND")),
                Text(_("STATUS")),
                Text(""),
            ])]
        self.report_to_row = {}
        for report in self.app.error_controller.reports.values():
            r = self.report_to_row[report] = self.row_for_report(report)
            rows.append(r)
        self.table = TablePile(rows, colspecs={1: ColSpec(can_shrink=True)})
        widgets = [
            self.table,
            Text(""),
            button_pile([close_btn(parent)]),
            ]
        super().__init__(_("Error Reports"), widgets, 0, 0)

    def open_report(self, sender, report):
        pass

    def row_for_report(self, report):
        icon = ClickableIcon(report.summary, 0)
        cells = [
            Text("["),
            icon,
            Text(_(report.kind.value)),
            Text(_(report.reporting_state.name)),
            Text("]"),
            ]
        return Color.menu_button(TableRow(cells))
