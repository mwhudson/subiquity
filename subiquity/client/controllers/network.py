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
import logging

import yaml

from subiquitycore.context import with_context
from subiquitycore.controllers.network import NetworkController
from subiquitycore import netplan
from subiquitycore.models.network import NetworkModel
from subiquitycore.ui.views.network import NetworkView

from subiquity.client.controller import SubiquityTuiController

log = logging.getLogger("subiquity.client.controllers.network")


class NetworkController(SubiquityTuiController, NetworkController):

    model_name = None
    endpoint = '/network'

    def __init__(self, app):
        self.model = NetworkModel("subiquity-client", False)
        self.model.config = netplan.Config()
        super().__init__(app)

    async def _start_ui(self, status):
        self.model.config.parse_netplan_config(yaml.dump(status))
        for netdev in self.model.get_all_netdevs(include_deleted=True):
            netdev.config = self.model.config.config_for_device(netdev)
            if netdev.config is None and netdev.info is None:
                del self.model.devices_by_name[netdev.name]
        self.view = NetworkView(self.model, self)
        if not self.view_shown:
            self.apply_config(silent=True)
            self.view_shown = True
        self.network_event_receiver.view = self.view
        await self.app.set_body(self.view)

    def cancel(self):
        self.app.prev_screen()

    @with_context(
        name="apply_config", description="silent={silent}", level="INFO")
    async def _apply_config(self, *, context, silent):
        dhcp_device_versions = []
        dhcp_events = set()
        for dev in self.model.get_all_netdevs():
            dev.dhcp_events = {}
            for v in 4, 6:
                if dev.dhcp_enabled(v):
                    if not silent:
                        dev.set_dhcp_state(v, "PENDING")
                        self.network_event_receiver.update_link(
                            dev.ifindex)
                    else:
                        dev.set_dhcp_state(v, "RECONFIGURE")
                    dev.dhcp_events[v] = e = asyncio.Event()
                    dhcp_events.add(e)

        if not silent and self.view:
            self.view.show_apply_spinner()

        try:
            await self.post(self.model.render_config())
        finally:
            if not silent and self.view:
                self.view.hide_apply_spinner()

        if self.answers.get('accept-default', False):
            self.done()
        elif self.answers.get('actions', False):
            actions = self.answers['actions']
            self.answers.clear()
            self._run_iterator(self._run_actions(actions))

        if not dhcp_events:
            return

        try:
            await asyncio.wait_for(
                asyncio.wait({e.wait() for e in dhcp_events}),
                10)
        except asyncio.TimeoutError:
            pass

        for dev, v in dhcp_device_versions:
            dev.dhcp_events = {}
            if not dev.dhcp_addresses()[v]:
                dev.set_dhcp_state(v, "TIMEDOUT")
                self.network_event_receiver.update_link(dev.ifindex)
