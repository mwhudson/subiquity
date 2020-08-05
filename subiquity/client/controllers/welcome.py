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

import logging

from subiquity.controller import SubiquityTuiController
from subiquity.ui.views import WelcomeView


log = logging.getLogger('subiquity.controllers.welcome')


class WelcomeController(SubiquityTuiController):

    endpoint = '/locale'

    def _start_ui(self, status):
        view = WelcomeView(self, status['language'])
        self.app.set_body(view)
        if 'lang' in self.answers:
            self.done(self.answers['lang'])

    def done(self, code):
        log.debug("WelcomeController.done %s next_screen", code)
        self.signal.emit_signal('l10n:language-selected', code)
        self.app.next_screen(self.post({'language': code}))

    def cancel(self):
        # Can't go back from here!
        pass