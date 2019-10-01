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
    Padding,
    Text,
    )

from subiquitycore.ui.buttons import other_btn
from subiquitycore.ui.container import (
    Pile,
    )
from subiquitycore.ui.form import (
    Toggleable,
    )
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
    rewrap,
    )
from subiquitycore.ui.width import (
    widget_width,
    )

from subiquity.controllers.error import (
    ErrorReportKind,
    ErrorReportConstructionState,
    ErrorReportReportingState,
    )


log = logging.getLogger('subiquity.ui.error')


def close_btn(parent):
    return other_btn(
        _("Close"), on_press=lambda sender: parent.remove_overlay())


error_report_intros = {
    ErrorReportKind.FULL_BLOCK_PROBE_FAILED: _("""
Sorry, there was a problem examining the storage devices on this system.
"""),
    ErrorReportKind.RESTRICTED_BLOCK_PROBE_FAILED: _("""
Sorry, there was a problem examining the storage devices on this system.
"""),
    ErrorReportKind.INSTALL_FAILED: _("""
Sorry, there was a problem completing the installation.
"""),
    ErrorReportKind.UI_CRASH: _("""
Sorry, the installer has restarted because of an error.
"""),
    ErrorReportKind.UNKNOWN: _("""
Sorry, an unknown error occurred.
"""),
}

incomplete_text = _("""
Information is being collected from the system that will help the
developers diagnose the report.
""")

submit_text = _("""
If you want to help improve the installer, you can send an error report.
""")

report_text = _("""
If you’re happy to be contacted to diagnose and test a fix for this
problem, you can report a bug with a Launchpad account.
""")

retry_text = _("""
Do you want to try starting the installation again?
""")

all_probing_failed_text = _("""
XXX
""")

full_block_probe_failed = _("""
XXX
""")


class ErrorReportStretchy(Stretchy):

    def __init__(self, app, ec, report, parent):
        self.app = app
        self.ec = ec
        self.report = report
        self.parent = parent

        self.view_btn = Toggleable(
                other_btn(
                    _("View Error Report"),
                    on_press=self.view_report))

        # Should here offer view / report / close
        # close without report should prompt to report to error tracker
        # reporting a bug should _also_ submit to the error tracker
        # no point offering any upload/report options if there is no network
        # should also explain how to report a bug on another machine
        self.submit_btn = Toggleable(
                other_btn(
                    _("Send to Canonical"),
                    on_press=self.submit))
        self.report_btn = Toggleable(
                other_btn(
                    _("Report a bug..."),
                    on_press=self.report_as_bug))
        self.close_btn = close_btn(parent)
        btns = {
            self.view_btn,
            self.submit_btn,
            self.report_btn,
            self.close_btn,
            }
        w = max(map(widget_width, btns))
        for a in 'view_btn', 'submit_btn', 'report_btn', 'close_btn':
            setattr(
                self,
                a,
                Padding(getattr(self, a), width=w, align='center'))
        self.table = TablePile(self.rows_for_report())
        self.desc = Text("")
        self.pile = Pile([])
        self._report_changed(self.report)
        widgets = [
            self.pile,
            ]
        super().__init__(report.summary, widgets, 0, 0)

    def _pile_elements(self):
        INCOMPLETE = ErrorReportConstructionState.INCOMPLETE
        LOADING = ErrorReportConstructionState.LOADING
        if self.report.construction_state == INCOMPLETE:
            return [
                Text(rewrap(_(incomplete_text))),
                Text(""),
                self.close_btn,
                ]
        elif self.report.construction_state == LOADING:
            return [
                Text(rewrap(_("Loading"))),
                Text(""),
                self.close_btn,
                ]
        if self.report.reporting_state in [
                ErrorReportReportingState.UPLOADING,
                ErrorReportReportingState.UPLOADED,
                ]:
            self.submit_btn.base_widget.set_label(_("Submitting..."))
            self.submit_btn.original_widget.enabled = False
        else:
            self.submit_btn.original_widget.enabled = True
        widgets = [
            Text(rewrap(_(error_report_intros[self.report.kind]))),
            Text(""),
            TablePile(self.rows_for_report()),
            Text(""),
            Text(rewrap(_(submit_text))),
            Text(""),
            self.view_btn,
            self.submit_btn,
            Text(""),
            Text(rewrap(_(report_text))),
            Text(""),
            self.report_btn,
            Text(""),
            ]
        if self.report.kind == ErrorReportKind.INSTALL_FAILED:
            widgets.extend([
                Text(rewrap(_(retry_text))),
                Text(""),
                ])
        elif self.report.kind == ErrorReportKind.FULL_BLOCK_PROBE_FAILED:
            widgets.extend([
                Text(rewrap(_(full_block_probe_failed))),
                Text(""),
                ])
        elif self.report.kind == ErrorReportKind.RESTRICTED_BLOCK_PROBE_FAILED:
            widgets.extend([
                Text(rewrap(_(all_probing_failed_text))),
                Text(""),
                ])
        else:
            widgets.extend([
                self.close_btn,
                ])
        return widgets

    def _report_changed(self, report):
        if report is not self.report:
            return
        self.pile.contents[:] = [
            (w, self.pile.options('pack')) for w in self._pile_elements()]
        while not self.pile.focus.selectable():
            self.pile.focus_position += 1

    def rows_for_report(self):
        rows = [
            ("Summary:", self.report.summary),
            ("State:", self.report.reporting_state.name),
            # XXX display relative date here!
            ("Date:", self.report.pr.get("Date", "???")),
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
        report.mark_seen()
        self.parent.show_stretchy_overlay(ErrorReportStretchy(
            self.app, self.ec, report, self.parent))

    def cells_for_report(self, report):
        icon = ClickableIcon(report.summary, 0)
        connect_signal(icon, 'click', self.open_report, report)
        return [
            Text("["),
            icon,
            Text(_(report.kind.value)),
            Text(_(report.reporting_state.name)),
            Text("]"),
            ]

    def row_for_report(self, report):
        return Color.menu_button(
            TableRow(self.cells_for_report(report)))

    def opened(self):
        connect_signal(self.ec, 'new_report', self._new_report)
        connect_signal(self.ec, 'report_changed', self._report_changed)

    def closed(self):
        disconnect_signal(self.ec, 'new_report', self._new_report)
        disconnect_signal(self.ec, 'report_changed', self._report_changed)

    def _new_report(self, report):
        i = len(self.table.table_rows)
        r = self.report_to_row[report] = self.row_for_report(report)
        self.table.insert_rows(i, [r])

    def _report_changed(self, report):
        old_r = self.report_to_row.get(report)
        if old_r is None:
            return
        old_r = old_r.base_widget
        new_cells = self.cells_for_report(report)
        for (s1, old_c), new_c in zip(old_r.cells, new_cells):
            old_c.set_text(new_c.text)
        self.table.invalidate()
