# Copyright 2018 Canonical, Ltd.
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

import logging

import attr

from subiquitycore.tuicontroller import (
    Skip,
    )

from subiquity.client.controller import (
    SubiquityTuiController,
    )

from subiquity.models.snaplist import (
    SnapInfo,
    SnapInfoList,
    SnapSelection,
    SnapSelectionDict,
    )
from subiquity.ui.views.snaplist import SnapListView

log = logging.getLogger('subiquity.controllers.snaplist')


@attr.s
class SnapListResponse:
    status = attr.ib()
    snaps = attr.ib()
    to_install = attr.ib()

    @classmethod
    def deserialize(cls, data):
        return cls(
            status=data['status'],
            snaps=SnapInfoList.deserialize(data.get('snaps', [])),
            to_install=SnapSelectionDict.deserialize(
                data.get('to_install', {})))


class SnapListController(SubiquityTuiController):

    endpoint = '/snaplist'

    async def _start_ui(self, data):
        data = SnapListResponse.deserialize(data)
        if data.status == 'failed':
            raise Skip()
        if 'snaps' in self.answers:
            to_install = {}
            for snap_name, selection in self.answers['snaps'].items():
                to_install[snap_name] = SnapSelection(**selection)
            self.done(to_install)
            return
        await self.app.set_body(SnapListView(self, data))

    def done(self, snaps_to_install):
        log.debug(
            "SnapListController.done next_screen snaps_to_install=%s",
            snaps_to_install)
        self.app.next_screen(self.post(snaps_to_install.serialize()))

    def cancel(self, sender=None):
        self.app.prev_screen()

    async def get_list_wait(self):
        return SnapListResponse.deserialize(
            await self.app.get('/snaplist/wait'))

    async def get_info(self, snap):
        if not snap.channels:
            data = await self.app.get('/snaplist/info/' + snap.name)
            snap.channels = SnapInfo.deserialize(data).channels
