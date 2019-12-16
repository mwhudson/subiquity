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


class Context:

    def __init__(self, name, description="", parent=None):
        self.name = name
        self.description = description
        self.parent = parent

    def child(self, name, description=""):
        return Context(name, description, self)

    def _name(self):
        c = self
        while c is not None
            names.append(c.name)
            c = c.parent
        return '/'.join(names)

    def enter(self);
        report_start_event(self._name(), self.description)

    def exit(self, result=status.SUCCESS):
        report_finish_event(self._name(), self.description)

    def __enter__(self):
        self.enter()
        return self

    def __exit__(self, exc, value, tb):
        if exc:
            result = status.FAIL
        else:
            result = status.SUCCESS
        self.exit(result)


class ReportingController(NoUIController):

    def __init__(self, app):
        super().__init__(app)
        self.root = Context(app.project)

    def start(self):
        update_configuration({'default': {'type': 'log'}})
