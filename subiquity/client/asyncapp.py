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
import logging

from subiquitycore.tui import TuiApplication
from subiquitycore.tuicontroller import Skip

log = logging.getLogger('subiquity.client.asyncapp')


MAX_BLOCK_TIME = 0.1
MIN_SHOW_PROGRESS_TIME = 1.0


class AsyncTuiApplication(TuiApplication):

    def __init__(self, opts):
        super().__init__(opts)
        self.show_progress_handle = None
        self.progress_min_wait = None

    async def set_body(self, view):
        self._cancel_show_progress()
        if self.progress_min_wait:
            await self.progress_min_wait
            self.progress_min_wait = None
        self.ui.set_body(view)

    def _show_progress(self):
        self.ui.block_input = False
        self.progress_min_wait = self.aio_loop.create_task(
            asyncio.sleep(MIN_SHOW_PROGRESS_TIME))
        self.progress_showing = True
        self.ui.set_body(self.progress_view())

    def progress_view(self):
        raise NotImplementedError(self.progress_view)

    def _cancel_show_progress(self):
        if self.show_progress_handle is not None:
            self.ui.block_input = False
            self.show_progress_handle.cancel()
            self.show_progress_handle = None
            self.progress_min_wait = None

    def move_screen(self, increment, coro):
        if self.show_progress_handle is None:
            self.ui.block_input = True
            self.show_progress_handle = self.aio_loop.call_later(
                MAX_BLOCK_TIME, self._show_progress)
        old, self.cur_screen = self.cur_screen, None
        if old is not None:
            old.context.exit("completed")
            old.end_ui()
        self.aio_loop.create_task(self._move_screen(increment, coro))

    async def _move_screen(self, increment, coro):
        if coro is not None:
            await coro
        cur_index = self.controllers.index
        while True:
            self.controllers.index += increment
            if self.controllers.index < 0:
                self.controllers.index = cur_index
                return
            if self.controllers.index >= len(self.controllers.instances):
                self.exit()
                return
            new = self.controllers.cur
            try:
                await self.select_screen(new)
            except Skip:
                log.debug("skipping screen %s", new.name)
                continue
            else:
                return

    def next_screen(self, coro=None):
        self.move_screen(1, coro)

    def prev_screen(self, coro=None):
        self.move_screen(-1, coro)

    async def select_screen(self, new):
        new.context.enter("starting UI")
        if self.opts.screens and new.name not in self.opts.screens:
            raise Skip
        try:
            await new.start_ui()
            self.cur_screen = new
        except Skip:
            new.context.exit("(skipped)")
            raise
        with open(self.state_path('last-screen'), 'w') as fp:
            fp.write(new.name)
