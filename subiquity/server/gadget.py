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
from typing import Optional

from subiquitycore import snapd

from subiquity.common.api.client import make_client
from subiquity.common.api.defs import api
from subiquity.common.serialize import Serializer

import attr


def named_field(name, default=attr.NOTHING):
    return attr.ib(metadata={'name': name}, default=default)


class Role(enum.Enum):

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
class VolumeStructure:
    name: str = ''
    label: str = named_field('filesystem-label', '')
    offset: Optional[int] = None
    offset_write: Optional[RelativeOffset] = None
    type: str = ''
    role: Optional[Role] = None
    id: Optional[str] = None
    filesystem: str = ''
    # content: List[VolumeContent] = attr.Factory(list)


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
        content = await snapd.get(path[1:], **params)
    else:
        1/0
    yield FakeResponse(content['result'])


@attr.s(auto_attribs=True)
class Snap:
    id: str


@api
class SnapdAPI:
    class v2:
        class snaps:
            class snap_name:
                __parameter__ = True
                def GET() -> Snap: ...


serializer = Serializer(ignore_missing_fields=True)


client = make_client(SnapdAPI, make_request, serializer=serializer)


async def run():
    print(await client.v2.snaps['go'].GET())


asyncio.get_event_loop().run_until_complete(run())
