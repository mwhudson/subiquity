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

        async def getter(path, params):
            async with client.get(path, params=params) as resp:
                return await resp.json()

        async def poster(path, *, json, params):
            async with client.post(path, json=json, params=params) as resp:
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
            def get(arg1: str, arg2: str): pass

        class Impl(TestControllerBase):
            async def get(self, arg1, arg2):
                return '{}+{}'.format(arg1, arg2)

        async def make_request():
            async with makeE2EClient(API, Impl()) as client:
                self.assertEqual(
                    await client.get(arg1="A", arg2="B"), 'A+B')

        run_coro(make_request())

    def test_defaults(self):
        @api
        class API:
            def get(arg1: str, arg2: str = "arg2"): pass

        class Impl(TestControllerBase):
            async def get(self, arg1, arg2):
                return '{}+{}'.format(arg1, arg2)

        async def make_request():
            async with makeE2EClient(API, Impl()) as client:
                self.assertEqual(
                    await client.get(arg1="A", arg2="B"), 'A+B')
                self.assertEqual(
                    await client.get(arg1="A"), 'A+arg2')

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
                def post(data: In) -> Out: pass

        class Impl(TestControllerBase):
            async def doubler_post(self, data: In) -> Out:
                return Out(doubled=data.val*2)

        async def make_request():
            async with makeE2EClient(API, Impl()) as client:
                out = await client.doubler.post(In(3))
                self.assertEqual(out.doubled, 6)

        run_coro(make_request())
