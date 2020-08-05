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

from subiquitycore.async_helpers import schedule_task
from subiquitycore.context import with_context

from subiquity.models.keyboard import KeyboardSetting
from subiquity.server.controller import SubiquityController
from subiquity.ui.views import KeyboardView

log = logging.getLogger('subiquity.controllers.keyboard')


class KeyboardController(SubiquityController):

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
    signals = [
        ('l10n:language-selected', 'language_selected'),
        ]

    def load_autoinstall_data(self, data):
        if data is not None:
            self.model.setting = KeyboardSetting(**data)

    @with_context()
    async def apply_autoinstall_config(self, context):
        await self.model.set_keyboard(self.model.setting)

    def language_selected(self, code):
        log.debug("language_selected %s", code)
        if not self.model.has_language(code):
            code = code.split('_')[0]
        if not self.model.has_language(code):
            code = 'C'
        log.debug("loading launguage %s", code)
        self.model.load_language(code)

    def start_ui(self):
        if self.model.current_lang is None:
            self.model.load_language('C')
        view = KeyboardView(self.model, self, self.opts)
        self.ui.set_body(view)
        if 'layout' in self.answers:
            layout = self.answers['layout']
            variant = self.answers.get('variant', '')
            self.done(KeyboardSetting(layout=layout, variant=variant))

    async def apply_settings(self, setting):
        await self.model.set_keyboard(setting)
        log.debug("KeyboardController next_screen")
        self.configured()
        self.app.next_screen()

    def done(self, setting):
        schedule_task(self.apply_settings(setting))

    def cancel(self):
        self.app.prev_screen()

    def make_autoinstall(self):
        return attr.asdict(self.model.setting)
