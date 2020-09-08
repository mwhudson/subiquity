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
async def makeE2EClient(api, impl, resp_hook=lambda x: x):
    async with makeTestClient(api, impl) as client:

        async def make_request(method, path, *, params, json):
            async with client.request(
                    method, path, params=params, json=json) as resp:
                return resp_hook(await resp.json())

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
                def POST(data: In) -> Out: ...

        class Impl(TestControllerBase):
            async def doubler_POST(self, data: In) -> Out:
                return Out(doubled=data.val*2)

        async def make_request():
            async with makeE2EClient(API, Impl()) as client:
                out = await client.doubler.POST(In(3))
                self.assertEqual(out.doubled, 6)

        run_coro(make_request())

    def test_hooks(self):

        @api
        class API:
            def GET(x: int) -> int: ...

        class Impl(TestControllerBase):
            def generic_result(self):
                return {'other': 2}

            async def GET(self, x: int) -> int:
                return x

        def resp_hook(resp):
            resp['result'] *= resp['other']
            return resp

        async def make_request():
            async with makeE2EClient(API, Impl(), resp_hook) as client:
                r = await client.GET(2)
                self.assertEqual(r, 4)

        run_coro(make_request())

    def test_error(self):

        @api
        class API:
            class good:
                def GET(x: int) -> int: ...

            class bad:
                def GET(x: int) -> int: ...

        class Impl(TestControllerBase):
            def make_error_response(self, exc):
                return {'error': str(exc)}

            async def good_GET(self, x: int) -> int:
                return x + 1

            async def bad_GET(self, x: int) -> int:
                raise Exception("baz")

        excs = []

        def resp_hook(resp):
            if 'error' in resp:
                excs.append(resp['error'])
            return resp

        async def make_request():
            async with makeE2EClient(API, Impl(), resp_hook) as client:
                r = await client.good.GET(2)
                self.assertEqual(r, 3)
                self.assertEqual(excs, [])
                r = await client.bad.GET(2)
                self.assertEqual(r, None)
                self.assertEqual(excs, ["baz"])

        run_coro(make_request())
