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

import asyncio
import copy
import logging
from typing import List

from curtin.config import merge_config

from subiquitycore.async_helpers import SingleInstanceTask
from subiquitycore.context import with_context

from subiquity.common.apidef import API
from subiquity.common.types import (
    MirrorCheckState,
    MirrorCheckStatus,
    MirrorState,
    )
from subiquity.server.apt import get_apt_configurer
from subiquity.server.controller import SubiquityController
from subiquity.server.types import InstallerChannels

log = logging.getLogger('subiquity.server.controllers.mirror')


class MirrorChecker:

    def __init__(self, apt_configurer):
        self.apt_configurer = apt_configurer
        self.status = MirrorCheckStatus.RUNNING
        self.output = []

    async def check(self):
        rc = await self.apt_configurer.check(self.output)
        if rc == 0:
            self.status = MirrorCheckStatus.PASSED
        else:
            self.status = MirrorCheckStatus.FAILED

    def state(self):
        return MirrorCheckState(self.status, '\n'.join(self.output))


class MirrorController(SubiquityController):

    endpoint = API.mirror

    autoinstall_key = "apt"
    autoinstall_schema = {  # This is obviously incomplete.
        'type': 'object',
        'properties': {
            'preserve_sources_list': {'type': 'boolean'},
            'primary': {'type': 'array'},
            'geoip':  {'type': 'boolean'},
            'sources': {'type': 'object'},
            'disable_components': {
                'type': 'array',
                'items': {
                    'type': 'string',
                    'enum': ['universe', 'multiverse', 'restricted',
                             'contrib', 'non-free']
                }
            }
        }
    }
    model_name = "mirror"

    def __init__(self, app):
        super().__init__(app)
        self.geoip_enabled = True
        self.app.hub.subscribe(InstallerChannels.GEOIP, self.on_geoip)
        self.app.hub.subscribe(
            (InstallerChannels.CONFIGURED, 'source'), self.on_source)
        self.cc_event = asyncio.Event()
        self.apt_configurer = None
        self.checkers = {}

    def load_autoinstall_data(self, data):
        if data is None:
            return
        geoip = data.pop('geoip', True)
        merge_config(self.model.config, data)
        self.geoip_enabled = geoip and self.model.mirror_is_default()

    @with_context()
    async def apply_autoinstall_config(self, context):
        if not self.geoip_enabled:
            return
        try:
            with context.child('waiting'):
                await asyncio.wait_for(self.cc_event.wait(), 10)
        except asyncio.TimeoutError:
            pass
        self.apt_configurer = self.make_apt_configurer(
            self.model.get_config())

    def on_geoip(self):
        if self.geoip_enabled:
            self.model.set_country(self.app.geoip.countrycode)
        self.cc_event.set()

    def on_source(self):
        self.checkers = {}

    def serialize(self):
        return self.model.get_mirror()

    def deserialize(self, data):
        self.model.set_mirror(data)

    def make_autoinstall(self):
        r = copy.deepcopy(self.model.config)
        r['geoip'] = self.geoip_enabled
        return r

    def maybe_start_check(self, url, apt_config, retry=False):
        if url in self.checkers and not retry:
            return
        configurer = self.make_apt_configurer(apt_config)
        checker = self.checkers[url] = MirrorChecker(configurer)
        asyncio.create_task(checker.check())

    def make_apt_configurer(self, config):
        return get_apt_configurer(
            self.app,
            self.context,
            self.app.controllers.Source.source_path,
            config)

    async def GET(self) -> MirrorState:
        return MirrorState(
            mirror=self.model.get_mirror(),
            check_state=MirrorCheckState(
                status=MirrorCheckStatus.NO_NETWORK, output=''))

    async def POST(self, data: str):
        self.model.set_mirror(data)
        if data in self.checkers:
            self.apt_configurer = self.checkers[data].apt_configurer
        else:
            self.apt_configurer = self.make_apt_configurer(
                self.model.get_config())
        await self.configured()

    async def disable_components_GET(self) -> List[str]:
        return list(self.model.disable_components)

    async def disable_components_POST(self, data: List[str]):
        self.model.disable_components = set(data)

    async def check_POST(self, url: str, retry: bool = False) \
            -> MirrorCheckState:
        if self.app.base_model.network.has_network:
            apt_config = self.model.config_for_mirror(url)
            self.maybe_start_check(url, apt_config, retry)
        return await self.check_GET(url)

    async def check_GET(self, url: str) -> MirrorCheckState:
        if not self.app.base_model.network.has_network:
            return MirrorCheckState(
                MirrorCheckStatus.NO_NETWORK, output='')
        checker = self.checkers.get(url)
        if checker is not None:
            return checker.state()
        return MirrorCheckState(
            MirrorCheckStatus.RUNNING, output='')
