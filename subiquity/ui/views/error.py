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
from subiquitycore.ui.container import Pile
from subiquitycore.ui.stretchy import Stretchy
from subiquitycore.ui.table import (
    TablePile,
    TableRow,
    )
from subiquitycore.ui.utils import (
    button_pile,
    ClickableIcon,
    Toggleable,
    )

from subiquity.controllers.error import (
    ErrorReportState,
    )

log = logging.getLogger('subiquity.ui.error')


def close_btn(parent):
    return other_btn(
        _("Close"), on_press=lambda sender: parent.remove_overlay())

def rewrap(text):
    paras = text.split("\n\n")
    return "\n\n".join([p.replace('\n', ' ') for p in paras]).strip()

error_intro_text = _("""
Unfortunately the installer encountered an error.
""")

incomplete_text = _("""

Information is being collected from the system that will help the
developers diagnose the report.

""")

complete_text = _("""

You can view the report (in less), and assuming you have an internet
connection, submit the report to the error tracker and/or create a bug
report in Launchpad.

Reporting a bug requires that you have or create a Launchpad account
and can visit a URL to complete the filing of the report (the URL can
be displayed as a QR code which might make this easier).

(something here about how to report the bug from another machine)

""")


class ErrorReportStretchy(Stretchy):

    def __init__(self, app, ec, report, parent):
        self.app = app
        self.ec = ec
        self.report = report
        self.parent = parent

        self.view_btn = Toggleable(
                other_btn(
                    _("View the report"),
                    on_press=self.view_report))
        self.submit_btn = Toggleable(
                other_btn(
                    _("Submit to the error tracker"),
                    on_press=self.submit))
        self.report_btn = Toggleable(
                other_btn(
                    _("Report as a bug in Launchpad"),
                    on_press=self.report_as_bug))
        self.btns = [
            self.view_btn, self.submit_btn, self.report_btn,
            ]
        self.table = TablePile(self.rows_for_report())
        self.desc = Text("")
        pile = Pile([
            ('pack', Text(rewrap(_(error_intro_text)))),
            ('pack', Text("")),
            ('pack', self.table),
            ('pack', Text("")),
            ('pack', self.desc),
            ])
        self.bp = button_pile(self.btns + [close_btn(parent)])
        self._report_changed(self.report)
        widgets = [
            pile,
            Text(""),
            self.bp,
            ]
        super().__init__(report.summary, widgets, 0, 2)

    def _report_changed(self, report):
        if report is not self.report:
            return
        if report.state == ErrorReportState.INCOMPLETE:
            text = rewrap(_(incomplete_text))
            for btn in self.btns:
                btn.enabled = False
        else:
            text = rewrap(_(complete_text))
            for btn in self.btns:
                btn.enabled = True
            if report.state in [ErrorReportState.UPLOADING, ErrorReportState.UPLOADED]:
                self.submit_btn.enabled = False
        while not self.bp.base_widget.focus.selectable():
            self.bp.base_widget.focus_position += 1
        self.desc.set_text(text)
        self.table.set_contents(self.rows_for_report())

    def rows_for_report(self):
        rows = [
            ("Summary:", self.report.summary),
            ("State:", self.report.state.name),
            # XXX display relative date here!
            ("Reported:", self.report.pr.get("Date", "???")),
            ]
        return [TableRow(map(Text, r)) for r in rows]

    def view_report(self, sender):
        self.app.run_command_in_foreground(["less", self.report.path])

    def submit(self, sender):
        self.report.mark_for_upload()

    def report_as_bug(self, sender):
        pass

    def opened(self):
        connect_signal(self.ec, 'report_changed', self._report_changed)

    def closed(self):
        disconnect_signal(self.ec, 'report_changed', self._report_changed)


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
        report.mark_seen()
        self.parent.show_stretchy_overlay(ErrorReportStretchy(
            self.app, self.ec, report, self.parent))

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
        for (span, cell), (span2, cell2) in zip(r.cells, self.row_for_report(report).cells):
            cell.set_text(cell2.text)
        self.table.invalidate()

