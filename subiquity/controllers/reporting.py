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

import contextlib

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
        self.stack = []

    def start(self):
        update_configuration({'default': {'type': 'log'}})

    def _name(self):
        return '/'.join([s[0] for s in self.stack])

    def event_start(self, name, description):
        self.stack.append((name, description))
        report_start_event(self._name(), description)
        return 

    def event_stop(self, result):
        report_finish_event(self._name(), self.stack[-1][1], result)
        self.stack.pop()

    @contextlib.contextmanager
    def event(self, name, description):
        self.event_start(name, description)
        try:
            yield
        except BaseException:
            self.event_stop(status.FAIL)
        else:
            self.event_stop(status.SUCCESS)
