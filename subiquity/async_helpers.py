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

import asyncio


def schedule_task(coro):
    loop = asyncio.get_event_loop()
    if asyncio.iscoroutine(coro):
        task = asyncio.Task(coro)
    else:
        task = coro
    loop.call_soon(asyncio.ensure_future, task)
    return task


async def run_in_thread(func, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args)


class SingleInstanceTask:

    def __init__(self):
        self.task = None

    async def start(self, coro):
        if self.task is not None:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        self.task = schedule_task(coro)

    def start_sync(self, coro):
        return schedule_task(self.start, coro)
