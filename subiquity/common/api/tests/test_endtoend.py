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

import attr
import unittest

from subiquitycore import contextlib38

from subiquity.common.api.client import make_client
from subiquity.common.api.defs import api, Payload

from .test_server import (
    makeTestClient,
    run_coro,
    TestControllerBase,
    )


@contextlib38.asynccontextmanager
async def makeE2EClient(api, impl):
    async with makeTestClient(api, impl) as client:

        async def make_request(method, path, *, params, json):
            async with client.request(
                    method, path, params=params, json=json) as resp:
                return await resp.json()

        yield make_client(api, make_request)


class TestEndToEnd(unittest.TestCase):

    def test_simple(self):
        @api
        class API:
            def GET() -> str: ...

        class Impl(TestControllerBase):
            async def GET(self) -> str:
                return 'value'

        async def make_request():
            async with makeE2EClient(API, Impl()) as client:
                self.assertEqual(await client.GET(), 'value')

        run_coro(make_request())

    def test_nested(self):
        @api
        class API:
            class endpoint:
                class nested:
                    def GET() -> str: ...

        class Impl(TestControllerBase):
            async def endpoint_nested_GET(self) -> str:
                return 'value'

        async def make_request():
            async with makeE2EClient(API, Impl()) as client:
                self.assertEqual(await client.endpoint.nested.GET(), 'value')

        run_coro(make_request())

    def test_args(self):
        @api
        class API:
            def GET(arg1: str, arg2: str) -> str: ...

        class Impl(TestControllerBase):
            async def GET(self, arg1: str, arg2: str) -> str:
                return '{}+{}'.format(arg1, arg2)

        async def make_request():
            async with makeE2EClient(API, Impl()) as client:
                self.assertEqual(
                    await client.GET(arg1="A", arg2="B"), 'A+B')

        run_coro(make_request())

    def test_defaults(self):
        @api
        class API:
            def GET(arg1: str, arg2: str = "arg2") -> str: ...

        class Impl(TestControllerBase):
            async def GET(self, arg1: str, arg2: str = "arg2") -> str:
                return '{}+{}'.format(arg1, arg2)

        async def make_request():
            async with makeE2EClient(API, Impl()) as client:
                self.assertEqual(
                    await client.GET(arg1="A", arg2="B"), 'A+B')
                self.assertEqual(
                    await client.GET(arg1="A"), 'A+arg2')

        run_coro(make_request())

    def test_post(self):
        @api
        class API:
            def POST(data: Payload[dict]) -> str: ...

        class Impl(TestControllerBase):
            async def POST(self, data: dict) -> str:
                return data['key']

        async def make_request():
            async with makeE2EClient(API, Impl()) as client:
                self.assertEqual(
                    await client.POST({'key': 'value'}), 'value')

        run_coro(make_request())

    def test_typed(self):

        @attr.s(auto_attribs=True)
        class In:
            val: int

        @attr.s(auto_attribs=True)
        class Out:
            doubled: int

        @api
        class API:
            class doubler:
                def post(data: In) -> Out: ...

        class Impl(TestControllerBase):
            async def doubler_post(self, data: In) -> Out:
                return Out(doubled=data.val*2)

        async def make_request():
            async with makeE2EClient(API, Impl()) as client:
                out = await client.doubler.post(In(3))
                self.assertEqual(out.doubled, 6)

        run_coro(make_request())
