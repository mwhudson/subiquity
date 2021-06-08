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
import concurrent.futures
import logging


log = logging.getLogger("subiquitycore.async_helpers")


def _done(fut):
    try:
        fut.result()
    except asyncio.CancelledError:
        pass


def schedule_task(coro, propagate_errors=True):
    loop = asyncio.get_event_loop()
    if asyncio.iscoroutine(coro):
        task = asyncio.Task(coro)
    else:
        task = coro
    if propagate_errors:
        task.add_done_callback(_done)
    loop.call_soon(asyncio.ensure_future, task)
    return task


async def run_in_thread(func, *args):
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, func, *args)
    except concurrent.futures.CancelledError:
        raise asyncio.CancelledError


class SingleInstanceTask:

    def __init__(self, func, propagate_errors=True):
        self.func = func
        self.propagate_errors = propagate_errors
        self.task = None

    async def _start(self, old):
        if old is not None:
            old.cancel()
            try:
                await old
            except BaseException:
                pass
        schedule_task(self.task, self.propagate_errors)

    async def start(self, *args, **kw):
        await self.start_sync(*args, **kw)
        return self.task

    def start_sync(self, *args, **kw):
        old = self.task
        coro = self.func(*args, **kw)
        if asyncio.iscoroutine(coro):
            self.task = asyncio.Task(coro)
        else:
            self.task = coro
        return schedule_task(self._start(old))

    async def wait(self):
        while True:
            try:
                return await self.task
            except asyncio.CancelledError:
                pass


class _AsyncChannelIter:

    def __init__(self):
        self._queue = asyncio.Queue()
        self._next_event = None
        self._events = set()

    def _send(self, e, v):
        self._events.add(e)
        self._queue.put_nowait((v, None))

    def _set(self):
        for e in self._events:
            e.set()
        self.events = set()

    def _stop(self):
        self._set()
        self._queue.put_nowait((None, StopAsyncIteration()))

    async def __anext__(self):
        self._set()
        v, e = await self._queue.get()
        if e is None:
            return v
        else:
            raise e


class _AsyncChannelSubscription:

    def __init__(self, channel):
        self.channel = channel
        self._it = None

    def __enter__(self):
        assert self._it is None
        self._it = _AsyncChannelIter()
        self.channel._iters.add(self._it)
        return self

    def __exit__(self, *args):
        assert self._it is not None
        self.channel._iters.remove(self._it)
        self._it._stop()
        self._it = None

    def __aiter__(self):
        return self._it


class AsyncChannel:

    def __init__(self):
        self._iters = set()
        self._tasks = set()

    def subscription(self):
        return _AsyncChannelSubscription(self)

    async def asend(self, value):
        waits = set()
        for it in self._iters:
            e = asyncio.Event()
            waits.add(e.wait())
            it._send(e, value)
        if waits:
            await asyncio.wait(waits)

    def send(self, value):
        self._tasks.add(
            asyncio.get_event_loop().create_task(self.asend(value)))

    async def close(self):
        for it in self._iters:
            it._stop()
        for t in self._tasks:
            await t


if __name__ == '__main__':

    async def c1(c):
        with c.subscription() as i:
            async for v in i:
                print('c1', v)
        print('c1 done')

    async def c2(c):
        with c.subscription() as i:
            async for v in i:
                print('c2', v)
                print('c2 waiting')
                await asyncio.sleep(1)
                print('c2 waited')
        print('c2 done')

    async def s(c):
        await asyncio.sleep(1)
        print('asending a')
        await c.asend('a')
        await asyncio.sleep(1)
        print('sending b')
        c.send('b')
        await asyncio.sleep(1)
        print('sending c')
        c.send('c')
        await asyncio.sleep(1)

    loop = asyncio.get_event_loop()

    async def main():
        c = AsyncChannel()
        loop.create_task(c1(c))
        loop.create_task(c2(c))
        await s(c)
        await c.close()

    loop.run_until_complete(main())
