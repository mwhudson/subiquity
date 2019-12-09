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
import enum
import logging
import os

import requests.exceptions

from subiquitycore.controller import BaseController
from subiquitycore.core import Skip

from subiquity.async_helpers import (
    schedule_task,
    SingleInstanceTask,
    )

log = logging.getLogger('subiquity.controllers.refresh')


class CheckState(enum.IntEnum):
    NOT_STARTED = enum.auto()
    CHECKING = enum.auto()
    FAILED = enum.auto()

    AVAILABLE = enum.auto()
    UNAVAILABLE = enum.auto()

    def is_definite(self):
        return self in [self.AVAILABLE, self.UNAVAILABLE]


class RefreshController(BaseController):

    autoinstall_key = 'refresh-installer'

    signals = [
        ('snapd-network-change', 'snapd_network_changed'),
    ]

    def __init__(self, app):
        self.enabled = True
        super().__init__(app)
        if self.interactive():
            self.enabled = True
        else:
            self.enabled = self.autoinstall_data.get('update', False)
        self.snap_name = os.environ.get("SNAP_NAME", "subiquity")
        self.check_state = CheckState.NOT_STARTED

        self.current_snap_version = "unknown"
        self.new_snap_version = ""

        self.offered_first_time = False
        self.check_task = SingleInstanceTask()

    def load_autoinstall(self):
        pass

    async def apply_autoinstall_config(self, index=0):
        if self.app.updated:
            return
        if not self.enabled:
            return
        print("configuring snapd")
        await self.configure_snapd_task
        print("checking for update")
        await asyncio.wait_for(self.check_for_update(), 60)
        if self.check_state == CheckState.AVAILABLE:
            print("update available, updating")
            update_marker = os.path.join(self.app.state_dir, 'updating')
            open(update_marker, 'w').close()
            await self.app.snapd.post_and_wait(
                'v2/snaps/{}'.format(self.snap_name),
                {'action': 'refresh'})
            self.app.updated = True
        else:
            print("no update available, continuing")

    def start(self):
        if self.app.updated:
            return
        self.check_state = CheckState.CHECKING
        self.configure_snapd_task = schedule_task(self.configure_snapd())

    async def configure_snapd(self):
        try:
            r = await self.app.snapd.get(
                'v2/snaps/{snap_name}'.format(snap_name=self.snap_name))
        except requests.exceptions.RequestException:
            log.exception("getting snap details")
            return
        self.current_snap_version = r['result']['version']
        for k in 'channel', 'revision', 'version':
            self.app.note_data_for_apport(
                "Snap" + k.title(), r['result'][k])
        log.debug(
            "current version of snap is: %r",
            self.current_snap_version)
        channel = self.get_refresh_channel()
        log.debug("switching %s to %s", self.snap_name, channel)
        try:
            await self.app.snapd.post_and_wait(
                'v2/snaps/{}'.format(self.snap_name),
                {'action': 'switch', 'channel': channel})
        except requests.exceptions.RequestException:
            log.exception("switching channels")
            return
        log.debug("snap switching completed")

    def get_refresh_channel(self):
        """Return the channel we should refresh subiquity to."""
        if self.autoinstall_data and 'channel' in self.autoinstall_data:
            return self.autoinstall_data['channel']
        if 'channel' in self.answers:
            return self.answers['channel']
        with open('/proc/cmdline') as fp:
            cmdline = fp.read()
        prefix = "subiquity-channel="
        for arg in cmdline.split():
            if arg.startswith(prefix):
                log.debug(
                    "get_refresh_channel: found %s on kernel cmdline", arg)
                return arg[len(prefix):]

        info_file = '/cdrom/.disk/info'
        try:
            fp = open(info_file)
        except FileNotFoundError:
            if self.opts.dry_run:
                info = (
                    'Ubuntu-Server 18.04.2 LTS "Bionic Beaver" - '
                    'Release amd64 (20190214.3)')
            else:
                log.debug(
                    "get_refresh_channel: failed to find .disk/info file")
                return
        else:
            with fp:
                info = fp.read()
        release = info.split()[1]
        return 'stable/ubuntu-' + release

    def snapd_network_changed(self):
        if self.check_state.is_definite():
            return
        if self.interactive():
            self.check_task.start_sync(self.check_for_update())

    async def check_for_update(self):
        await self.configure_snapd_task
        log.debug("hitting v2/find")
        try:
            result = await self.app.snapd.get('v2/find', select='refresh')
        except requests.exceptions.RequestException as e:
            log.exception("checking for update")
            self.check_error = e
            self.check_state = CheckState.FAILED
            return
        log.debug("_check_result %s", result)
        for snap in result["result"]:
            if snap["name"] == self.snap_name:
                self.check_state = CheckState.AVAILABLE
                self.new_snap_version = snap["version"]
                log.debug(
                    "new version of snap available: %r",
                    self.new_snap_version)
                break
        else:
            self.check_state = CheckState.UNAVAILABLE
        if self.showing:
            self.ui.body.update_check_state()

    def start_update(self, callback):
        update_marker = os.path.join(self.app.state_dir, 'updating')
        open(update_marker, 'w').close()
        return schedule_task(self._start_update(callback))

    async def _start_update(self, callback):
        try:
            change = await self.app.snapd.post(
                'v2/snaps/{}'.format(self.snap_name),
                {'action': 'refresh'})
        except requests.exceptions.RequestException as e:
            log.exception("requesting update")
            self.update_state = CheckState.FAILED
            self.update_failure = e
            return
        log.debug("refresh requested: %s", change)
        callback(change)

    def get_progress(self, change, callback):
        schedule_task(self._get_progress(change, callback))

    async def _get_progress(self, change, callback):
        try:
            result = await self.app.snapd.get(
                'v2/changes/{}'.format(change))
        except requests.exceptions.RequestException as e:
            log.exception("checking for progress")
            self.update_state = CheckState.FAILED
            self.update_failure = e
            return
        callback(result['result'])

    def start_ui(self, index=1):
        from subiquity.ui.views.refresh import RefreshView
        if self.app.updated:
            raise Skip()
        show = False
        if index == 1:
            if self.check_state == CheckState.AVAILABLE:
                show = True
                self.offered_first_time = True
        elif index == 2:
            if not self.offered_first_time:
                if self.check_state in [CheckState.AVAILABLE,
                                        CheckState.CHECKING]:
                    show = True
        else:
            raise AssertionError("unexpected index {}".format(index))
        if show:
            self.ui.set_body(RefreshView(self))
            if 'update' in self.answers:
                if self.answers['update']:
                    self.ui.body.update()
                else:
                    self.done()
        else:
            raise Skip()

    def done(self, sender=None):
        log.debug("RefreshController.done next-screen")
        self.signal.emit_signal('next-screen')

    def cancel(self, sender=None):
        self.signal.emit_signal('prev-screen')
