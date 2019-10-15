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
import shlex

from urwid import (
    connect_signal,
    Padding,
    ProgressBar,
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


def close_btn(parent, label=None):
    if label is None:
        label = _("Close")
    return other_btn(label, on_press=lambda sender: parent.remove_overlay())


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
If you're happy to be contacted to diagnose and test a fix for this
problem, you can report a bug with a Launchpad account.
""")

retry_text = _("""
Do you want to try starting the installation again?
""")

all_probing_failed_text = _("""
You may be able to fix the issue by switching to a shell and
reconfiguring the system's block devices.
""")

full_block_probe_failed = _("""
You can continue but the installer will just present the disks present
in the system, not other block devices.
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
        self.report_pb = ProgressBar(
            normal='progress_incomplete',
            complete='progress_complete')
        self.report_btn = Toggleable(
                other_btn(
                    _("Report a bug..."),
                    on_press=self.report_as_bug))
        self.complete_btn = other_btn(
                    _("Complete bug report"),
                    on_press=self.complete_reporting)
        self.shell_btn = other_btn(
                    _("Switch to a shell"),
                    on_press=self.debug_shell)
        self.restart_btn = other_btn(
                    _("Restart installer"),
                    on_press=self.restart)
        self.close_btn = close_btn(parent)
        btns = {
            self.complete_btn,
            self.view_btn,
            self.submit_btn,
            self.report_btn,
            self.close_btn,
            self.shell_btn,
            self.restart_btn,
            }
        w = max(map(widget_width, btns))
        for a in ('view_btn', 'submit_btn', 'report_btn', 'close_btn',
                  'complete_btn', 'shell_btn', 'restart_btn'):
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
        self.add_connection(
            self.ec, 'report_changed', self._report_changed)
        self.add_connection(
            self.ec, 'reporting_progress', self._reporting_progress)
        self.add_connection(
            self.ec, 'reporting_completed', self._reporting_completed)

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
                ]:
            self.submit_btn.base_widget.set_label(_("Submitting..."))
            self.submit_btn.original_widget.enabled = False
        elif self.report.reporting_state in [
                ErrorReportReportingState.UPLOADED,
                ]:
            self.submit_btn.base_widget.set_label(_("Submitted"))
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
            ]

        if self.report.reporting_state in [
                ErrorReportReportingState.REPORTING,
                ]:
            widgets.append(self.report_pb)
        elif self.report.reporting_state in [
                ErrorReportReportingState.REPORTED,
                ]:
            widgets.append(self.complete_btn)
        else:
            widgets.append(self.report_btn)

        widgets.append(Text(""))

        if self.report.kind == ErrorReportKind.INSTALL_FAILED:
            widgets.extend([
                Text(rewrap(_(retry_text))),
                Text(""),
                self.restart_btn,
                self.close_btn,
                ])
        elif self.report.kind == ErrorReportKind.FULL_BLOCK_PROBE_FAILED:
            widgets.extend([
                Text(rewrap(_(full_block_probe_failed))),
                Text(""),
                self.close_btn,
                ])
        elif self.report.kind == ErrorReportKind.RESTRICTED_BLOCK_PROBE_FAILED:
            widgets.extend([
                Text(rewrap(_(all_probing_failed_text))),
                Text(""),
                self.shell_btn,
                self.close_btn,
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
        self.title = report.summary

    def _reporting_progress(self, report):
        if report is not self.report:
            return
        if report.bytes_to_send is None or report.bytes_sent is None:
            return
        self.report_pb.done = report.bytes_to_send
        self.report_pb.current = report.bytes_sent

    def _reporting_completed(self, report):
        if report is not self.report:
            return
        self.complete_reporting()

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
        self.report.upload()

    def report_as_bug(self, sender):
        self.parent.show_stretchy_overlay(
            ErrorReportBugReportStretchy(self.ec, self.report, self.parent))

    def complete_reporting(self, sender=None):
        self.parent.show_stretchy_overlay(
            ErrorReportCompleteBugReportStretchy(
                self.ec, self.report, self.parent))

    def debug_shell(self, sender=None):
        self.app.debug_shell()

    def restart(self, sender=None):
        self.app.exit()

    def opened(self):
        self.report.mark_seen()


error_report_help = _("""
Reporting a bug in Launchpad involves uploading the crash report and
then visting a URL in a browser that is logged in as your account. If
the report is uploaded now (which requires an internet connection),
the URL to be visited can be displayed as a QR code, which may be
easier to use than a printed URL.
""")

persisted_help = _("""
The crash report has been saved to the install media (as
"crash/{base}.crash" on the filesystem with label "{label}"). This
report can be filed as a bug on another Ubuntu system by running
"apport-cli $crash_file".
""")


class ErrorReportBugReportStretchy(Stretchy):
    def __init__(self, ec, report, parent):
        self.ec = ec
        self.report = report
        self.parent = parent
        bp = button_pile([
            other_btn(_("Upload now"), on_press=self._report),
            close_btn(parent),
            ])
        widgets = [
            Text(rewrap(_(error_report_help))),
            Text(""),
            ]
        if self.ec.are_reports_persistent():
            t = _(persisted_help).format(
                base=self.report.base, label='casper-rw')
            widgets.extend([
                Text(rewrap(t)),
                Text(""),
                ])
        widgets.append(bp)
        super().__init__(_("Report as bug"), widgets, 0, len(widgets) - 1)

    def _report(self, sender):
        self.report.report()
        self.parent.remove_overlay()


class ErrorReportCompleteBugReportStretchy(Stretchy):
    def __init__(self, ec, report, parent):
        self.ec = ec
        self.report = report
        self.parent = parent
        bp = button_pile([
            other_btn(_("View as QR code"), on_press=self._qr),
            Text(""),
            close_btn(parent),
            ])
        widgets = [
            Text(_("You need to visit the below URL to complete the bug "
                   "report.")),
            Text(""),
            Text(self.report.reported_url),
            Text(""),
            ]
        widgets.append(bp)
        super().__init__(
            _("Complete bug report"), widgets, 0, len(widgets) - 1)

    def _qr(self, sender):
        self.ec.app.run_command_in_foreground(
            "qrencode -t UTF8 {} | less -R".format(
                shlex.quote(self.report.reported_url)), shell=True)


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
        for report in self.app.error_controller.reports:
            r = self.report_to_row[report] = self.row_for_report(report)
            rows.append(r)
        self.table = TablePile(rows, colspecs={1: ColSpec(can_shrink=True)})
        widgets = [
            self.table,
            Text(""),
            button_pile([close_btn(parent)]),
            ]
        super().__init__(_("Error Reports"), widgets, 0, 0)
        self.add_connection(self.ec, 'new_report', self._new_report)
        self.add_connection(self.ec, 'report_changed', self._report_changed)

    def open_report(self, sender, report):
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
