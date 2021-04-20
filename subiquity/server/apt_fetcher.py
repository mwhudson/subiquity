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
import enum
import functools
import logging
import os
import shutil
import subprocess
import tempfile
import yaml

import apt_pkg

from curtin.util import ensure_dir, load_file, write_file

from subiquitycore.context import with_context
from subiquitycore.lsb_release import lsb_release
from subiquitycore.utils import (
    arun_command,
    astart_command,
    )

# from subiquity.common.types import MirrorCheck

log = logging.getLogger('subiquity.server.controllers.mirror')


class CheckState(enum.IntEnum):
    NOT_STARTED = enum.auto()
    CHECKING = enum.auto()
    FAILED = enum.auto()
    DONE = enum.auto()


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


def once(deps=()):
    deps = [d.__name__ for d in deps]

    def wrap(m):
        my_name = m.__name__

        @functools.wraps(m)
        async def impl(self, context=None, **kw):
            print('running', my_name)
            for d in deps:
                print('waiting for', d)
                await getattr(self, d)(context=context)
            if my_name not in self._tasks:
                print('actually running', my_name)
                self._tasks[my_name] = asyncio.get_event_loop().create_task(
                    m(self, context=context, **kw))
            return await self._tasks[my_name]
        return impl
    return wrap


LIST_OEM_CMD = '''
import apt, sys, UbuntuDrivers.detect
c = apt.Cache(rootdir=sys.argv[1])
print("\\n".join(UbuntuDrivers.detect.system_device_specific_metapackages(c)))
'''

LIST_GPGPU_CMD = '''
import apt, sys, UbuntuDrivers.detect
c = apt.Cache(rootdir=sys.argv[1])
packages = UbuntuDrivers.detect.system_gpgpu_driver_packages(c)
for package in packages:
    candidate = packages[package]['metapackage']
    if candidate:
        print(candidate)
'''

LIST_OEM_KERNEL_FLAVOR = '''
import apt, sys, UbuntuDrivers.detect
c = apt.Cache(rootdir=sys.argv[1])
for p in sys.argv[2:]:
    print(p.candidate.record['Ubuntu-Oem-Kernel-Flavour'])
'''

CHECK_PKG_EXISTS_CMD = '''
import apt, sys, UbuntuDrivers.detect
c = apt.Cache(rootdir=sys.argv[1])
if sys.argv[2] in c:
    print('ok')
'''


class PackageListFetcher:

    _id = 0

    def __init__(self, context, source, config, has_network):
        PackageListFetcher._id += 1
        self.id = str(PackageListFetcher._id)
        self.context = context
        self.source = source
        self.config = config
        self.has_network = has_network
        self._tasks = {}
        self._tree = None
        self._check_output = []
        self._check_rc = None

    @property
    def etc_apt_dir(self):
        return os.path.join(self._tree, 'etc/apt')

    @property
    def apt_lists_dir(self):
        return os.path.join(self._tree, 'var/lib/apt')

    async def _run_chrooted(self, cmd):
        return await arun_command([
            self.executable, '-m', 'curtin',
            'in-target', '-t', self._tree,
            ] + cmd, check=True)

    @once()
    async def create_tree(self, context):
        self._root = tempfile.mkdtemp(prefix='mirror-check')
        self._tree = os.path.join(self._root, 'tree')
        u = self._upper = os.path.join(self._root, 'work')
        w = self._work = os.path.join(self._root, 'upper')
        for d in (self._tree, self._upper, self._work):
            os.mkdir(d)
        await arun_command([
            'mount', '-t', 'overlay', 'overlay'
            '-o', f'lowerdir={self.source},workdir={w},upperdir={u}',
            self._tree,
            ], check=True)
        self._curtin_conf = os.path.join(self._root, 'curtin-apt-conf.yaml')
        with open(self._curtin_conf, 'w') as fp:
            yaml.dump(self.config, fp)

    @once(deps=(create_tree,))
    async def add_cdrom_ref(self, *, replace_all):
        sources_list_path = os.path.join(self.etc_apt_dir, 'sources.list')
        if replace_all:
            trailer = ''
        else:
            trailer = load_file(sources_list_path)
        codename = lsb_release()['codename']
        new_content = f'deb file:///cdrom {codename} main restricted\n'
        write_file(sources_list_path, new_content + trailer)

    @once(deps=(create_tree,))
    async def run_apt_config(self):
        await arun_command([
            self.executable, '-m', 'curtin',
            'apt-config', '-t', self._tree, '-c', self._curtin_conf,
            ], check=True)

    @once()
    @with_context()
    async def configure(self, context):
        if self.has_network:
            await self.run_apt_config()
            await self.add_cdrom_ref(replace_all=False)
        else:
            await self.add_cdrom_ref(replace_all=True)
            # Add something to disable use of sources.list.d here

    @once(deps=(configure,))
    @with_context()
    async def check(self, context):
        apt_cmd = ['apt-get', 'update', f'-oDir={self._tree}'] \
            + apt_options_for_checking()
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
                self._check_output.append(line.decode('utf-8'))
                print(self._check_output)

        async def _waiter():
            rc = await proc.wait()
            await reader
            if rc == 0:
                for line in self._check_output:
                    if line.startswith('Err:'):
                        rc = 1
            print('rc=', rc)
            self._check_rc = rc

        reader = asyncio.get_event_loop().create_task(_reader())

        await _waiter()

#    def check_status(self):
#        return MirrorCheck(
#            id=self.id,
#            in_progress=self._check_rc is None,
#            success=self._check_rc == 0,
#            output=self._check_output)

    @once(deps=(check,))
    @with_context(description="downloading package metadata")
    async def download(self, context):
        return await arun_command(
            ['apt-get', 'update', f'-oDir={self._tree}'],
            check=True)

    @once(deps=(check,))
    @with_context(description="checking for OEM packages")
    async def check_oem(self, context):
        cp = await arun_command(
            ['/usr/bin/python3', '-c', LIST_OEM_CMD, self._tree])
        print(cp)
        return cp.stdout.splitlines()

    @once(deps=(check,))
    @with_context(description="checking for GPGPU packages")
    async def check_gpgpu(self, context):
        cp = await arun_command(
            ['/usr/bin/python3', '-c', LIST_GPGPU_CMD, self._tree])
        print(cp)
        return cp.stdout.splitlines()

    @once()
    @with_context(description="checking for kernel flavor")
    async def kernel_flavor(self, context):
        packages = await self.check_oem(context=context)
        cp = await arun_command(
            ['/usr/bin/python3', '-c', LIST_OEM_KERNEL_FLAVOR, self._tree]
            + packages)
        print(cp)
        for line in cp.stdout.splitlines():
            if line != 'default':
                return line
        return None

    @once()
    @with_context(description="checking package exists")
    async def package_exists(self, context, package):
        cp = await arun_command(
            ['/usr/bin/python3', '-c', CHECK_PKG_EXISTS_CMD, self._tree,
             package])
        return cp.stdout.strip() == 'ok'


class DryRunPackageListFetcher(PackageListFetcher):

    @once()
    async def create_tree(self, context):
        self._root = tempfile.mkdtemp(prefix='mirror-check')
        self._tree = os.path.join(self._root, 'tree')
        os.mkdir(self._tree)
        self._curtin_conf = os.path.join(self._root, 'curtin-apt-conf.yaml')
        write_file(os.path.join(self._tree, 'var/lib/dpkg/status'), '')
        ensure_dir(os.path.join(self._tree, 'etc/apt'))
        ensure_dir(os.path.join(self._tree, 'var/lib/apt/lists'))
        paths = (
            'etc/apt/trusted.gpg',
            'etc/apt/trusted.gpg.d',
            'var/lib/dpkg/status',
            )
        for path in paths:
            src = '/' + path
            tgt = os.path.join(self._tree, path)
            ensure_dir(os.path.dirname(tgt))
            if os.path.isdir(src):
                shutil.copytree(src, tgt)
            else:
                shutil.copy(src, tgt)
        with open(self._curtin_conf, 'w') as fp:
            yaml.dump(self.config, fp)

    @once(deps=(create_tree,))
    @with_context()
    async def configure(self, context):
        try:
            from curtin.distro import get_architecture
        except ImportError:
            from curtin.util import get_architecture
        from curtin.commands.apt_config import get_mirror
        url = get_mirror(self.config['apt'], "primary", get_architecture())
        sources_list_path = os.path.join(self.etc_apt_dir, 'sources.list')
        codename = lsb_release()['codename']
        new_content = f'deb {url} {codename} main\n'
        print(new_content)
        write_file(sources_list_path, new_content)
