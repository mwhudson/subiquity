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

import asyncio
import logging
import os
import shutil
import tempfile
from typing import List, Optional

from subiquitycore.models.network import (
    BondConfig,
    NetDevAction,
    NetDevInfo,
    StaticConfig,
    )
from subiquitycore.ui.stretchy import StretchyOverlay
from subiquitycore.ui.views.network import NetworkView

from subiquity.client.controller import SubiquityTuiController
from subiquity.common.api.server import make_server_at_path
from subiquity.common.apidef import LinkAction, NetEventAPI

log = logging.getLogger('subiquity.client.controllers.network')


class NetworkController(SubiquityTuiController):

    endpoint_name = 'network'

    def __init__(self, app):
        super().__init__(app)
        self.view = None

    def _action_get(self, id):
        dev_spec = id[0].split()
        if dev_spec[0] == "interface":
            if dev_spec[1] == "index":
                name = self.view.cur_netdev_names[int(dev_spec[2])]
            elif dev_spec[1] == "name":
                name = dev_spec[2]
            return self.view.dev_name_to_table[name]
        raise Exception("could not resolve {}".format(id))

    def _action_clean_interfaces(self, devices):
        r = [self._action_get(device).dev_info.name for device in devices]
        log.debug("%s", r)
        return r

    async def _answers_action(self, action):
        log.debug("_answers_action %r", action)
        if 'obj' in action:
            table = self._action_get(action['obj'])
            meth = getattr(
                self.ui.body,
                "_action_{}".format(action['action']))
            action_obj = getattr(NetDevAction, action['action'])
            self.ui.body._action(None, (action_obj, meth), table)
            yield
            body = self.ui.body._w
            if action['action'] == "DELETE":
                t = 0.0
                while table.dev_info.name in self.view.cur_netdev_names:
                    await asyncio.sleep(0.1)
                    t += 0.1
                    if t > 5.0:
                        raise Exception(
                            "interface did not disappear in 5 secs")
                log.debug("waited %s for interface to disappear", t)
            if not isinstance(body, StretchyOverlay):
                return
            for k, v in action.items():
                if not k.endswith('data'):
                    continue
                form_name = "form"
                submit_key = "submit"
                if '-' in k:
                    prefix = k.split('-')[0]
                    form_name = prefix + "_form"
                    submit_key = prefix + "-submit"
                async for _ in self._enter_form_data(
                        getattr(body.stretchy, form_name),
                        v,
                        action.get(submit_key, True)):
                    pass
        elif action['action'] == 'create-bond':
            self.ui.body._create_bond()
            yield
            body = self.ui.body._w
            data = action['data'].copy()
            if 'devices' in data:
                data['interfaces'] = data.pop('devices')
            async for _ in self._enter_form_data(
                    body.stretchy.form,
                    data,
                    action.get("submit", True)):
                pass
            t = 0.0
            while data['name'] not in self.view.cur_netdev_names:
                await asyncio.sleep(0.1)
                t += 0.1
                if t > 5.0:
                    raise Exception("bond did not appear in 5 secs")
            if t > 0:
                log.debug("waited %s for bond to appear", t)
            yield
        elif action['action'] == 'done':
            self.ui.body.done()
        else:
            raise Exception("could not process action {}".format(action))

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

    async def apply_starting_POST(self) -> None:
        if self.view is not None:
            self.view.show_apply_spinner()

    async def apply_stopping_POST(self) -> None:
        if self.view is not None:
            self.view.hide_apply_spinner()

    async def apply_error_POST(self, stage: str) -> None:
        if self.view is not None:
            self.view.show_network_error(stage)

    async def subscribe(self):
        self.tdir = tempfile.mkdtemp()
        self.sock_path = os.path.join(self.tdir, 'socket')
        self.site = await make_server_at_path(
            self.sock_path, NetEventAPI, self)
        await self.endpoint.subscription.PUT(self.sock_path)

    async def unsubscribe(self):
        await self.endpoint.subscription.DELETE(self.sock_path)
        await self.site.stop()
        shutil.rmtree(self.tdir)

    async def make_ui(self):
        netdev_infos = await self.endpoint.GET()
        self.view = NetworkView(self, netdev_infos)
        await self.subscribe()
        return self.view

    def run_answers(self):
        if self.answers.get('accept-default', False):
            self.done()
        elif self.answers.get('actions', False):
            actions = self.answers['actions']
            self.answers.clear()
            self.app.aio_loop.create_task(
                self._run_actions(actions))

    def end_ui(self):
        if self.view is not None:
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
