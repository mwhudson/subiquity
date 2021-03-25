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
import attr
import enum
import logging
import pathlib
import shutil
import subprocess
import tempfile
from typing import Any
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
from subiquitycore.utils import (
    astart_command,
    )

from subiquity.common.apidef import API
from subiquity.common.types import MirrorCheck
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
        self._checks = {}
        self._check_id = 0

    def load_autoinstall_data(self, data):
        if data is None:
            return
        geoip = data.pop('geoip', True)
        merge_config(self.model.config, data)
        self.geoip_enabled = geoip and self.model.is_default()

    @with_context()
    async def apply_autoinstall_config(self, context):
        if self.geoip_enabled:
            if self.lookup_task.task is None:
                return
            try:
                with context.child('waiting'):
                    await asyncio.wait_for(self.lookup_task.wait(), 10)
            except asyncio.TimeoutError:
                pass
        msg = await self.check_url(
            context=context, url=self.model.get_mirror())
        if msg:
            raise Exception("apt mirror could not be used: " + msg)

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
        #if self.interactive():
        #    await self.check_url(
        #        context=context, url=self.model.get_mirror(), force_new=True)

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
            opts = [
                '-oDir::Etc::sourceparts=/dev/null',
                '-oDir::Cache::pkgcache=',
                '-oDir::Cache::srcpkgcache=',
                '-oAPT::Update::Error-Mode=any',
                ]
            apt_pkg.init_config()
            for key in apt_pkg.config.keys('Acquire::IndexTargets'):
                if key.count('::') == 3:
                    opts.append(f'-o{key}::DefaultEnabled=false')
            self._apt_options_for_checking = opts
        return self._apt_options_for_checking

    async def _start_check(self, url):
        id = str(self._check_id)
        self._check_id += 1

        self._checks[id] = check = MirrorCheck(id=id)

        tdir = tempfile.mkdtemp()
        tdir = pathlib.Path(tdir)
        sources_list = tdir.joinpath('sources.list')
        lists = tdir.joinpath('lists')
        lists.joinpath('partial').mkdir(parents=True)
        with open(sources_list, 'w') as fp:
            fp.write("deb {url} {codename} main\n".format(
                url=url, codename=lsb_release()['codename']))
        apt_cmd = [
            'apt-get',
            'update',
            f'-oDir::Etc::sourcelist={sources_list}',
            f'-oDir::State::lists={lists}',
            ] + self.apt_options_for_checking()
        proc = await astart_command(
            apt_cmd, stderr=subprocess.STDOUT)

        async def _reader():
            while not proc.stdout.at_eof():
                try:
                    line = await proc.stdout.readuntil(b'\n')
                except asyncio.IncompleteReadError as e:
                    line = e.partial
                    if not line:
                        return
                check.output.append(line.decode('utf-8'))

        async def _waiter():
            rc = await proc.wait()
            shutil.rmtree(tdir)
            await reader
            if rc == 0:
                for line in check.output:
                    if line.startswith('Err:'):
                        rc = 1
            check.in_progress = False
            check.success = rc == 0

        reader = self.app.aio_loop.create_task(_reader())
        self.app.aio_loop.create_task(_waiter())

        return check

    async def start_check_GET(self, url: str) -> MirrorCheck:
        return await self._start_check(url)

    async def get_check_status_GET(self, id: str) -> MirrorCheck:
        return self._checks[id]
