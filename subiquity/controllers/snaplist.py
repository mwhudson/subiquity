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

import logging

import requests.exceptions

from subiquitycore.controller import BaseController
from subiquitycore.core import Skip

from subiquity.async_helpers import (
    schedule_task,
    )
from subiquity.models.snaplist import SnapSelection
from subiquity.ui.views.snaplist import SnapListView

log = logging.getLogger('subiquity.controllers.snaplist')


class SnapdSnapInfoLoader:

    def __init__(self, model, snapd, store_section):
        self.model = model
        self.store_section = store_section

        self.main_task = None
        self.snap_list_fetched = False
        self.failed = False

        self.snapd = snapd
        self.pending_info_snaps = []
        self.tasks = {}  # {snap:task}

    def start(self):
        self._running = True
        log.debug("loading list of snaps")
        self.main_task = schedule_task(self._start())

    async def _start(self):
        task = self.tasks[None] = schedule_task(self._load_list())
        await task
        self.pending_snaps = self.model.get_snap_list()
        log.debug("fetched list of %s snaps", len(self.pending_snaps))
        while self.pending_snaps and self._running:
            snap = self.pending_snaps.pop(0)
            task = self.tasks[snap] = schedule_task(
                self._fetch_info_for_snap(snap))
            await task

    async def _load_list(self):
        try:
            result = await self.snapd.get(
                'v2/find', section=self.store_section)
        except requests.exceptions.RequestException:
            log.exception("loading list of snaps failed")
            self.failed = True
            return
        self.model.load_find_data(result)
        self.snap_list_fetched = True

    def stop(self):
        if self.main_task is not None:
            self.main_task.cancel()

    async def _fetch_info_for_snap(self, snap):
        log.debug('starting fetch for %s', snap.name)
        try:
            data = await self.snapd.get(
                'v2/find', name=snap.name)
        except requests.exceptions.RequestException:
            log.exception("loading snap info failed")
            # XXX something better here?
            return
        if not self._running:
            return
        log.debug('got data for %s', snap.name)
        self.model.load_info_data(data)

    def get_snap_list_task(self):
        return self.tasks[None]

    def get_snap_info_task(self, snap):
        if snap not in self.tasks:
            if snap in self.pending_snaps:
                self.pending_snaps.remove(snap)
            self.tasks[snap] = schedule_task(
                self._fetch_info_for_snap(snap))
        return self.tasks[snap]


class SnapListController(BaseController):

    signals = [
        ('snapd-network-change', 'snapd_network_changed'),
    ]

    def _make_loader(self):
        return SnapdSnapInfoLoader(
            self.model, self.app.snapd,
            self.opts.snap_section)

    def __init__(self, app):
        super().__init__(app)
        self.model = app.base_model.snaplist
        self.loader = self._make_loader()

    def snapd_network_changed(self):
        # If the loader managed to load the list of snaps, the
        # network must basically be working.
        if self.loader.snap_list_fetched:
            return
        else:
            self.loader.stop()
        self.loader = self._make_loader()
        self.loader.start()

    def start_ui(self):
        if self.loader.failed or not self.app.base_model.network.has_network:
            # If loading snaps failed or the network is disabled, skip the
            # screen.
            self.signal.emit_signal("installprogress:snap-config-done")
            raise Skip()
        if 'snaps' in self.answers:
            to_install = {}
            for snap_name, selection in self.answers['snaps'].items():
                to_install[snap_name] = SnapSelection(**selection)
            self.done(to_install)
            return
        self.ui.set_body(SnapListView(self.model, self))

    def get_snap_list_task(self):
        return self.loader.get_snap_list_task()

    def get_snap_info_task(self, snap):
        return self.loader.get_snap_info_task(snap)

    def done(self, snaps_to_install):
        log.debug(
            "SnapListController.done next-screen snaps_to_install=%s",
            snaps_to_install)
        self.model.set_installed_list(snaps_to_install)
        self.signal.emit_signal("installprogress:snap-config-done")
        self.signal.emit_signal("next-screen")

    def cancel(self, sender=None):
        self.signal.emit_signal("prev-screen")
