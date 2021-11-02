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

import os
import tempfile

from subiquitycore.lsb import lsb_release
from subiquitycore.util import arun_command


async def mount(device, mountpoint, options=None, type=None):
    opts = []
    if options is not None:
        opts.extend(['-o', options])
    if type is not None:
        opts.extend(['-t', type])
    await arun_command(['mount'] + opts + [device, mountpoint], check=True)


async def unmount(mountpoint):
    await arun_command(['umount', mountpoint], check=True)


async def setup_overlay(dir):
    tdir = tempfile.mkdtemp()
    w = f'{tdir}/work'
    u = f'{tdir}/upper'
    for d in w, u:
        os.mkdirs(d)
    await mount(
        'overlay', dir, type='overlay',
        options=f'lowerdir={dir},upper={u},work={w}')


class AptConfigurer:

    def __init__(self, has_network, target, curtin_cmd_maker):
        self.has_network = has_network
        self.target = target
        self.curtin_cmd_maker

    def tpath(self, *path):
        return os.path.join(self.target, *path)

    async def configure(self):
        cmd = self.curtin_cmd_maker('apt-config')
        await arun_command(cmd, check=True)
        await setup_overlay(self.tpath('etc/apt'))
        if self.has_network:
            os.rename(
                self.tpath('etc/apt/sources.list'),
                self.tpath('etc/apt/sources.list.d/original.list'))
        else:
            os.unlink(self.tpath('etc/apt/apt.conf.d/90curtin-aptproxy'))
            await setup_overlay(self.tpath('var/lib/apt/lists'))
        series = lsb_release()['series']
        with open(self.tpath('etc/apt/sources.list', 'w')) as fp:
            fp.write(
                f'deb [check-date=no] file:///cdrom {series} main restricted\n'
                )
