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

import asyncio
import logging
import os
import platform
import subprocess

from subiquitycore.context import with_context
from subiquitycore.utils import arun_command, run_command

from subiquity.server.controller import SubiquityController, web_handler
from subiquity.server.controllers.install import InstallState

log = logging.getLogger("subiquity.controllers.restart")


class RebootController(SubiquityController):

    def __init__(self, app):
        super().__init__(app)
        self.context.set('hidden', True)
        self.user_reboot_event = asyncio.Event()
        self.rebooting_event = asyncio.Event()

    def add_routes(self, app):
        app.router.add_post('/reboot', self._reboot)

    @web_handler
    async def _reboot(self, context, request):
        self.app.controllers.Install.stop_uu()
        self.user_reboot_event.set()
        await self.rebooting_event.wait()

    def start(self):
        self.app.aio_loop.create_task(self._run())

    async def _run(self):
        Install = self.app.controllers.Install
        await Install.install_task
        await self.app.controllers.Late.run_event.wait()
        await self.copy_logs_to_target()
        if self.app.interactive():
            await self.user_reboot_event.wait()
            self.reboot()
        elif Install.install_state == InstallState.DONE:
            self.reboot()

    @with_context()
    async def copy_logs_to_target(self, context):
        if self.opts.dry_run and 'copy-logs-fail' in self.app.debug_flags:
            raise PermissionError()
        target_logs = os.path.join(
            self.app.base_model.target, 'var/log/installer')
        if self.opts.dry_run:
            os.makedirs(target_logs, exist_ok=True)
        else:
            await arun_command(
                ['cp', '-aT', '/var/log/installer', target_logs])
        journal_txt = os.path.join(target_logs, 'installer-journal.txt')
        try:
            with open(journal_txt, 'w') as output:
                await arun_command(
                    ['journalctl', '-b'],
                    stdout=output, stderr=subprocess.STDOUT)
        except Exception:
            log.exception("saving journal failed")

    def reboot(self):
        self.rebooting_event.set()
        if self.opts.dry_run:
            self.app.exit()
        else:
            if platform.machine() == 's390x':
                run_command(["chreipl", "/target/boot"])
            run_command(["/sbin/reboot"])
