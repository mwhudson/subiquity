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
import logging

import aiohttp

from subiquity.client.asyncapp import AsyncTuiApplication
from subiquity.common.api.client import make_client
from subiquity.common.api.definition import API


log = logging.getLogger('subiquity.client.client')


class SubiquityClient(AsyncTuiApplication):

    def __init__(self, opts):
        super().__init__(opts)
        self.conn = aiohttp.UnixConnector(path=opts.socket)
        self.client = make_client(API, self.get, self.post)

    @contextlib.asynccontextmanager
    async def session(self):
        async with aiohttp.ClientSession(
                connector=self.conn, connector_owner=False) as session:
            yield session

    async def get(self, path):
        async with self.session() as session:
            async with session.get('http://a' + path) as resp:
                return await resp.json()

    async def post(self, path, *, json):
        async with self.session() as session:
            async with session.post('http://a' + path, json=json) as resp:
                return await resp.json()

    async def connect(self):
        print("connecting...", end='', flush=True)
        while True:
            try:
                state = await self.client.status.get()
            except aiohttp.ClientError:
                await asyncio.sleep(1)
                print(".", end='', flush=True)
            else:
                print()
                break
        print(state.status)
        self.aio_loop.stop()

    async def shutdown(self):
        await self.conn.close()
        await self.aio_loop.shutdown_asyncgens()

    def run(self):
        self.aio_loop.create_task(self.connect())
        try:
            super().run()
        finally:
            self.aio_loop.run_until_complete(self.shutdown())
