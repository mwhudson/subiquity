# Copyright 2020 Canonical, Ltd.
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

import json
import logging

from aiohttp import web

import jsonschema

from subiquitycore.context import with_context
from subiquitycore.controller import (
    BaseController,
    )

log = logging.getLogger("subiquity.controller")


def trim(text):
    if len(text) > 80:
        return text[:77] + '...'
    else:
        return text


def web_handler(meth):
    async def w(self, request):
        context = self.context.child(meth.__name__, trim(await request.text()))
        with context:
            context.set('request', request)
            resp = await meth(
                self, request=request, context=context)
            if resp is None:
                resp = {}
            if not isinstance(resp, web.Response):
                resp = web.json_response(resp)
            context.description = trim(resp.text)
            return resp
    return w


class SubiquityController(BaseController):

    autoinstall_key = None
    autoinstall_schema = None
    autoinstall_default = None
    endpoint = None

    def __init__(self, app):
        super().__init__(app)
        self.autoinstall_applied = False
        self.context.set('controller', self)
        self.setup_autoinstall()

    def setup_autoinstall(self):
        if self.app.autoinstall_config:
            with self.context.child("load_autoinstall_data"):
                ai_data = self.app.autoinstall_config.get(
                    self.autoinstall_key,
                    self.autoinstall_default)
                if ai_data is not None and self.autoinstall_schema is not None:
                    jsonschema.validate(ai_data, self.autoinstall_schema)
                self.load_autoinstall_data(ai_data)

    def load_autoinstall_data(self, data):
        """Load autoinstall data.

        This is called if there is an autoinstall happening. This
        controller may not have any data, and this controller may still
        be interactive.
        """
        pass

    @with_context()
    async def apply_autoinstall_config(self, context):
        """Apply autoinstall configuration.

        This is only called for a non-interactive controller. It should
        block until the configuration has been applied. (self.configured()
        is called after this is done).
        """
        pass

    def interactive(self):
        if not self.app.autoinstall_config:
            return True
        i_sections = self.app.autoinstall_config.get(
            'interactive-sections', [])
        if '*' in i_sections or self.autoinstall_key in i_sections:
            return True
        return False

    def configured(self):
        """Let the world know that this controller's model is now configured.
        """
        if self.model_name is not None:
            self.app.base_model.configured(self.model_name)

    def deserialize(self, state):
        pass

    def make_autoinstall(self):
        return {}

    def add_routes(self, app):
        if self.endpoint:
            app.router.add_get(self.endpoint, self.get)
            app.router.add_post(self.endpoint, self.post)

    @web_handler
    async def get(self, context, request):
        resp = await self._get(context)
        resp['interactive'] = self.interactive()
        return resp

    @web_handler
    async def post(self, context, request):
        payload = await request.text()
        resp = await self._post(context, json.loads(payload))
        if resp is None:
            resp = {}
        base_model = self.app.base_model
        confirmation_needed = False
        if self.model_name:
            if base_model.is_last_install_event(self.model_name):
                base_model.last_install_event = self.model_name
                confirmation_needed = True
            else:
                self.configured()
        resp['confirmation-needed'] = confirmation_needed
        return resp
