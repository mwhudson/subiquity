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

import attr
import collections
import enum


def asdict(inst):
    r = collections.OrderedDict()
    for field in attr.fields(type(inst)):
        if field.name.startswith('_'):
            continue
        m = getattr(inst, 'serialize_' + field.name, None)
        if m:
            r.update(m())
        else:
            v = getattr(inst, field.name)
            if v is not None:
                if field.metadata.get('enum_cls', False):
                    r[field.name] = v.name
                else:
                    r[field.name] = v
    return r


def enumfield(enum_cls):
    return attr.ib(
        converter=lambda a: getattr(enum_cls, a),
        metadata={'enum_cls': enum_cls})


@attr.s
class Locale:
    language = attr.ib()


class CheckState(enum.Enum):
    UNKNOWN = enum.auto()
    AVAILABLE = enum.auto()
    UNAVAILABLE = enum.auto()


class RefreshResponse:
    status = enumfield(CheckState)
    current_snap_version = attr.ib()
    new_snap_version = attr.ib()


class API:

    class locale:
        def get() -> Locale: pass
        def post(data: Locale): pass

    class refresh:

        def get() -> RefreshResponse: pass
        def post(data: None) -> None: pass

        class progress:
            class id:
                path = '{id}'
                def get(self): pass

        class wait:
            def get(self) -> RefreshResponse: pass
