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
import time

import requests.exceptions

from subiquitycore.controller import BaseController
from subiquitycore.core import Skip

from subiquity.ui.views.refresh import RefreshView

log = logging.getLogger("subiquitycore.controller.refresh")


class CHECK_STATE(enum.Enum):
    CHECKING = 1
    AVAILABLE = 2
    UNAVAILABLE = 3


class RefreshController(BaseController):

    def __init__(self, common):
        super().__init__(common)
        self.update_state = CHECK_STATE.CHECKING
        self.offered_at_first = False
        self.run_in_bg(self._bg_check_for_update, self._check_result)

    def _bg_check_for_update(self):
        return self.snapd_connection.get('v2/find', select='refresh')

    def _check_result(self, fut):
        try:
            response = fut.result()
            response.raise_for_status()
        except requests.exceptions.RequestException:
            log.exception("checking for update")
            self.update_state = CHECK_STATE.UNAVAILABLE
        result = response.json()
        for snap in result["result"]:
            if snap["name"] == os.environ.get("SNAP_NAME", "subiquity"):
                self.update_state = CHECK_STATE.AVAILABLE
                return
        self.update_state = CHECK_STATE.UNAVAILABLE

    def default(self, index=1):
        if self.offered_at_first and index == 2:
            raise Skip()
        if self.update_state == CHECK_STATE.UNAVAILABLE:
            raise Skip()
        if self.update_state == CHECK_STATE.AVAILABLE and index == 1:
            self.offered_at_first = True
            self.ui.set_body(RefreshView(self))
        elif self.update_state == CHECK_STATE.CHECKING:
            if index == 2:
                self.ui.set_body(RefreshView(self, still_checking=True))
            else:
                raise Skip()
        else:
            raise NotImplementedError()

    def done(self):
        self.signal.emit_signal("next-screen")

    def cancel(self, sender=None):
        self.signal.emit_signal("prev-screen")
