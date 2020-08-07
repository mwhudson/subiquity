# Copyright 2015 Canonical, Ltd.
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
import datetime
import logging
import os
import re
import shutil
import sys
import tempfile
import traceback

from curtin.commands.install import (
    ERROR_TARFILE,
    INSTALL_LOG,
    )
from curtin.util import write_file

from systemd import journal

import yaml

from subiquitycore.async_helpers import (
    run_in_thread,
    schedule_task,
    )
from subiquitycore.context import Status, with_context
from subiquitycore.utils import (
    arun_command,
    astart_command,
    )

from subiquity.client.controller import SubiquityTuiController
from subiquity.common.errorreport import ErrorReportKind
from subiquity.journald import journald_listener
from subiquity.ui.views.installprogress import ProgressView


log = logging.getLogger("subiquity.client.controllers.installprogress")


class InstallProgressController(SubiquityTuiController):

    def __init__(self, app):
        super().__init__(app)
        self.model = app.base_model
        self.progress_view = ProgressView(self)
        app.add_event_listener(self)

        journal_fd, watcher = journald_listener(
            ["subiquity"],
            self.curtin_event)
        self.app.aio_loop.add_reader(journal_fd, watcher)
        self.reboot_clicked = asyncio.Event()
        if self.answers.get('reboot', False):
            self.reboot_clicked.set()

        self.curtin_event_contexts = {}
        self.confirmation = asyncio.Event()

    def _journal_event(self, event):
        if event['SYSLOG_IDENTIFIER'] == self._event_syslog_identifier:
            self.curtin_event(event)
        elif event['SYSLOG_IDENTIFIER'] == self._log_syslog_identifier:
            self.curtin_log(event)

    def curtin_log(self, event):
        log_line = event['MESSAGE']
        self.progress_view.add_log_line(log_line)
        self.tb_extractor.feed(log_line)

    def cancel(self):
        pass

    async def _start_ui(self, status):
        if self.install_state in [
                InstallState.NOT_STARTED,
                InstallState.RUNNING,
                ]:
            self.progress_view.title = _("Installing system")
        elif self.install_state == InstallState.DONE:
            self.progress_view.title = _("Install complete!")
        elif self.install_state == InstallState.ERROR:
            self.progress_view.title = (
                _('An error occurred during installation'))
        self.ui.set_body(self.progress_view)
        schedule_task(self.move_on())


uu_apt_conf = """\
# Config for the unattended-upgrades run to avoid failing on battery power or
# a metered connection.
Unattended-Upgrade::OnlyOnACPower "false";
Unattended-Upgrade::Skip-Updates-On-Metered-Connections "true";
"""
