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

import asyncio
import unittest

from aiohttp.test_utils import TestClient, TestServer, loop_context
from aiohttp import web

from subiquitycore.context import Context

from subiquity.common.api.defs import api
from subiquity.common.api.server import bind


def run_coro(coro):
    asyncio.get_event_loop().run_until_complete(coro)


class TestApp:
    def __init__(self):
        self.context = Context.new(self)

    def report_start_event(self, context, description):
        pass

    def report_finish_event(self, context, description, result):
        pass

    project = 'test'


class TestControllerBase:

    def __init__(self, generic={}):
        self.generic = generic
        self.app = TestApp()
        self.context = self.app.context.child('test')

    def generic_result(self):
        return self.generic


class TestBind(unittest.TestCase):

    def test_simple(self):
        @api
        class API:
            class endpoint:
                def get(): pass

        class Impl(TestControllerBase):
            async def get(self):
                return 'value'

        app = web.Application()

        bind(app.router, API.endpoint, Impl())

        async def make_request():
            async with TestClient(TestServer(app)) as client:
                resp = await client.get("/endpoint")
                assert resp.status == 200
                self.assertEqual(await resp.json(), {'result': 'value'})

        run_coro(make_request())

    def test_nested(self):
        @api
        class API:
            class endpoint:
                class nested:
                    def get(): pass

        class Impl(TestControllerBase):
            async def nested_get(self, request, context):
                return 'nested'

        app = web.Application()

        bind(app.router, API.endpoint, Impl())

        async def make_request():
            async with TestClient(TestServer(app)) as client:
                resp = await client.get("/endpoint/nested")
                assert resp.status == 200
                self.assertEqual(await resp.json(), {'result': 'nested'})

        run_coro(make_request())

    def test_args(self):
        @api
        class API:
            class endpoint:
                path = '{arg}'
                def get(): pass

        class Impl(TestControllerBase):
            async def get(self, request):
                return request.match_info['arg']

        app = web.Application()

        bind(app.router, API.endpoint, Impl())

        async def make_request():
            async with TestClient(TestServer(app)) as client:
                resp = await client.get("/what")
                assert resp.status == 200
                self.assertEqual(await resp.json(), {'result': 'what'})

        run_coro(make_request())