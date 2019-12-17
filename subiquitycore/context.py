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

import enum


class Status(enum.Enum):
    SUCCESS = enum.auto()
    FAILURE = enum.auto()
    SKIP = enum.auto()


class Context:

    def __init__(self, app, name, description, parent):
        self.app = app
        self.name = name
        self.description = description
        self.parent = parent

    def child(self, name, description=""):
        return Context(self.app, name, description, self)

    def _name(self):
        c = self
        names = []
        while c is not None:
            names.append(c.name)
            c = c.parent
        return '/'.join(reversed(names))

    def enter(self):
        self.app.report_start_event(self._name(), self.description)

    def exit(self, result=Status.SUCCESS):
        self.app.report_finish_event(self._name(), self.description, result)

    def __enter__(self):
        self.enter()
        return self

    def __exit__(self, exc, value, tb):
        if exc:
            result = Status.FAIL
        else:
            result = Status.SUCCESS
        self.exit(result)
