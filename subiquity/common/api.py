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
import inspect


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


def identity(x):
    return x


def serializer(annotation):
    if annotation is inspect.Signature.empty:
        return lambda x: x
    elif attr.has(annotation):
        return asdict
    else:
        raise Exception(str(annotation))


def deserializer(annotation):
    if annotation is inspect.Signature.empty:
        return identity
    elif attr.has(annotation):
        return lambda x: annotation(**x)
    else:
        raise Exception(str(annotation))


def enumfield(enum_cls):
    def conv(a):
        if isinstance(a, enum_cls):
            return a
        else:
            return getattr(enum_cls, a)
    return attr.ib(
        converter=conv,
        metadata={'enum_cls': enum_cls})


@attr.s
class Locale:
    language = attr.ib()


class CheckState(enum.Enum):
    UNKNOWN = enum.auto()
    AVAILABLE = enum.auto()
    UNAVAILABLE = enum.auto()


@attr.s
class RefreshStatus:
    availability = enumfield(CheckState)
    current_snap_version = attr.ib()
    new_snap_version = attr.ib()


class API:

    class locale:
        def get() -> Locale: pass
        def post(data: Locale): pass

    class refresh:

        def get() -> RefreshStatus: pass
        def post(data): pass

        class progress:
            class id:
                path = '{id}'
                def get(self): pass

        class wait:
            def get(self) -> RefreshStatus: pass
