# Copyright 2015 Canonical, Ltd.
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
import os

from subiquitycore.context import (
    Context,
    )
from subiquitycore.controllerset import ControllerSet
from subiquitycore.signals import Signal

log = logging.getLogger('subiquitycore.core')


class Application:

    # A concrete subclass must set project and controllers attributes, e.g.:
    #
    # project = "subiquity"
    # controllers = [
    #         "Welcome",
    #         "Network",
    #         "Filesystem",
    #         "Identity",
    #         "InstallProgress",
    # ]
    # The 'next_screen' and 'prev_screen' methods move through the list of
    # controllers in order, calling the make_ui method on the controller
    # instance.

    def __init__(self, opts):
        self._exc = None
        self.debug_flags = ()
        if opts.dry_run:
            # Recognized flags are:
            #  - install-fail: makes curtin install fail by replaying curtin
            #    events from a failed installation, see
            #    subiquity/controllers/installprogress.py
            #  - bpfail-full, bpfail-restricted: makes block probing fail, see
            #    subiquitycore/prober.py
            #  - copy-logs-fail: makes post-install copying of logs fail, see
            #    subiquity/controllers/installprogress.py
            self.debug_flags = os.environ.get('SUBIQUITY_DEBUG', '').split(',')
            log.debug("debug_flags: %r", self.debug_flags)

        self.opts = opts
        opts.project = self.project

        self.root = '/'
        if opts.dry_run:
            self.root = '.subiquity'
        self.state_dir = os.path.join(self.root, 'run', self.project)
        os.makedirs(self.state_path('states'), exist_ok=True)

        self.scale_factor = float(
            os.environ.get('SUBIQUITY_REPLAY_TIMESCALE', "1"))
        self.updated = os.path.exists(self.state_path('updating'))
        self.signal = Signal()
        self.aio_loop = asyncio.get_event_loop()
        self.aio_loop.set_exception_handler(self._exception_handler)
        self.controllers = ControllerSet(
            self.controllers_mod, self.controllers, init_args=(self,))
        self.context = Context.new(self)

    def _exception_handler(self, loop, context):
        exc = context.get('exception')
        if exc:
            loop.stop()
            self._exc = exc
        else:
            loop.default_exception_handler(context)

    def _connect_base_signals(self):
        """Connect signals used in the core controller."""
        # Registers signals from each controller
        for controller in self.controllers.instances:
            controller.register_signals()
        log.debug("known signals: %s", self.signal.known_signals)

    def state_path(self, *parts):
        return os.path.join(self.state_dir, *parts)

    def report_start_event(self, context, description):
        log = logging.getLogger(context.full_name())
        level = getattr(logging, context.level)
        log.log(level, "start: %s", description)

    def report_finish_event(self, context, description, status):
        log = logging.getLogger(context.full_name())
        level = getattr(logging, context.level)
        log.log(level, "finish: %s %s", description, status.name)

# EventLoop -------------------------------------------------------------------

    def exit(self):
        self.aio_loop.stop()

    def start_controllers(self):
        log.debug("starting controllers")
        for controller in self.controllers.instances:
            controller.start()
        log.debug("controllers started")

    async def start(self):
        self.controllers.load_all()
        self._connect_base_signals()
        self.start_controllers()

    def run(self):
        self.base_model = self.make_model()
        self.aio_loop.create_task(self.start())
        self.aio_loop.run_forever()
        if self._exc:
            exc, self._exc = self._exc, None
            raise exc
