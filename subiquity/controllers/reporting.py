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

from curtin.reporter import (
    update_configuration,
    )
from curtin.reporter.events import (
    report_finish_event,
    report_start_event,
    status,
    )

from subiquitycore.controller import NoUIController


class ReportingController(NoUIController):

    def __init__(self, app):
        super().__init__(app)

    def start(self):
        update_configuration({'default': {'type': 'log'}})

    def report_start_event(self, name, description):
        report_start_event(name, description)

    def report_finish_event(self, name, description, result):
        result = getattr(status, result.name, status.WARN)
        report_finish_event(name, description, result)
