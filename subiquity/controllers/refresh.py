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

import logging

from subiquitycore.controller import BaseController

from subiquity.ui.views.refresh import RefreshView

log = logging.getLogger("subiquitycore.controller.refresh")


class RefreshController(BaseController):

    def __init__(self, common):
        super().__init__(common)
        self.offered = False

    def default(self):
        if self.offered:
            # XXX should call self.cancel if we are moving backwards!!
            self.done()
        else:
            self.offered = True
            self.ui.set_body(RefreshView(self))

    def done(self):
        self.signal.emit_signal("next-screen")

    def cancel(self, sender=None):
        self.signal.emit_signal("prev-screen")
