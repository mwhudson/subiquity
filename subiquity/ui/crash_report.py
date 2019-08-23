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

import apport.fileutils

from urwid import Text

from subiquitycore.ui.buttons import other_btn
from subiquitycore.ui.container import (
    Columns,
    WidgetWrap,
    )
from subiquitycore.ui.spinner import Spinner
from subiquitycore.ui.stretchy import Stretchy
from subiquitycore.ui.utils import button_pile


log = logging.getLogger('subiquity.ui.crash_report')


def stretchy_for_crash_report(parent, crash_file):

    def show(sender):
        parent.controller.app.run_command_in_foreground(
            ["less", crash_file])

    def upload(sender):
        apport.fileutils.mark_report_upload(crash_file)
        parent.remove_overlay()

    def close(sender):
        parent.remove_overlay()

    log.debug("loading from %s", crash_file)

    spinner = Spinner(parent.controller.app.loop, align='left')
    spinner.start()
    summary = WidgetWrap(Columns([Text("loading"), spinner]))

    def _bg_load():
        report = apport.Report()
        with open(crash_file, 'rb') as f:
            report.load(f, binary=False)
        return report
    def loaded(fut):
        try:
            report = fut.result()
        except Exception:
            summary_text = "loading problem report failed"
        else:
            summary_text = report.get('Summary', report['Title'])
        spinner.stop()
        summary._w = Text(summary_text)

    parent.controller.app.run_in_bg(_bg_load, loaded)

    widgets = [
        summary,
        Text(''),
        Text('Would you like to upload the problem report?'),
        Text(''),
        button_pile([
            other_btn("View problem report", on_press=show),
            other_btn("Submit problem report", on_press=upload),
            other_btn("Close", on_press=close),
            ]),
        ]


    return Stretchy("The installer encountered a problem", widgets, 0, len(widgets)-1)
