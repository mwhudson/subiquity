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

import apport.fileutils

from urwid import Text

from subiquitycore.ui.buttons import other_btn
from subiquitycore.ui.stretchy import Stretchy
from subiquitycore.ui.utils import button_pile


def stretchy_for_crash_report(parent, crash_file):
    def show(sender):
        parent.controller.app.run_command_in_foreground(
            ["less", crash_file])

    def upload(sender):
        apport.fileutils.mark_report_upload(crash_file)
        parent.remove_overlay()

    def close(sender):
        parent.remove_overlay()

    widgets = [
        Text('Blah'),
        Text(''),
        Text('Would you like to upload the crash report?'),
        Text(''),
        button_pile([
            other_btn("View crash file", on_press=show),
            other_btn("Submit crash report", on_press=upload),
            other_btn("Close", on_press=close),
            ]),
        ]
    return Stretchy("An error occurred", widgets, 0, 4)
