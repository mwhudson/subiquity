# Copyright 2020 Canonical, Ltd.
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

from subiquity.common.types import ErrorReportKind, ErrorReportRef


class DryRunController:

    def __init__(self, app):
        self.app = app
        self.context = app.context.child("DryRun")

    async def make_error_POST(self) -> ErrorReportRef:
        try:
            1/0
        except ZeroDivisionError:
            report = self.app.make_apport_report(
                ErrorReportKind.UNKNOWN, "example")
            return report.ref()

    async def crash_GET(self) -> None:
        1/0
