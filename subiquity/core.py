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
import sys
import traceback

import apport
import apport.hookutils
import apport.fileutils

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
        self._apport_files = []

    def run(self):
        try:
            super().run()
        except Exception:
            print("making crash report")
            path = self.make_apport_report("Installer UI")
            print("crash report at", path)
            print("press enter to continue")
            input()

    def _network_change(self):
        self.signal.emit_signal('snapd-network-change')

    def _proxy_set(self):
        self.run_in_bg(
            lambda: self.snapd_connection.configure_proxy(
                self.base_model.proxy),
            lambda fut: (
                fut.result(), self.signal.emit_signal('snapd-network-change')),
            )

    def note_file_for_apport(self, key, path):
        self._apport_files.append((key, path))

    def make_apport_report(self, thing):
        pr = apport.Report('Bug')

        # Add basic info to report.
        pr.add_proc_info()
        pr.add_os_info()
        pr.add_hooks_info(None)
        apport.hookutils.attach_hardware(pr)

        exc_info = sys.exc_info()
        pr['Title'] = "{} crashed with {}".format(thing, exc_info[0].__name__)
        pr['Traceback'] = "".join(traceback.format_exception(*exc_info))

        # Attach any files other parts of the code think we should know about.
        for key, path in self._apport_files:
            apport.hookutils.attach_file_if_exists(pr, path, key)

        # Because apport-cli will in general be run on a different
        # machine, we make some slightly obscure alterations to the
        # report to make this go better.

        # If ExecutableTimestamp is present, apport-cli will try to check that
        # ExecutablePath hasn't changed. But it won't be there.
        del pr['ExecutableTimestamp']
        # apport-cli gets upset at the probert C extensions it sees in here.
        # /proc/maps is very unlikely to be interesting for us anyway.
        del pr['ProcMaps']

        # apport-cli gets upset if neither of these are present.
        pr['Package'] = 'subiquity'
        pr['SourcePackage'] = 'subiquity'

        # Report to the subiquity project on Launchpad.
        crashdb = {
            'impl': 'launchpad',
            'project': 'subiquity',
            }
        if self.opts.dry_run:
            crashdb['launchpad_instance'] = 'staging'
        pr['CrashDB'] = repr(crashdb)

        # Write the log file to disk.
        i = 0
        crash_dir = os.path.join(self.base_model.root, 'var/log/crash')
        os.makedirs(crash_dir, exist_ok=True)
        while 1:
            try:
                path = os.path.join(crash_dir, "installer.{}.crash".format(i))
                f = open(path, 'xb')
            except FileExistsError:
                i += 1
                continue
            else:
                break
        with f:
            pr.write(f)
        return path
