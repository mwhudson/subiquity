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

import logging
import os
import shlex
import sys
import traceback

from aiohttp import web

import jsonschema

import yaml

from subiquitycore.async_helpers import (
    run_in_thread,
    schedule_task,
    )
from subiquitycore.core import Application
from subiquitycore.snapd import (
    AsyncSnapd,
    FakeSnapdConnection,
    SnapdConnection,
    )

from subiquity.common.errorreport import (
    ErrorReporter,
    ErrorReportKind,
    )
from subiquity.models.subiquity import SubiquityModel


log = logging.getLogger('subiquity.core')


class Subiquity(Application):

    snapd_socket_path = '/run/snapd.socket'

    base_schema = {
        'type': 'object',
        'properties': {
            'version': {
                'type': 'integer',
                'minimum': 1,
                'maximum': 1,
                },
            },
        'required': ['version'],
        'additionalProperties': True,
        }

    from subiquity.server import controllers as controllers_mod
    project = "subiquity"

    def make_model(self):
        root = '/'
        if self.opts.dry_run:
            root = os.path.abspath('.subiquity')
        return SubiquityModel(root, self.opts.sources)

    controllers = [
        "Early",
        "Reporting",
        "Error",
        "Userdata",
        "Package",
        "Debconf",
        "Welcome",
        "Refresh",
        "Keyboard",
        ## "Zdev",
        ## "Network",
        ## "Proxy",
        ## "Mirror",
        ## "Filesystem",
        ## "Identity",
        ## "SSH",
        ## "SnapList",
        ## "InstallProgress",
        ## "Late",
        ## "Reboot",
    ]

    def __init__(self, opts, block_log_dir):
        super().__init__(opts)
        self.event_listeners = []
        self.block_log_dir = block_log_dir
        self.kernel_cmdline = shlex.split(opts.kernel_cmdline)
        if opts.snaps_from_examples:
            connection = FakeSnapdConnection(
                os.path.join(
                    os.path.dirname(
                        os.path.dirname(
                            os.path.dirname(__file__))),
                    "examples", "snaps"),
                self.scale_factor)
        else:
            connection = SnapdConnection(self.root, self.snapd_socket_path)
        self.snapd = AsyncSnapd(connection)
        self.signal.connect_signals([
            ('network-proxy-set', lambda: schedule_task(self._proxy_set())),
            ('network-change', self._network_change),
            ])

        self.autoinstall_config = {}
        self.error_reporter = ErrorReporter(
            self.context.child("ErrorReporter"), self.opts.dry_run, self.root)

        self.note_data_for_apport("SnapUpdated", str(self.updated))

        self.install_confirmed = False

    def restart(self, remove_last_screen=True):
        XXX

    def load_autoinstall_config(self):
        with open(self.opts.autoinstall) as fp:
            self.autoinstall_config = yaml.safe_load(fp)
        self.controllers.load("Reporting")
        self.controllers.Reporting.start()
        self.controllers.load("Error")
        with self.context.child("core_validation", level="INFO"):
            jsonschema.validate(self.autoinstall_config, self.base_schema)
        self.controllers.load("Early")
        if self.controllers.Early.cmds:
            stamp_file = self.state_path("early-commands")
            if not os.path.exists(stamp_file):
                self.aio_loop.run_until_complete(
                    self.controllers.Early.run())
                self.new_event_loop()
                open(stamp_file, 'w').close()
            with open(self.opts.autoinstall) as fp:
                self.autoinstall_config = yaml.safe_load(fp)
            with self.context.child("core_validation", level="INFO"):
                jsonschema.validate(self.autoinstall_config, self.base_schema)
            for controller in self.controllers.instances:
                controller.setup_autoinstall()

    async def _root(self, request):
        return web.json_response({
            'interactive': self.interactive(),
            })

    async def start_serving(self):
        app = web.Application()
        app['app'] = self
        app.router.add_get('/', self._root)
        for c in self.controllers.instances:
            c.add_routes(app)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.UnixSite(runner, ".subiquity/run/subiquity/socket")
        await site.start()

    def run(self):
        try:
            if self.opts.autoinstall is not None:
                self.load_autoinstall_config()
                if not self.interactive() and not self.opts.dry_run:
                    open('/run/casper-no-prompt', 'w').close()
            self.aio_loop.create_task(self.start_serving())
            super().run()
        except Exception:
            print("generating crash report")
            try:
                report = self.make_apport_report(
                    ErrorReportKind.DAEMON, "Installer Daemon", wait=True)
                if report is not None:
                    print("report saved to {path}".format(path=report.path))
            except Exception:
                print("report generation failed")
                traceback.print_exc()
            Error = getattr(self.controllers, "Error", None)
            if Error is not None and Error.cmds:
                self.new_event_loop()
                self.aio_loop.run_until_complete(Error.run())
            raise

    def add_event_listener(self, listener):
        self.event_listeners.append(listener)

    def report_start_event(self, context, description):
        for listener in self.event_listeners:
            listener.report_start_event(context, description)

    def report_finish_event(self, context, description, status):
        for listener in self.event_listeners:
            listener.report_finish_event(context, description, status)

    def confirm_install(self):
        self.install_confirmed = True
        self.controllers.InstallProgress.confirmation.set()

    def _cancel_show_progress(self):
        if self.show_progress_handle is not None:
            self.ui.block_input = False
            self.show_progress_handle.cancel()
            self.show_progress_handle = None

    def interactive(self):
        if not self.autoinstall_config:
            return True
        return bool(self.autoinstall_config.get('interactive-sections'))

    async def _apply(self, controller):
        await controller.apply_autoinstall_config()
        controller.autoinstall_applied = True
        controller.configured()
        self.next_screen()

    def _network_change(self):
        self.signal.emit_signal('snapd-network-change')

    async def _proxy_set(self):
        await run_in_thread(
            self.snapd.connection.configure_proxy, self.base_model.proxy)
        self.signal.emit_signal('snapd-network-change')

    def note_file_for_apport(self, key, path):
        self.error_reporter.note_file_for_apport(key, path)

    def note_data_for_apport(self, key, value):
        self.error_reporter.note_data_for_apport(key, value)

    def make_apport_report(self, kind, thing, *, wait=False, **kw):
        return self.error_reporter.make_apport_report(
            kind, thing, wait=wait, **kw)

    def make_autoinstall(self):
        config = {'version': 1}
        for controller in self.controllers.instances:
            controller_conf = controller.make_autoinstall()
            if controller_conf:
                config[controller.autoinstall_key] = controller_conf
        return config


if __name__ == '__main__':
    from subiquity.cmd.tui import parse_options
    logger = logging.getLogger('')
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s:%(lineno)d %(message)s"))
    logger.addHandler(handler)
    opts = parse_options(['--dry-run', '--snaps-from-examples'])
    Subiquity(opts, '').run()
