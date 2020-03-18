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

from subiquity.controller import NoUIController


class CmdListController(NoUIController):

    autoinstall_default = []
    cmds = ()

    def load_autoinstall_data(self, data):
        self.cmds = data

    async def run(self):
        with self.app.exclusive(self.name) as done:
            if done:
                return
            for i, cmd in enumerate(self.cmds):
                sc_cmd = [
                    "systemd-cat", "--level-prefix=false",
                    "--identifier=subiquity", "sh", "-c", cmd]
                with self.context.child("command_{}".format(i), cmd):
                    proc = await asyncio.create_subprocess_exec(*sc_cmd)
                    await proc.communicate()


class EarlyController(CmdListController):

    autoinstall_key = 'early-commands'


class LateController(CmdListController):

    autoinstall_key = 'late-commands'
