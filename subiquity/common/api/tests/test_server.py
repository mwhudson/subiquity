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
import contextlib
import unittest

from aiohttp.test_utils import TestClient, TestServer
from aiohttp import web

from subiquitycore.context import Context

from subiquity.common.api.defs import api, Payload
from subiquity.common.api.server import bind


def run_coro(coro):
    asyncio.get_event_loop().run_until_complete(coro)


class TestApp:

    def report_start_event(self, context, description):
        pass

    def report_finish_event(self, context, description, result):
        pass

    project = 'test'


class TestControllerBase:

    def __init__(self, generic={}):
        self.generic = generic
        self.context = Context.new(TestApp())

    def generic_result(self):
        return self.generic


@contextlib.asynccontextmanager
async def makeTestClient(api, impl):
    app = web.Application()
    bind(app.router, api, impl)
    async with TestClient(TestServer(app)) as client:
        yield client


class TestBind(unittest.TestCase):

    async def assertResponse(self, coro, value):
        resp = await coro
        self.assertEqual(resp.status, 200)
        self.assertEqual(await resp.json(), value)

    def test_simple(self):
        @api
        class API:
            def GET() -> str: ...

        class Impl(TestControllerBase):
            async def GET(self) -> str:
                return 'value'

        async def make_request():
            async with makeTestClient(API, Impl()) as client:
                await self.assertResponse(
                    client.get("/"), {'result': 'value'})

        run_coro(make_request())

    def test_nested(self):
        @api
        class API:
            class endpoint:
                class nested:
                    def get(): ...

        class Impl(TestControllerBase):
            async def nested_get(self, request, context):
                return 'nested'

        async def make_request():
            async with makeTestClient(API.endpoint, Impl()) as client:
                await self.assertResponse(
                    client.get("/endpoint/nested"), {'result': 'nested'})

        run_coro(make_request())

    def test_args(self):
        @api
        class API:
            def GET(arg: str): ...

        class Impl(TestControllerBase):
            async def GET(self, arg: str):
                return arg

        async def make_request():
            async with makeTestClient(API, Impl()) as client:
                await self.assertResponse(
                    client.get('/?arg="whut"'), {'result': 'whut'})

        run_coro(make_request())

    def test_post(self):
        @api
        class API:
            def POST(data: Payload[str]) -> str: ...

        class Impl(TestControllerBase):
            async def POST(self, data: str) -> str:
                return data

        async def make_request():
            async with makeTestClient(API, Impl()) as client:
                await self.assertResponse(
                    client.post("/", json={'data': 'value'}),
                    {'result': 'value'})

        run_coro(make_request())
