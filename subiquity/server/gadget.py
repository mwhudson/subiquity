# Copyright 2022 Canonical, Ltd.
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

import asyncio
import contextlib
import enum
import json as json_mod
from typing import Dict, List, Optional

from subiquitycore import snapd

from subiquity.common.api.client import make_client
from subiquity.common.api.defs import api, path_parameter
from subiquity.common.serialize import Serializer

import attr


def named_field(name, default=attr.NOTHING):
    return attr.ib(metadata={'name': name}, default=default)


class Role(enum.Enum):

    NONE = ''
    MBR = 'mbr'
    SYSTEM_BOOT = 'system-boot'
    SYSTEM_BOOT_IMAGE = 'system-boot-image'
    SYSTEM_BOOT_SELECT = 'system-boot-select'
    SYSTEM_DATA = 'system-data'
    SYSTEM_RECOVERY_SELECT = 'system-recovery-select'
    SYSTEM_SAVE = 'system-save'
    SYSTEM_SEED = 'system-seed'


@attr.s(auto_attribs=True)
class RelativeOffset:
    relative_to: str = named_field('relative-to')
    offset: int


@attr.s(auto_attribs=True)
class VolumeContent:
    source: str = ''
    target: str = ''
    image: str = ''
    offset: Optional[int] = None
    offset_write: Optional[RelativeOffset] = named_field('offset-write', None)
    size: int = 0
    unpack: bool = False


@attr.s(auto_attribs=True)
class VolumeUpdate:
    edition: int = 0
    preserve: Optional[List[str]] = None


@attr.s(auto_attribs=True)
class VolumeStructure:
    name: str = ''
    label: str = named_field('filesystem-label', '')
    offset: Optional[int] = None
    offset_write: Optional[RelativeOffset] = named_field('offset-write', None)
    size: int = 0
    type: str = ''
    role: Role = Role.NONE
    id: Optional[str] = None
    filesystem: str = ''
    content: Optional[List[VolumeContent]] = None
    update: VolumeUpdate = attr.Factory(VolumeUpdate)


@attr.s(auto_attribs=True)
class Volume:
    schema: str = ''
    bootloader: str = ''
    id: str = ''
    structure: Optional[List[VolumeStructure]] = None


@attr.s(auto_attribs=True)
class SystemDetails:
    current: bool = False
    volumes: Dict[str, Volume] = attr.Factory(dict)


connection = snapd.SnapdConnection('/', '/var/run/snapd.socket')
snapd = snapd.AsyncSnapd(connection)


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    async def json(self):
        return self.data


@contextlib.asynccontextmanager
async def make_request(method, path, *, params, json):
    if method == "GET":
        if path == "/v2/systems/20220914":
            with open('v2-systems-20220914.json') as fp:
                content = json_mod.load(fp)
        else:
            content = await snapd.get(path[1:], **params)
    else:
        1/0
    yield FakeResponse(content['result'])


class EnumByValueSerializer(Serializer):
    def _serialize_enum(self, annotation, value):
        return value.value

    def _deserialize_enum(self, annotation, value):
        return annotation(value)


serializer = EnumByValueSerializer(ignore_unknown_fields=True)


class SnapStatus(enum.Enum):
    ACTIVE = 'active'
    AVAILABLE = 'available'


@attr.s(auto_attribs=True)
class Publisher:
    id: str
    username: str
    display_name: str = named_field('display-name')


@attr.s(auto_attribs=True)
class Snap:
    id: str
    status: SnapStatus
    publisher: Publisher


@api
class SnapdAPI:
    serialize_query_args = False

    class v2:
        class snaps:
            @path_parameter
            class snap_name:
                def GET() -> Snap: ...

        class find:
            def GET(name: str) -> List[Snap]: ...

        class systems:
            @path_parameter
            class label:
                def GET() -> SystemDetails: ...


client = make_client(SnapdAPI, make_request, serializer=serializer)


async def run():
    print(await client.v2.snaps['go'].GET())
    system = await client.v2.systems['20220914'].GET()
    with open('v2-systems-20220914.json') as fp:
        content = json_mod.load(fp)['result']
    print(serializer.serialize(SystemDetails, system)['volumes'])
    print(content['volumes'])
    print(serializer.serialize(SystemDetails, system)['volumes'] == content['volumes'])


asyncio.get_event_loop().run_until_complete(run())
