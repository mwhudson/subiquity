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
    connect_signal,
    disconnect_signal,
    Text,
    )

from subiquitycore.ui.buttons import other_btn
from subiquitycore.ui.stretchy import Stretchy
from subiquitycore.ui.table import (
    TablePile,
    TableRow,
    )
from subiquitycore.ui.utils import (
    button_pile,
    ClickableIcon,
    )

log = logging.getLogger('subiquity.ui.error')


def close_btn(parent):
    return other_btn(
        _("Close"), on_press=lambda sender: parent.remove_overlay())


class ErrorReportStretchy(Stretchy):

    def __init__(self, report, parent):
        self.report = report
        self.parent = parent
        super().__init__("report", [Text(report.summary)], 0, 0)


class ErrorReportListStretchy(Stretchy):

    def __init__(self, app, parent):
        self.app = app
        self.parent = parent
        self.ec = app.error_controller
        rows = [
            TableRow([
                Text(""),
                Text(_("SUMMARY")),
                Text(_("STATUS")),
                Text(""),
            ])]
        self.report_to_row = {}
        for report in self.app.error_controller.reports.values():
            r = self.report_to_row[report] = self.row_for_report(report)
            rows.append(r)
        connect_signal(
            self.app.error_controller, 'new_report', self._new_report)
        self.table = TablePile(rows)
        widgets = [
            self.table,
            Text(""),
            button_pile([close_btn(parent)]),
            ]
        super().__init__(_("Error Reports"), widgets, 0, 0)

    def focus_report(self, report):
        row = self.report_to_row.get(report)
        for i, orow in enumerate(self.table.table_rows):
            if orow.base_widget == row:
                break
        else:
            return
        self.table.focus_position = i

    def open_report(self, sender, report):
        self.parent.show_stretchy_overlay(ErrorReportStretchy(
            report, self))

    def row_for_report(self, report):
        icon = ClickableIcon(report.summary, 0)
        connect_signal(icon, 'click', self.open_report, report)
        cells = [
            Text("["),
            icon,
            Text(_(report.state.name)),
            Text("]"),
            ]
        return TableRow(cells)

    def opened(self):
        connect_signal(self.ec, 'new_report', self._new_report)
        connect_signal(self.ec, 'report_changed', self._report_changed)

    def closed(self):
        disconnect_signal(self.ec, 'new_report', self._new_report)
        disconnect_signal(self.ec, 'report_changed', self._report_changed)

    def _new_report(self, report):
        pass

    def _report_changed(self, report):
        r = self.report_to_row.get(report)
        if r is None:
            return
        r.cells[2][1].set_text(_(report.state.name))
        self.table.invalidate()
