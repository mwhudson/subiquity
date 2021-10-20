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
import logging

from curtin.config import merge_config
from curtin.util import sanitize_source

from subiquitycore.context import with_context

from subiquity.common.apidef import API
from subiquity.common.types import (
    MirrorCheckState,
    MirrorCheckStatus,
    MirrorState,
    )
from subiquity.server.apt_fetcher import DryRunMirrorChecker
from subiquity.server.controller import SubiquityController
from subiquity.server.types import InstallerChannels

log = logging.getLogger('subiquity.server.controllers.mirror')


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
            },
        }
    model_name = "mirror"

    def __init__(self, app):
        super().__init__(app)
        self.geoip_enabled = True
        self.app.hub.subscribe(InstallerChannels.GEOIP, self.on_geoip)
        self.app.hub.subscribe(
            (InstallerChannels.CONFIGURED, 'source'), self.on_source)
        self.on_source()
        self.cc_event = asyncio.Event()
        self.checker = None

    def load_autoinstall_data(self, data):
        if data is None:
            return
        geoip = data.pop('geoip', True)
        merge_config(self.model.config, data)
        self.geoip_enabled = geoip and self.model.is_default()

    @with_context()
    async def apply_autoinstall_config(self, context):
        if not self.geoip_enabled:
            return
        try:
            with context.child('waiting'):
                await asyncio.wait_for(self.cc_event.wait(), 10)
        except asyncio.TimeoutError:
            pass

    def on_geoip(self):
        if self.geoip_enabled:
            self.model.set_country(self.app.geoip.countrycode)
        self.cc_event.set()
        self.maybe_start_check(self.model.render())

    def on_source(self):
        self.source = sanitize_source(self.app.base_model.source.source_uri())

    def maybe_start_check(self, apt_config):
        if self.checker is not None and self.checker.apt_config == apt_config:
            return
        self.checker = DryRunMirrorChecker({'uri': 'cp:///'}, apt_config)
        self.app.aio_loop.create_task(self.checker.check(context=self.context))

    def serialize(self):
        return self.model.get_mirror()

    def deserialize(self, data):
        self.model.set_mirror(data)

    def make_autoinstall(self):
        r = self.model.render()['apt']
        r['geoip'] = self.geoip_enabled
        return r

    def configured(self):
        return super().configured()

    async def GET(self) -> MirrorState:
        return MirrorState(
            self.model.get_mirror(),
            await self.check_GET())

    async def POST(self, data: str):
        self.model.set_mirror(data)
        await self.configured()

    async def check_POST(self, url: str):
        apt_config = self.model.config_for_mirror(url)
        # XXX Do we have network!!
        self.maybe_start_check(apt_config)

    async def check_GET(self) -> MirrorCheckState:
        if self.checker is not None:
            return self.checker.state()
        else:
            return MirrorCheckState(
                MirrorCheckStatus.NOT_STARTED, output='')
