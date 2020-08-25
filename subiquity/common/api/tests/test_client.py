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

import unittest

from subiquity.common.api.client import make_client
from subiquity.common.api.defs import api, Payload


def extract(c):
    try:
        c.__await__().send(None)
    except StopIteration as s:
        return s.value
    else:
        raise AssertionError("coroutine not done")


class TestClient(unittest.TestCase):

    def test_simple(self):

        @api
        class API:
            class endpoint:
                def GET() -> str: ...
                def POST(data: Payload[str]): ...

        async def make_request(method, path, *, params, json):
            requests.append((method, path, params, json))
            if method == "GET":
                return {'result': 'value'}
            else:
                return {'result': None}

        client = make_client(API, make_request)

        requests = []
        r = extract(client.endpoint.GET())
        self.assertEqual(r, 'value')
        self.assertEqual(requests, [("GET", '/endpoint', {}, None)])

        requests = []
        r = extract(client.endpoint.POST('value'))
        self.assertEqual(r, None)
        self.assertEqual(
            requests, [("POST", '/endpoint', {}, {'data': 'value'})])

    def test_args(self):

        @api
        class API:
            def GET(arg: str): ...

        async def make_request(method, path, *, params, json):
            requests.append((method, path, params, json))
            return {'result': params['arg']}

        client = make_client(API, make_request)

        requests = []
        r = extract(client.GET(arg='v'))
        self.assertEqual(r, '"v"')
        self.assertEqual(requests, [("GET", '/', {'arg': '"v"'}, None)])
