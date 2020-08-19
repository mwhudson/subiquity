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
import contextlib
import unittest

from subiquity.common.api.client import make_client
from subiquity.common.api.defs import api

from .test_server import (
    makeTestClient,
    run_coro,
    TestControllerBase,
    )


@contextlib.asynccontextmanager
async def makeE2EClient(api, impl):
    async with makeTestClient(api, impl) as client:

        async def getter(path):
            async with client.get(path) as resp:
                return await resp.json()

        async def poster(path, *, json):
            async with client.post(path, json=json) as resp:
                return await resp.json()

        yield make_client(api, getter, poster)


class TestEndToEnd(unittest.TestCase):

    def test_simple(self):
        @api
        class API:
            def get() -> str: pass

        class Impl(TestControllerBase):
            async def get(self):
                return 'value'

        async def make_request():
            async with makeE2EClient(API, Impl()) as client:
                self.assertEqual(await client.get(), 'value')

        run_coro(make_request())

    def test_nested(self):
        @api
        class API:
            class endpoint:
                class nested:
                    def get() -> str: pass

        class Impl(TestControllerBase):
            async def endpoint_nested_get(self):
                return 'value'

        async def make_request():
            async with makeE2EClient(API, Impl()) as client:
                self.assertEqual(await client.endpoint.nested.get(), 'value')

        run_coro(make_request())

    def test_args(self):
        @api
        class API:
            class e1:
                path = '{arg1}'

                class e2:
                    path = '{arg2}'
                    def get(): pass

        class Impl(TestControllerBase):
            async def e1_e2_get(self, request):
                return '{}+{}'.format(
                    request.match_info['arg1'], request.match_info['arg2'])

        async def make_request():
            async with makeE2EClient(API, Impl()) as client:
                self.assertEqual(
                    await client.e1.e2.get(arg1="A", arg2="B"), 'A+B')

        run_coro(make_request())

    def test_post(self):
        @api
        class API:
            def post(data): pass

        class Impl(TestControllerBase):
            async def post(self, data):
                return data['key']

        async def make_request():
            async with makeE2EClient(API, Impl()) as client:
                self.assertEqual(
                    await client.post({'key': 'value'}), 'value')

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
                def post(arg: In) -> Out: pass

        class Impl(TestControllerBase):
            async def doubler_post(self, arg: In) -> Out:
                return Out(doubled=arg.val*2)

        async def make_request():
            async with makeE2EClient(API, Impl()) as client:
                out = await client.doubler.post(In(3))
                self.assertEqual(out.doubled, 6)

        run_coro(make_request())
