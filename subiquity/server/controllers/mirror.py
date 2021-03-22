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
import pathlib
import tempfile
from typing import Optional
from xml.etree import ElementTree

from curtin.config import merge_config

import apt.progress.base
import apt.cache

import apt_pkg

import requests

from subiquitycore.async_helpers import (
    run_in_thread,
    SingleInstanceTask,
    )
from subiquitycore.context import with_context
from subiquitycore.lsb_release import lsb_release

from subiquity.common.apidef import API
from subiquity.server.controller import SubiquityController

log = logging.getLogger('subiquity.server.controllers.mirror')


class CheckState(enum.IntEnum):
    NOT_STARTED = enum.auto()
    CHECKING = enum.auto()
    FAILED = enum.auto()
    DONE = enum.auto()


class Progress(apt.progress.base.AcquireProgress):

    def __init__(self):
        super().__init__()
        self.failures = []

    def fail(self, item):
        super().fail(item)
        self.failures.append(item.owner.error_text)


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
        self._configured_apt = False
        self._good_mirrors = set()

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
        await self.check_url_GET(self.model.get_mirror())

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

    def configure_apt(self):
        if not self._configured_apt:
            apt_pkg.init_config()
            for key in apt_pkg.config.keys('Acquire::IndexTargets'):
                if key.count('::') == 3:
                    apt_pkg.config[f'{key}::DefaultEnabled'] = 'false'
            apt_pkg.config['Dir::Etc::sourceparts'] = '/dev/null'
            apt_pkg.config['Dir::Cache::pkgcache'] = ''
            apt_pkg.config['Dir::Cache::srcpkgcache'] = ''
            apt_pkg.init_system()
            self._configured_apt = True

    def _bg_update(self, cache, progress):
        try:
            cache.update(progress, raise_on_error=False)
        except apt.cache.FetchFailedException:
            pass

    async def check_url_GET(self, url: str) -> Optional[str]:
        if url in self._good_mirrors:
            return None
        await asyncio.sleep(5)
        self.configure_apt()
        with tempfile.TemporaryDirectory() as tdir:
            tdir = pathlib.Path(tdir)
            sources_list = tdir.joinpath('sources.list')
            lists = tdir.joinpath('lists')
            lists.joinpath('partial').mkdir(parents=True)
            with open(sources_list, 'w') as fp:
                fp.write("deb {url} {codename} main\n".format(
                    url=url, codename=lsb_release()['codename']))
            apt_pkg.config['Dir::Etc::sourcelist'] = str(sources_list)
            apt_pkg.config['Dir::State::lists'] = str(lists)
            cache = apt.cache.Cache()
            progress = Progress()
            await run_in_thread(self._bg_update, cache, progress)
        if progress.failures:
            msgs = []
            for msg in progress.failures:
                if msg not in msgs:
                    msgs.append(msg)
            return "\n".join(msgs)
        else:
            self._good_mirrors.add(url)
            return None
