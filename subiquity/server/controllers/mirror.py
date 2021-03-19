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
import enum
import logging
import os
import subprocess
import tempfile
from typing import Optional
from xml.etree import ElementTree

from curtin.config import merge_config

import apt_pkg

import requests

from subiquitycore.async_helpers import (
    run_in_thread,
    SingleInstanceTask,
    )
from subiquitycore.context import with_context
from subiquitycore.lsb_release import lsb_release
from subiquitycore.utils import arun_command

from subiquity.common.apidef import API
from subiquity.server.controller import SubiquityController

log = logging.getLogger('subiquity.server.controllers.mirror')


class CheckState(enum.IntEnum):
    NOT_STARTED = enum.auto()
    CHECKING = enum.auto()
    FAILED = enum.auto()
    DONE = enum.auto()


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
    signals = [
        ('snapd-network-change', 'snapd_network_changed'),
    ]

    def __init__(self, app):
        super().__init__(app)
        self.geoip_enabled = True
        self.check_state = CheckState.NOT_STARTED
        self.lookup_task = SingleInstanceTask(self.lookup)
        self._apt_options_for_checking = None

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
        if self.lookup_task.task is None:
            return
        try:
            with context.child('waiting'):
                await asyncio.wait_for(self.lookup_task.wait(), 10)
        except asyncio.TimeoutError:
            pass

    def snapd_network_changed(self):
        if not self.geoip_enabled:
            return
        if self.check_state != CheckState.DONE:
            self.check_state = CheckState.CHECKING
            self.lookup_task.start_sync()

    @with_context()
    async def lookup(self, context):
        try:
            response = await run_in_thread(
                requests.get, "https://geoip.ubuntu.com/lookup")
            response.raise_for_status()
        except requests.exceptions.RequestException:
            log.exception("geoip lookup failed")
            self.check_state = CheckState.FAILED
            return
        try:
            e = ElementTree.fromstring(response.text)
        except ElementTree.ParseError:
            log.exception("parsing %r failed", response.text)
            self.check_state = CheckState.FAILED
            return
        cc = e.find("CountryCode")
        if cc is None:
            log.debug("no CountryCode found in %r", response.text)
            self.check_state = CheckState.FAILED
            return
        cc = cc.text.lower()
        if len(cc) != 2:
            log.debug("bogus CountryCode found in %r", response.text)
            self.check_state = CheckState.FAILED
            return
        self.check_state = CheckState.DONE
        self.model.set_country(cc)

    def serialize(self):
        return self.model.get_mirror()

    def deserialize(self, data):
        self.model.set_mirror(data)

    def make_autoinstall(self):
        r = self.model.render()['apt']
        r['geoip'] = self.geoip_enabled
        return r

    async def GET(self) -> str:
        return self.model.get_mirror()

    async def POST(self, data: str):
        self.model.set_mirror(data)
        self.configured()

    def apt_options_for_checking(self):
        if self._apt_options_for_checking is None:
            apt_pkg.init_config()
            opts = []
            for key in apt_pkg.config.keys('Acquire::IndexTargets'):
                if key.endswith('::DefaultEnabled'):
                    opts.append(f'-o{key}=false')
            self._apt_options_for_checking = opts
        return self._apt_options_for_checking

    async def check_url_GET(self, url: str) -> Optional[str]:
        with tempfile.TemporaryDirectory() as tdir:
            sources_list = os.path.join(tdir, 'sources.list')
            with open(sources_list, 'w') as fp:
                fp.write("deb {} {} main\n".format(
                    url, lsb_release()['codename']))
            apt_cmd = [
                'apt-get',
                'update',
                f'-oDir::Etc::sourcelist={sources_list}',
                '-oDir::Etc::sourceparts=/dev/null',
                ] + self.apt_options_for_checking()
            cp = await arun_command(apt_cmd)
            if cp.returncode == 0:
                return None
            else:
                return cp.stderr
