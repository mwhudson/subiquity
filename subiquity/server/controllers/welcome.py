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
import os

from subiquitycore.screen import is_linux_tty

from subiquity.server.controller import SubiquityController
from subiquity.ui.views import WelcomeView


log = logging.getLogger('subiquity.controllers.welcome')


class WelcomeController(SubiquityController):

    endpoint = '/locale'

    autoinstall_key = model_name = "locale"
    autoinstall_schema = {'type': 'string'}
    autoinstall_default = 'en_US.UTF-8'

    def interactive(self):
        return self.app.interactive()

    def load_autoinstall_data(self, data):
        os.environ["LANG"] = data

    def start(self):
        lang = os.environ.get("LANG")
        if lang is not None and lang.endswith(".UTF-8"):
            lang = lang.rsplit('.', 1)[0]
        for code, name in self.model.get_languages(is_linux_tty()):
            if code == lang:
                self.model.switch_language(code)
                break
        else:
            self.model.selected_language = lang

    def serialize(self):
        return self.model.selected_language

    def deserialize(self, data):
        self.model.switch_language(data)

    def make_autoinstall(self):
        return self.model.selected_language

    async def _get(self):
        return {'language': self.model.selected_language}

    async def post(self, request):
        self.model.switch_language(request.json()['language'])
