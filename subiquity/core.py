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

import logging
import os
import platform
import traceback

import apport, apport.hookutils, apport.fileutils

from subiquitycore.core import Application

from subiquity.models.subiquity import SubiquityModel
from subiquity.snapd import (
    FakeSnapdConnection,
    SnapdConnection,
    )


log = logging.getLogger('subiquity.core')


class Subiquity(Application):

    snapd_socket_path = '/run/snapd.socket'

    from subiquity.palette import COLORS, STYLES, STYLES_MONO

    project = "subiquity"

    def make_model(self):
        root = '/'
        if self.opts.dry_run:
            root = os.path.abspath('.subiquity')
        return SubiquityModel(root, self.opts.sources)

    controllers = [
            "Welcome",
            "Refresh",
            "Keyboard",
            "Zdev",
            "Network",
            "Proxy",
            "Mirror",
            "Refresh",
            "Filesystem",
            "Identity",
            "SSH",
            "SnapList",
            "InstallProgress",
    ]

    def __init__(self, ui, opts, block_log_dir):
        if not opts.bootloader == 'none' and platform.machine() != 's390x':
            self.controllers.remove("Zdev")

        super().__init__(ui, opts)
        self.ui.progress_completion += 1
        self.block_log_dir = block_log_dir
        if opts.snaps_from_examples:
            connection = FakeSnapdConnection(
                os.path.join(
                    os.path.dirname(
                        os.path.dirname(__file__)),
                    "examples", "snaps"))
        else:
            connection = SnapdConnection(self.root, self.snapd_socket_path)
        self.snapd_connection = connection
        self.signal.connect_signals([
            ('network-proxy-set', self._proxy_set),
            ('network-change', self._network_change),
            ])

    def _network_change(self):
        self.signal.emit_signal('snapd-network-change')

    def _proxy_set(self):
        self.run_in_bg(
            lambda: self.snapd_connection.configure_proxy(
                self.base_model.proxy),
            lambda fut: (
                fut.result(), self.signal.emit_signal('snapd-network-change')),
            )

    def _make_apport_report(self, title, exc_info):
        log.debug("_make_probe_failure_crash_file starting")
        pr = apport.Report('Bug')
        pr.add_proc_info()
        del pr['ExecutableTimestamp']
        del pr['ProcMaps']
        pr.add_os_info()
        pr.add_hooks_info(None)
        pr['Package'] = pr['SourcePackage'] = 'subiquity'
        pr['Title'] = title
        pr['Traceback'] = "".join(traceback.format_exception(*exc_info))
        pr['JournalErrors'] = apport.hookutils.command_output(
                ['journalctl', '-b', '--priority=warning', '--lines=1000'])
        pr['UdevDump'] = apport.hookutils.command_output(
                ['udevadm', 'info', '--export-db'])
        apport.hookutils.attach_file_if_exists(
            pr, os.path.join(self.block_log_dir, 'discover.log'), 'DiscoverLog')
        apport.hookutils.attach_hardware(pr)
        crashdb = {
            'impl': 'launchpad',
            'project': 'subiquity',
            }
        if self.app.opts.dry_run:
            crashdb['launchpad_instance'] = 'staging'
        pr['CrashDB'] = repr(crashdb)
        return pr

    def _write_apport_report(self, pr, file_pat):
        i = 0
        while 1:
            try:
                path = os.path.join(file_pat.format(i))
                f = open(path, 'xb')
            except FileExistsError:
                i += 1
                continue
            else:
                break
        with f:
            pr.write(f)
        return path
