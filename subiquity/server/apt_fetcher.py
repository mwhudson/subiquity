# Copyright 2021 Canonical, Ltd.
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
import subprocess
import sys
import tempfile
import yaml

import apt_pkg

from curtin.commands.extract import get_handler_for_source
from curtin import util

from subiquitycore.context import with_context
from subiquitycore.utils import (
    arun_command,
    astart_command,
    )

from subiquity.common.types import (
    MirrorCheckState,
    MirrorCheckStatus,
    )


log = logging.getLogger('subiquity.server.controllers.mirror')


_apt_options_for_checking = None


def apt_options_for_checking():
    global _apt_options_for_checking
    if _apt_options_for_checking is None:
        opts = [
            '-oDir::Cache::pkgcache=',
            '-oDir::Cache::srcpkgcache=',
            '-oAPT::Update::Error-Mode=any',
            ]
        apt_pkg.init_config()
        for key in apt_pkg.config.keys('Acquire::IndexTargets'):
            if key.count('::') == 3:
                opts.append(f'-o{key}::DefaultEnabled=false')
        _apt_options_for_checking = opts
    return _apt_options_for_checking


class MirrorChecker:

    def __init__(self, source, apt_config):
        self._status = MirrorCheckStatus.NOT_STARTED
        self.source = source
        self.apt_config = apt_config
        self._tmp_root = None
        self._mounts = []
        self._output = []

    def tmpdir(self):
        return tempfile.mkdtemp(dir=self._tmp_root)

    def tmpfile(self):
        return tempfile.mktemp(dir=self._tmp_root)

    async def add_mount(self, typ, src, *, options=None):
        mountpoint = self.tmpdir()
        cmd = ['mount', '-t', typ, src]
        if options:
            cmd.extend(['-o', options])
        cmd.append(mountpoint)
        await arun_command(cmd, check=True)
        self._mounts.append(mountpoint)
        return mountpoint

    async def add_overlay(self, lower):
        upper = self.tmpdir()
        work = self.tmpdir()
        options = f'lowerdir={lower},upperdir={upper},workdir={work}'
        return await self.add_mount('overlay', 'overlay', options=options)

    async def run(self, cmd):
        proc = await astart_command(cmd, stderr=subprocess.STDOUT)

        start_output_len = len(self._output)

        async def _reader():
            while not proc.stdout.at_eof():
                try:
                    line = await proc.stdout.read(64)
                except asyncio.IncompleteReadError as e:
                    line = e.partial
                    if not line:
                        return
                self._output.append(line.decode('utf-8'))

        async def _waiter():
            rc = await proc.wait()
            await reader
            if rc == 0:
                for line in self._output[start_output_len:]:
                    if line.startswith('Err:'):
                        rc = 1
            print('rc=', rc)
            return rc

        reader = asyncio.get_event_loop().create_task(_reader())

        rc = await _waiter()
        if rc != 0:
            raise Exception

    @with_context()
    async def apply_apt_config(self, context, target):
        conf = self.tmpfile()
        with open(conf, 'w') as fp:
            yaml.dump(self.apt_config, fp)
        await self.run([
            sys.executable, '-m', 'curtin',
            'apt-config', '-t', target, '-c', conf,
            ])

    @with_context()
    async def apt_update_check(self, context, target):
        await self.run([
            'apt-get', 'update', f'-oDir={target}',
            ] + apt_options_for_checking())

    @with_context()
    async def check(self, context):
        handler = get_handler_for_source(self.source)
        root = handler.setup()
        self._status = MirrorCheckStatus.RUNNING
        try:
            self._tmp_root = tempfile.mkdtemp()
            overlay1 = await self.add_overlay(root)
            await self.apply_apt_config(context=context, target=overlay1)
            overlay2 = await self.add_overlay(overlay1)
            await self.apt_update_check(context=context, target=overlay2)
            self._status = MirrorCheckStatus.PASSED
        except Exception:
            self._status = MirrorCheckStatus.FAILED
            raise
        finally:
            pass
            #await self.cleanup()
            #handler.cleanup()

    async def cleanup(self):
        if self._tmp_root is not None:
            for mount in reversed(self._mounts):
                await arun_command(['mount', '--make-rprivate', mount])
                await arun_command(['umount', '-R', mount])
        shutil.rmtree(self._tmp_root)

    def state(self):
        return MirrorCheckState(
            status=self._status,
            output=''.join(self._output))


class DryRunMirrorChecker(MirrorChecker):

    async def add_overlay(self, lower):
        t = self.tmpdir()
        os.mkdir(f'{t}/etc')
        os.makedirs(f'{t}/var/lib/apt/partial')
        util.write_file(f'{t}/var/lib/dpkg/status', '')
        await arun_command([
            'cp', '-aT', f'{lower}/etc/apt', f'{t}/etc/apt',
            ])
        return t

    @with_context()
    async def apply_apt_config(self, context, target):
        from curtin.commands.apt_config import (
            distro,
            find_apt_mirror_info,
            generate_sources_list,
            apply_preserve_sources_list,
            rename_apt_lists)
        cfg = self.apt_config['apt']
        release = distro.lsb_release()['codename']
        arch = distro.get_architecture()
        mirrors = find_apt_mirror_info(cfg, arch)

        generate_sources_list(cfg, release, mirrors, target, arch)
        apply_preserve_sources_list(target)
        rename_apt_lists(mirrors, target, arch)
