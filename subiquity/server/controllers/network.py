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

import asyncio
import contextlib
import logging
from typing import List, Optional

import aiohttp

from subiquitycore.async_helpers import schedule_task
from subiquitycore.context import with_context
from subiquitycore.controllers.network import BaseNetworkController
from subiquitycore.models.network import (
    BondConfig,
    NetDevInfo,
    StaticConfig,
    )

from subiquity.common.api.client import make_client
from subiquity.common.api.definition import (
    API,
    LinkAction,
    NetEventAPI,
    )
from subiquity.common.errorreport import ErrorReportKind
from subiquity.server.controller import SubiquityController


log = logging.getLogger("subiquity.controllers.network")

MATCH = {
    'type': 'object',
    'properties': {
        'name': {'type': 'string'},
        'macaddress': {'type': 'string'},
        'driver': {'type': 'string'},
        },
    'additionalProperties': False,
    }

NETPLAN_SCHEMA = {
    'type': 'object',
    'properties': {
        'version': {
            'type': 'integer',
            'minimum': 2,
            'maximum': 2,
            },
        'ethernets': {
            'type': 'object',
            'properties': {
                'match': MATCH,
                }
            },
        'wifis': {
            'type': 'object',
            'properties': {
                'match': MATCH,
                }
            },
        'bridges': {'type': 'object'},
        'bonds': {'type': 'object'},
        'tunnels': {'type': 'object'},
        'vlans': {'type': 'object'},
        },
    'required': ['version'],
    }


class EventClient:

    def __init__(self, socket_path):
        self.conn = aiohttp.UnixConnector(path=socket_path)
        self.client = make_client(NetEventAPI, self.make_request)

    @contextlib.asynccontextmanager
    async def session(self):
        async with aiohttp.ClientSession(
                connector=self.conn, connector_owner=False) as session:
            yield session

    async def make_request(self, method, path, *, params, json):
        async with self.session() as session:
            async with session.request(
                    method, 'http://a' + path, json=json,
                    params=params, timeout=0) as response:
                return await response.json()


class NetworkController(BaseNetworkController, SubiquityController):

    endpoint = API.network

    ai_data = None
    autoinstall_key = "network"
    autoinstall_schema = {
        'oneOf': [
            NETPLAN_SCHEMA,
            {
                'type': 'object',
                'properties': {
                    'network': NETPLAN_SCHEMA,
                    },
                'required': ['network'],
            },
            ],
        }

    def __init__(self, app):
        super().__init__(app)
        app.note_file_for_apport("NetplanConfig", self.netplan_path)
        self.view_shown = False
        self.clients = {}

    def load_autoinstall_data(self, data):
        if data is not None:
            self.ai_data = data
            # The version included with 20.04 accidentally required
            # that you put:
            #
            # network:
            #   network:
            #     version: 2
            #
            # in your autoinstall config. Continue to support that for
            # backwards compatibility.
            if 'network' in self.ai_data:
                self.ai_data = self.ai_data['network']

    def start(self):
        if self.ai_data is not None:
            self.model.override_config = {'network': self.ai_data}
            self.apply_config()
            if self.interactive():
                # If interactive, we want edits in the UI to override
                # the provided config. If not, we just splat the
                # autoinstall config onto the target system.
                schedule_task(self.unset_override_config())
        elif not self.interactive():
            self.initial_config = schedule_task(self.wait_for_initial_config())
        super().start()

    async def unset_override_config(self):
        await self.apply_config_task.wait()
        self.model.override_config = None

    @with_context()
    async def wait_for_initial_config(self, context):
        # In interactive mode, we disable all nics that haven't got an
        # address by the time we get to the network screen. But in
        # non-interactive mode we might get to that screen much faster
        # so we wait for up to 10 seconds for any device configured
        # to use dhcp to get an address.
        dhcp_events = set()
        for dev in self.model.get_all_netdevs(include_deleted=True):
            dev.dhcp_events = {}
            for v in 4, 6:
                if dev.dhcp_enabled(v) and not dev.dhcp_addresses()[v]:
                    dev.dhcp_events[v] = e = asyncio.Event()
                    dhcp_events.add(e)
        if not dhcp_events:
            return

        with context.child("wait_dhcp"):
            try:
                await asyncio.wait_for(
                    asyncio.wait({e.wait() for e in dhcp_events}),
                    10)
            except asyncio.TimeoutError:
                pass

    @with_context()
    async def apply_autoinstall_config(self, context):
        if self.ai_data is None:
            with context.child("wait_initial_config"):
                await self.initial_config
            self.update_initial_configs()
            self.apply_config(context)
        with context.child("wait_for_apply"):
            await self.apply_config_task.wait()
        self.model.has_network = bool(
            self.network_event_receiver.default_routes)

    async def _apply_config(self, *, context=None, silent=False):
        try:
            await super()._apply_config(context=context, silent=silent)
        except asyncio.CancelledError:
            # asyncio.CancelledError is a subclass of Exception in
            # Python 3.6 (sadface)
            raise
        except Exception:
            log.exception("_apply_config failed")
            self.model.has_network = False
            self.app.make_apport_report(
                ErrorReportKind.NETWORK_FAIL, "applying network",
                interrupt=True)
            if not self.interactive():
                raise

    def make_autoinstall(self):
        return self.model.render_config()['network']

    async def GET(self) -> List[NetDevInfo]:
        if not self.view_shown:
            self.apply_config(silent=True)
            self.view_shown = True
        return [
            netdev.netdev_info() for netdev in self.model.get_all_netdevs()
            ]

    async def POST(self) -> None:
        self.model.has_network = bool(
            self.network_event_receiver.default_routes)
        self.configured()

    async def subscription_PUT(self, socket_path: str) -> None:
        log.debug('added subscription %s', socket_path)
        client = EventClient(socket_path).client
        self.clients[socket_path] = client
        self.app.aio_loop.create_task(
            client.route_watch.POST(
                self.network_event_receiver.default_routes))

    async def subscription_DELETE(self, socket_path: str) -> None:
        log.debug('removed subscription %s', socket_path)
        del self.clients[socket_path]

    def apply_starting(self):
        super().apply_starting()
        for v in self.clients.values():
            self.app.aio_loop.create_task(v.apply_starting.POST())

    def apply_stopping(self):
        super().apply_stopping()
        for v in self.clients.values():
            self.app.aio_loop.create_task(v.apply_stopping.POST())

    def apply_error(self, stage):
        super().apply_error()
        for v in self.clients.values():
            self.app.aio_loop.create_task(v.apply_error.POST(stage))

    def update_default_routes(self, routes):
        super().update_default_routes(routes)
        for v in self.clients.values():
            self.app.aio_loop.create_task(v.route_watch.POST(routes))

    def _send_update(self, act, dev):
        dev_info = dev.netdev_info()
        for k, v in self.clients.items():
            log.debug('sending update to %s', k)
            self.app.aio_loop.create_task(v.update_link.POST(act, dev_info))

    def new_link(self, dev):
        super().new_link(dev)
        self._send_update(LinkAction.NEW, dev)

    def update_link(self, dev):
        super().update_link(dev)
        self._send_update(LinkAction.CHANGE, dev)

    def del_link(self, dev):
        super().del_link(dev)
        self._send_update(LinkAction.DEL, dev)

    async def set_static_config_POST(self, dev_name: str, ip_version: int,
                                     static_config: StaticConfig) -> None:
        self.set_static_config(dev_name, ip_version, static_config)

    async def enable_dhcp_POST(self, dev_name: str, ip_version: int) -> None:
        self.enable_dhcp(dev_name, ip_version)

    async def disable_POST(self, dev_name: str, ip_version: int) -> None:
        self.disable_network(dev_name, ip_version)

    async def vlan_PUT(self, dev_name: str, vlan_id: int) -> None:
        self.add_vlan(dev_name, vlan_id)

    async def add_or_edit_bond_POST(self, existing_name: Optional[str],
                                    new_name: str,
                                    bond_config: BondConfig) -> None:
        self.add_or_update_bond(existing_name, new_name, bond_config)

    async def delete_POST(self, dev_name: str) -> None:
        self.delete_link(dev_name)

    async def info_GET(self, dev_name: str) -> str:
        return self.get_info_for_netdev(dev_name)
