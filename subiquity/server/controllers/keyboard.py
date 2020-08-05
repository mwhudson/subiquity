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

import attr

from subiquitycore.context import with_context

from subiquity.models.keyboard import KeyboardSetting
from subiquity.server.controller import SubiquityController

log = logging.getLogger('subiquity.controllers.keyboard')


class KeyboardController(SubiquityController):

    endpoint = '/keyboard'

    autoinstall_key = model_name = "keyboard"
    autoinstall_schema = {
        'type': 'object',
        'properties': {
            'layout': {'type': 'string'},
            'variant': {'type': 'string'},
            'toggle': {'type': ['string', 'null']},
            },
        'required': ['layout'],
        'additionalProperties': False,
        }

    def load_autoinstall_data(self, data):
        if data is not None:
            self.model.setting = KeyboardSetting(**data)

    @with_context()
    async def apply_autoinstall_config(self, context):
        await self.model.set_keyboard(self.model.setting)

    async def apply_settings(self, setting):
        await self.model.set_keyboard(setting)
        log.debug("KeyboardController next_screen")
        self.configured()
        self.app.next_screen()

    def make_autoinstall(self):
        return attr.asdict(self.model.setting)

    async def _get(self, context):
        return attr.asdict(self.model.setting)

    async def _post(self, context, data):
        self.model.setting = KeyboardSetting(**data)