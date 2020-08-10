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

from subiquitycore.context import with_context
from subiquitycore.tuicontroller import (
    RepeatedController,
    Skip,
    TuiController,
    )

log = logging.getLogger("subiquity.controller")


class SubiquityTuiController(TuiController):

    def __init__(self, app):
        super().__init__(app)
        self.answers = app.answers.get(self.name, {})

    async def post(self, data):
        response = await self.app.post(self.endpoint, data)
        if response['confirmation-needed']:
            self.app.show_confirm_install()

    @with_context()
    async def start_ui(self, context, **kw):
        status = await self.app.get(self.endpoint)
        if not status['interactive']:
            raise Skip
        await self._start_ui(status, **kw)


class RepeatedController(RepeatedController):

    @with_context()
    async def start_ui(self, context):
        return await self.orig.start_ui(context=context, index=2)


def run_in_task(meth):
    def w(self, *args, **kw):
        self.aio_loop.create_task(meth(self, *args, **kw))
    return w
