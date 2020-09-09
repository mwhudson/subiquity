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

import logging
import platform

from collections import OrderedDict

from subiquitycore.utils import run_command

from subiquity.client.controller import SubiquityTuiController
from subiquity.common.types import ZdevInfo
from subiquity.ui.views import ZdevView


log = logging.getLogger("subiquitycore.controller.zdev")

lszdev_cmd = ['lszdev', '--pairs', '--columns',
              'id,type,on,exists,pers,auto,failed,names']


class ZdevController(SubiquityTuiController):

    endpoint_name = 'zdev'

    async def start_ui(self):
        if 'accept-default' in self.answers:
            self.done()
        zdev_infos = await self.endpoint.GET()
        await self.app.set_body(ZdevView(self, zdev_infos))

    def cancel(self):
        self.app.prev_screen()

    def done(self):
        # switch to next screen
        self.app.next_screen()

    async def chzdev(self, action, zdevinfo):
        return await self.endpoint.chzdev.POST(action, zdevinfo)

    def lszdev(self):
        devices = run_command(lszdev_cmd, universal_newlines=True).stdout
        devices = devices.splitlines()
        devices.sort()
        return [ZdevInfo.from_row(row) for row in devices]
