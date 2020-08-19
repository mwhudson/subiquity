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
from subiquity.common.api.defs import api, simple_endpoint


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
            endpoint = simple_endpoint(str)

        gets = []
        posts = []

        async def getter(path):
            gets.append(path)
            return {'result': 'value'}

        async def poster(path, *, json):
            posts.append((path, json))
            return {'result': None}

        client = make_client(API, getter, poster)

        r = extract(client.endpoint.get())
        self.assertEqual(r, 'value')
        self.assertEqual(gets, ['/endpoint'])

        r = extract(client.endpoint.post('value'))
        self.assertEqual(r, None)
        self.assertEqual(posts, [('/endpoint', {'data': 'value'})])

    def test_args(self):

        @api
        class API:
            class endpoint:
                path = 'arg{arg}'

                def get(self):
                    pass

        gets = []

        async def getter(path):
            gets.append(path)
            return {'result': 'value'}

        client = make_client(API, getter, None)

        r = extract(client.endpoint.get(arg='v'))
        self.assertEqual(r, 'value')
        self.assertEqual(gets, ['/argv'])
