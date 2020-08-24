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

from subiquity.common.api.definition import API
from subiquity.common.types import KeyboardSetting
from subiquity.common.keyboard import (
    set_keyboard,
    )
from subiquity.server.controller import SubiquityController

log = logging.getLogger('subiquity.controllers.keyboard')


class KeyboardController(SubiquityController):

    endpoint = API.keyboard

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

    def __init__(self, app):
        self.ai_setting = None
        super().__init__(app)

    def load_autoinstall_data(self, data):
        if data is not None:
            self.ai_setting = KeyboardSetting(**data)

    @with_context()
    async def apply_autoinstall_config(self, context):
        if self.ai_setting is not None:
            if self.ai_setting != self.model.setting:
                self.model.setting = self.ai_setting
                await set_keyboard(self.model.setting, self.opts.dry_run)

    def make_autoinstall(self):
        return attr.asdict(self.model.setting)

    async def get(self):
        return self.model.setting

    async def post(self, data):
        self.model.setting = data
        self.configured()
