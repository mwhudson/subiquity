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

import enum
import logging
import os

import requests.exceptions

from subiquitycore.controller import BaseController
from subiquitycore.core import Skip

class CHECK_STATE(enum.Enum):
    CHECKING = 1
    AVAILABLE = 2
    UNAVAILABLE = 3
    FAILED = 4

from subiquity.ui.views.refresh import RefreshView

log = logging.getLogger("subiquitycore.controller.refresh")



class RefreshController(BaseController):

    def __init__(self, common):
        super().__init__(common)
        self.snap_name = os.environ.get("SNAP_NAME", "subiquity")
        self.update_state = CHECK_STATE.CHECKING
        self.update_failure = None
        self.offered_at_first = False
        self.run_in_bg(self._bg_check_for_update, self._check_result)
        self.view = None

    def _bg_check_for_update(self):
        return self.snapd_connection.get('v2/find', select='refresh')

    def _check_result(self, fut):
        try:
            response = fut.result()
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            log.exception("checking for update")
            self.update_state = CHECK_STATE.FAILED
            self.update_failure = e
        result = response.json()
        for snap in result["result"]:
            if snap["name"] == os.environ.get("SNAP_NAME", "subiquity"):
                self.update_state = CHECK_STATE.AVAILABLE
                return
        self.update_state = CHECK_STATE.UNAVAILABLE
        if self.view is not None:
            self.view.update_check_status()

    def start_update(self, callback):
        self.run_in_bg(
            self._bg_start_update,
            lambda fut: self.update_started(fut, callback))

    def _bg_start_update(self):
        return self.snapd_connection.post(
            'v2/snaps/subiquity', {'action':'refresh'})

    def update_started(self, fut, callback):
        try:
            response = fut.result()
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            log.exception("checking for update")
            self.update_state = CHECK_STATE.FAILED
            self.update_failure = e
        result = response.json()
        log.debug("%s", result)
        callback(result['change'])

    def get_progress(self, change, callback):
        self.run_in_bg(
            lambda: self._bg_get_progress(change),
            lambda fut: self.got_progress(fut, callback))

    def _bg_get_progress(self, change):
        return self.snapd_connection.get('v2/changes/{}'.format(change))

    def got_progress(self, fut, callback):
        try:
            response = fut.result()
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            log.exception("checking for update")
            self.update_state = CHECK_STATE.FAILED
            self.update_failure = e
        result = response.json()
        #log.debug("%s", result.keys())
        #log.debug("%s", result)
        ### should massage example data so this can be result['result']!!!
        callback(result)

    def default(self, index=1):
        if self.offered_at_first and index == 2:
            raise Skip()
        elif self.update_state == CHECK_STATE.UNAVAILABLE:
            raise Skip()
        elif self.update_state == CHECK_STATE.AVAILABLE and index == 1:
            self.offered_at_first = True
            self.view = RefreshView(self)
        elif self.update_state == CHECK_STATE.CHECKING:
            if index == 2:
                self.view = RefreshView(self, still_checking=True)
            else:
                raise Skip()
        elif self.update_state == CHECK_STATE.FAILED:
            raise Skip()
        else:
            raise NotImplementedError()
        self.ui.set_body(self.view)

    def done(self):
        self.view = None
        self.signal.emit_signal("next-screen")

    def cancel(self, sender=None):
        self.view = None
        self.signal.emit_signal("prev-screen")
