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
from typing import List

from aiohttp import web

from subiquitycore.models.network import (
    DHCPState,
    NetDevInfo,
    StaticConfig,
    VLANConfig,
    BondConfig,
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
        if act == LinkAction.CHANGE:
            self.view.update_link(info)

    async def route_watch_POST(self, routes: List[int]) -> None: ...

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

    def set_static_config(self, dev_info: NetDevInfo, ip_version: int,
                          static_config: StaticConfig) -> None:
        #setattr(dev_info, 'static' + str(ip_version), static_config)
        #getattr(dev_info, 'dhcp' + str(ip_version)).enabled = False

        self.app.aio_loop.create_task(
            self.endpoint.set_static_config.POST(
                dev_info, ip_version, static_config))

    def enable_dhcp(self, dev_info: NetDevInfo, ip_version: int) -> None:
        setattr(dev_info, 'static' + str(ip_version), StaticConfig())
        getattr(dev_info, 'dhcp' + str(ip_version)).enabled = True
        getattr(dev_info, 'dhcp' + str(ip_version)).state = DHCPState.PENDING

        self.app.aio_loop.create_task(
            self.endpoint.enable_dhcp.POST(dev_info, ip_version))

    def disable_network(self, dev_info: NetDevInfo, ip_version: int) -> None:
        setattr(dev_info, 'static' + str(ip_version), StaticConfig())
        getattr(dev_info, 'dhcp' + str(ip_version)).enabled = False

        self.app.aio_loop.create_task(
            self.endpoint.disable.POST(dev_info, ip_version))

    def add_vlan(self, dev_info: NetDevInfo, vlan_config: VLANConfig):
        new = self.model.new_vlan(dev_info.name, vlan_config)
        dev = self.model.get_netdev_by_name(dev_info.name)
        self.update_link(dev)
        self.apply_config()
        return new.netdev_info()

    def delete_link(self, dev_info: NetDevInfo):
        touched_devices = set()
        if dev_info.type == "bond":
            for device_name in dev_info.bond.interfaces:
                interface = self.model.get_netdev_by_name(device_name)
                touched_devices.add(interface)
        elif dev_info.type == "vlan":
            link = self.model.get_netdev_by_name(dev_info.vlan.link)
            touched_devices.add(link)
        dev_info.has_config = False

        device = self.model.get_netdev_by_name(dev_info.name)
        self.del_link(device)
        device.config = None
        for dev in touched_devices:
            self.update_link(dev)
        self.apply_config()

    def add_or_update_bond(self, existing_name: NetDevInfo, new_name: str,
                           new_info: BondConfig) -> None:
        get_netdev_by_name = self.model.get_netdev_by_name
        touched_devices = set()
        for device_name in new_info.interfaces:
            device = get_netdev_by_name(device_name)
            device.config = {}
            touched_devices.add(device)
        if existing_name is None:
            new_dev = self.model.new_bond(new_name, new_info)
            self.new_link(new_dev)
        else:
            existing = get_netdev_by_name(existing_name)
            for interface in existing.config['interfaces']:
                touched_devices.add(get_netdev_by_name(interface))
            existing.config.update(new_info.to_config())
            if existing.name != new_name:
                config = existing.config
                existing.config = None
                self.del_link(existing)
                existing.config = config
                existing.name = new_name
                self.new_link(existing)
            else:
                touched_devices.add(existing)
        self.apply_config()
        for dev in touched_devices:
            self.update_link(dev)

    async def get_info_for_netdev(self, dev_info: NetDevInfo) -> str:
        return await self.endpoint.info.GET(dev_info.name)
