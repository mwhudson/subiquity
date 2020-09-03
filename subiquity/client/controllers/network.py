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

import logging
import os
import shutil
import tempfile
from typing import List, Optional

from aiohttp import web

from subiquitycore.models.network import (
    BondConfig,
    NetDevInfo,
    StaticConfig,
    )

from subiquitycore.ui.views.network import NetworkView

from subiquity.client.controller import SubiquityTuiController
from subiquity.common.api.definition import LinkAction, NetEventAPI
from subiquity.common.api.server import bind

log = logging.getLogger('subiquity.client.controllers.network')


class NetworkController(SubiquityTuiController):

    endpoint_name = 'network'

    def __init__(self, app):
        super().__init__(app)
        self.view = None

    def generic_result(self):
        return {}

    async def update_link_POST(self, act: LinkAction,
                               info: NetDevInfo) -> None:
        if self.view is None:
            return
        if act == LinkAction.NEW:
            self.view.new_link(info)
        if act == LinkAction.CHANGE:
            self.view.update_link(info)
        if act == LinkAction.DEL:
            self.view.del_link(info)

    async def route_watch_POST(self, routes: List[int]) -> None:
        if self.view is not None:
            self.view.update_default_routes(routes)

    async def apply_starting_POST(self) -> None: ...

    async def apply_stopping_POST(self) -> None: ...

    async def apply_error_POST(self, stage: str) -> None: ...

    async def subscribe(self):
        self.tdir = tempfile.mkdtemp()
        self.sock_path = os.path.join(self.tdir, 'socket')
        app = web.Application()
        bind(app.router, NetEventAPI, self)
        runner = web.AppRunner(app)
        await runner.setup()
        self.site = web.UnixSite(runner, self.sock_path)
        await self.site.start()
        await self.endpoint.subscription.PUT(self.sock_path)

    async def unsubscribe(self):
        await self.endpoint.subscription.DELETE(self.sock_path)
        await self.site.stop()
        shutil.rmtree(self.tdir)

    async def start_ui(self):
        netdev_infos = await self.endpoint.GET()
        self.view = NetworkView(self, netdev_infos)
        await self.subscribe()
        await self.app.set_body(self.view)

    def end_ui(self):
        self.view = None
        self.app.aio_loop.create_task(self.unsubscribe())

    def cancel(self):
        self.app.prev_screen()

    def done(self):
        self.app.next_screen(self.endpoint.POST())

    def set_static_config(self, dev_name: str, ip_version: int,
                          static_config: StaticConfig) -> None:
        self.app.aio_loop.create_task(
            self.endpoint.set_static_config.POST(
                dev_name, ip_version, static_config))

    def enable_dhcp(self, dev_name, ip_version: int) -> None:
        self.app.aio_loop.create_task(
            self.endpoint.enable_dhcp.POST(dev_name, ip_version))

    def disable_network(self, dev_name: str, ip_version: int) -> None:
        self.app.aio_loop.create_task(
            self.endpoint.disable.POST(dev_name, ip_version))

    def add_vlan(self, dev_name: str, vlan_id: int):
        self.app.aio_loop.create_task(
            self.endpoint.vlan.PUT(dev_name, vlan_id))

    def delete_link(self, dev_name: str):
        self.app.aio_loop.create_task(self.endpoint.delete.POST(dev_name))

    def add_or_update_bond(self, existing_name: Optional[str],
                           new_name: str, new_info: BondConfig) -> None:
        self.app.aio_loop.create_task(
            self.endpoint.add_or_edit_bond.POST(
                existing_name, new_name, new_info))

    async def get_info_for_netdev(self, dev_name: str) -> str:
        return await self.endpoint.info.GET(dev_name)
