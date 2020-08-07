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


class ProgressController(SubiquityTuiController):

    def __init__(self, app):
        super().__init__(app)
        self.progress_view = ProgressView(self)

        self.reboot_clicked = asyncio.Event()
        if self.answers.get('reboot', False):
            self.reboot_clicked.set()

        self.curtin_event_contexts = {}
        self.confirmation = asyncio.Event()

    def event(self, event):
        if event["SUBIQUITY_EVENT_TYPE"] == "start":
            self.progress_view.event_start(
                event["SUBIQUITY_CONTEXT_ID"],
                event.get("SUBIQUITY_CONTEXT_PARENT_ID"),
                event["MESSAGE"])
        elif event["SUBIQUITY_EVENT_TYPE"] == "finish":
            self.progress_view.event_finish(
                event["SUBIQUITY_CONTEXT_ID"])

    def log_line(self, event):
        log_line = event['MESSAGE']
        self.progress_view.add_log_line(log_line)

    def cancel(self):
        pass

    @with_context()
    async def start_ui(self, context):
        ## if self.install_state in [
        ##         InstallState.NOT_STARTED,
        ##         InstallState.RUNNING,
        ##         ]:
        ##     self.progress_view.title = _("Installing system")
        ## elif self.install_state == InstallState.DONE:
        ##     self.progress_view.title = _("Install complete!")
        ## elif self.install_state == InstallState.ERROR:
        ##     self.progress_view.title = (
        ##         _('An error occurred during installation'))
        await self.app.set_body(self.progress_view)
