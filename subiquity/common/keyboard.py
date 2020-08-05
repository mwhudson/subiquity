# Copyright 2020 Canonical, Ltd.
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

import attr
import os

from subiquitycore.utils import arun_command


@attr.s
class KeyboardSetting:
    layout = attr.ib()
    variant = attr.ib(default='')
    toggle = attr.ib(default=None)


async def set_keyboard(setting, dry_run):
    cmds = [
        ['setupcon', '--save', '--force', '--keyboard-only'],
        ['/snap/bin/subiquity.subiquity-loadkeys'],
        ]
    if dry_run:
        scale = os.environ.get('SUBIQUITY_REPLAY_TIMESCALE', "1")
        cmds = [['sleep', str(1/float(scale))]]
    for cmd in cmds:
        await arun_command(cmd)
