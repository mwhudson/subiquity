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

import collections
import datetime
import enum
import inspect
from typing import List, Optional

import attr


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
                if issubclass(field.type, enum.Enum):
                    r[field.name] = v.name
                elif attr.has(field.type):
                    r[field.name] = asdict(v)
                else:
                    r[field.name] = v
    return r


def serialize(annotation, value):
    if annotation is inspect.Signature.empty:
        return value
    elif attr.has(annotation):
        return asdict(value)
    elif annotation in (str, int):
        return value
    else:
        raise Exception(str(annotation))


def deserialize(annotation, value):
    if annotation is inspect.Signature.empty:
        return value
    elif attr.has(annotation):
        d = {}
        for field in attr.fields(annotation):
            if field.name not in value:
                continue
            v = value[field.name]
            if issubclass(field.type, enum.Enum):
                d[field.name] = getattr(field.type, v)
            elif attr.has(field.type):
                d[field.name] = deserialize(field.type, v)
            else:
                d[field.name] = v
        return annotation(**d)
    elif annotation in (str, int):
        return value
    else:
        raise Exception(str(annotation))


class CheckState(enum.Enum):
    UNKNOWN = enum.auto()
    AVAILABLE = enum.auto()
    UNAVAILABLE = enum.auto()


@attr.s(auto_attribs=True)
class RefreshStatus:
    availability: CheckState
    current_snap_version: str
    new_snap_version: str


@attr.s(auto_attribs=True)
class KeyboardSetting:
    layout: str
    variant: str = ''
    toggle: Optional[str] = None


@attr.s(auto_attribs=True)
class Identity:
    realname: str
    username: str
    crypted_password: str = attr.ib(repr=False)
    hostname: str


@attr.s(auto_attribs=True)
class SSH:
    install_server: str
    allow_pw: bool
    authorized_keys: List[str] = attr.Factory(list)


class SnapCheckState(enum.Enum):
    FAILED = enum.auto()
    LOADING = enum.auto()
    DONE = enum.auto()


@attr.s(auto_attribs=True)
class ChannelSnapInfo:
    channel_name = attr.ib()
    revision = attr.ib()
    confinement = attr.ib()
    version = attr.ib()
    size = attr.ib()
    released_at: datetime.datetime = attr.ib(
        metadata={'time_fmt': '%Y-%m-%dT%H:%M:%S.%fZ'})


@attr.s(auto_attribs=True)
class SnapInfo:
    name: str
    summary: str
    publisher: str
    verified: str
    description: str
    confinement: str
    license: str
    channels: List[ChannelSnapInfo] = attr.Factory(list)


@attr.s(auto_attribs=True)
class SnapSelection:
    name: str
    channel: str
    is_classic: bool = False


@attr.s(auto_attribs=True)
class SnapListResponse:
    status: SnapCheckState
    snaps: List[SnapInfo]
    selection: List[SnapSelection]


class InstallState(enum.Enum):
    NOT_STARTED = enum.auto()
    RUNNING = enum.auto()
    UU_RUNNING = enum.auto()
    UU_CANCELLING = enum.auto()
    DONE = enum.auto()
    ERROR = enum.auto()

    def is_terminal(self):
        return self in [InstallState.DONE, InstallState.ERROR]


def api(cls):
    for k, v in cls.__dict__.items():
        if isinstance(v, type):
            v.__name__ = k
    return cls


def simple_endpoint(typ):
    class endpoint:
        def get() -> typ: pass
        def post(data: typ): pass
    return endpoint


@api
class API:
    locale = simple_endpoint(str)

    class refresh:
        def get() -> RefreshStatus: pass
        def post(data): pass

        class progress:
            class id:
                path = '{id}'
                def get(self): pass

        class wait:
            def get(self) -> RefreshStatus: pass

    keyboard = simple_endpoint(KeyboardSetting)
    proxy = simple_endpoint(str)
    mirror = simple_endpoint(str)
    identity = simple_endpoint(Identity)
    ssh = simple_endpoint(SSH)

    class snaplist:
        def get() -> SnapListResponse: pass
        def post(data: List[SnapSelection]): pass

        class info:
            class snap_name:
                path = '{snap}'
                def get() -> SnapInfo: pass

        class wait:
            def get() -> SnapListResponse: pass

    class install:
        class status:
            def get() -> InstallState: pass

    class reboot:
        def post(self, data): pass
