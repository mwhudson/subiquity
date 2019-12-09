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
from concurrent.futures import Future
import contextlib
import datetime
import logging
import os
import re
import subprocess
import sys
import platform
import tempfile
import traceback

from curtin.commands.install import (
    ERROR_TARFILE,
    INSTALL_LOG,
    )

import urwid

from systemd import journal

import yaml

from subiquitycore import utils
from subiquitycore.controller import BaseController

from subiquity.async_helpers import (
    run_in_thread,
    schedule_task,
    )
from subiquity.controllers.error import ErrorReportKind
from subiquity.ui.views.installprogress import ProgressView


log = logging.getLogger("subiquitycore.controller.installprogress")


class InstallState:
    NOT_STARTED = 0
    RUNNING = 1
    DONE = 2
    ERROR = -1


task_counter = 0


def task(f=None, transitions=None, **kw):
    """Annotate a method as a task to be used with StateMachine.

    If the method's name starts with _bg_ it is run in a background thread.
    (This ability to have tasks flip between running in the foreground and
    background is what makes all this interesting).

    Annotated methods have various attributes:

      ._name -- the name of the state, which is the name of the method with
                _bg_ stripped off if it was there.
      ._is_bg -- indicates if this method should run in a background thread.
      ._transitions -- transitions from this state to another, mapping
                       transition name to the following state. The transition
                       named 'success' is special -- it is what is followed
                       when the function returns, unless some other transition
                       has been followed beforehand.
      ._extra -- any extra keyword arguments passed to @task()
    """
    if transitions is None:
        transitions = {}

    def annotate(f):
        global task_counter
        f._is_task = True
        f._order = task_counter
        task_counter += 1
        if f.__name__.startswith("_bg_"):
            f._name = f.__name__[4:]
            f._is_bg = True
        else:
            f._name = f.__name__
            f._is_bg = False
        f._transitions = transitions
        f._extra = kw
        return f

    if f is not None:
        return annotate(f)
    else:
        return annotate


def collect_tasks(inst, filter_task=lambda f: True):
    """Collect the methods on inst annotated with @task.

    Returns a list of tuples (method, transitions) where method is the
    annotated method and transitions are the transitions defined while
    method is running, with 'success' automatically filled in as a
    transition to the next state if not otherwise defined.
    """
    task_funcs = []
    attrs = inst.__class__.__dict__.values()
    for a in attrs:
        if not hasattr(a, "_is_task"):
            continue
        if filter_task(a):
            task_funcs.append(getattr(inst, a.__name__))
    task_funcs.sort(key=lambda f: f._order)
    r = []
    for i, func in enumerate(task_funcs[:-1]):
        transitions = func._transitions.copy()
        if 'success' not in transitions:
            transitions['success'] = task_funcs[i+1]._name
        r.append((func, transitions))
    r.append((task_funcs[-1], task_funcs[-1]._transitions.copy()))
    return r


class StateMachine:
    """Run tasks as returned by collect_tasks."""

    def __init__(self, controller, task_funcs):
        self.controller = controller
        self._tasks = {}
        self._results = {}
        self._transitions = {}
        self._subscribers = {}

        for func, transitions in task_funcs:
            self._tasks[func._name] = func
            self._transitions[func._name] = transitions
            self.subscribe(
                func._name,
                lambda fut, name=func._name: self._task_complete(name, fut))

        self.cur = task_funcs[0][0]._name

    def subscribe(self, name, subscriber):
        if name in self._results:
            subscriber(self._results[name])
        else:
            self._subscribers.setdefault(name, set()).add(subscriber)

    def _task_complete(self, name, fut):
        if name != self.cur:
            log.debug(
                "_task_complete ignoring %s as %s != %s", fut, name, self.cur)
            return
        try:
            fut.result()
        except urwid.ExitMainLoop:
            raise
        except Exception:
            log.debug("%s failed", name)
            self.controller.curtin_error()
        else:
            log.debug("%s completed", name)
            if 'success' in self._transitions[name]:
                self.transition('success')
            else:
                log.debug("all tasks completed")

    def run(self):
        log.debug("running task %s", self.cur)
        func = self._tasks[self.cur]

        def end(fut):
            log.debug('_end %s %s', func._name, fut)
            self._results[func._name] = fut
            if 'label' in func._extra:
                self.controller._install_event_finish()
            for subscriber in self._subscribers.get(func._name, ()):
                subscriber(fut)

        if 'label' in func._extra:
            self.controller._install_event_start(func._extra['label'])

        if func._is_bg:
            self.controller.run_in_bg(func, end)
        else:
            fut = Future()
            try:
                fut.set_result(func())
            except urwid.ExitMainLoop:
                raise
            except Exception as e:
                fut.set_exception(e)
            end(fut)

    def transition(self, name):
        """Follow the named transition for the current state."""
        new = self._transitions[self.cur][name]
        log.debug("transition %s: %s -> %s", name, self.cur, new)
        self.cur = new
        self.run()


class TracebackExtractor:

    start_marker = re.compile(r"^Traceback \(most recent call last\):")
    end_marker = re.compile(r"\S")

    def __init__(self):
        self.traceback = []
        self.in_traceback = False

    def feed(self, line):
        if not self.traceback and self.start_marker.match(line):
            self.in_traceback = True
        elif self.in_traceback and self.end_marker.match(line):
            self.traceback.append(line)
            self.in_traceback = False
        if self.in_traceback:
            self.traceback.append(line)


class InstallProgressController(BaseController):
    signals = [
        ('installprogress:filesystem-config-done', 'filesystem_config_done'),
        ('installprogress:identity-config-done',   'identity_config_done'),
        ('installprogress:ssh-config-done',        'ssh_config_done'),
        ('installprogress:snap-config-done',       'snap_config_done'),
    ]

    def __init__(self, app):
        super().__init__(app)
        self.model = app.base_model
        self.answers.setdefault('reboot', False)
        self.progress_view = None
        self.install_state = InstallState.NOT_STARTED
        self.journal_listener_handle = None
        self.filesystem_event = asyncio.Event()
        self.reboot_clicked = asyncio.Event()
        self._postinstall_prerequisites = {
            'ssh': asyncio.Event(),
            'identity': asyncio.Event(),
            'snap': asyncio.Event(),
            }
        self.uu_running = False
        self._event_indent = ""
        self._event_syslog_identifier = 'curtin_event.%s' % (os.getpid(),)
        self._log_syslog_identifier = 'curtin_log.%s' % (os.getpid(),)
        self.sm = None
        self.tb_extractor = TracebackExtractor()

    def start(self):
        schedule_task(self.install())

    def interactive(self):
        if not self.app.autoinstall_config:
            return True
        return bool(self.app.autoinstall_config.get('interactive-sections'))

    def tpath(self, *path):
        return os.path.join(self.model.target, *path)

    def filesystem_config_done(self):
        self.filesystem_event.set()

    def _step_done(self, step):
        self._postinstall_prerequisites[step].set()

    def identity_config_done(self):
        self._step_done('identity')

    def ssh_config_done(self):
        self._step_done('ssh')

    def snap_config_done(self):
        self._step_done('snap')

    def curtin_error(self):
        self.install_state = InstallState.ERROR
        kw = {}
        if self.tb_extractor.traceback:
            kw["Traceback"] = "\n".join(self.tb_extractor.traceback)
        crash_report = self.app.make_apport_report(
            ErrorReportKind.INSTALL_FAIL, "install failed", interrupt=False,
            **kw)
        self.progress_view.spinner.stop()
        if sys.exc_info()[0] is not None:
            self.progress_view.add_log_line(traceback.format_exc())
        self.progress_view.set_status(('info_error',
                                       _("An error has occurred")))
        self.start_ui()
        self.progress_view.show_error(crash_report)

    def _bg_run_command_logged(self, cmd, **kwargs):
        return utils.run_command(self.logged_command(cmd), **kwargs)

    def logged_command(self, cmd):
        return ['systemd-cat', '--level-prefix=false',
               '--identifier=' + self._log_syslog_identifier] + cmd

    def _journal_event(self, event):
        if event['SYSLOG_IDENTIFIER'] == self._event_syslog_identifier:
            self.curtin_event(event)
        elif event['SYSLOG_IDENTIFIER'] == self._log_syslog_identifier:
            self.curtin_log(event)

    def _install_event_start(self, message):
        log.debug("_install_event_start %s", message)
        self.progress_view.add_event(self._event_indent + message)
        self._event_indent += "  "
        self.progress_view.spinner.start()

    def _install_event_finish(self):
        self._event_indent = self._event_indent[:-2]
        log.debug("_install_event_finish %r", self._event_indent)
        self.progress_view.spinner.stop()

    def curtin_event(self, event):
        e = {}
        for k, v in event.items():
            if k.startswith("CURTIN_"):
                e[k] = v
        log.debug("curtin_event received %r", e)
        event_type = event.get("CURTIN_EVENT_TYPE")
        if event_type not in ['start', 'finish']:
            return
        if event_type == 'start':
            self._install_event_start(event.get("CURTIN_MESSAGE", "??"))
        if event_type == 'finish':
            self._install_event_finish()

    def curtin_log(self, event):
        log_line = event['MESSAGE']
        self.progress_view.add_log_line(log_line)
        self.tb_extractor.feed(log_line)

    def start_journald_listener(self, identifiers, callback):
        reader = journal.Reader()
        args = []
        for identifier in identifiers:
            args.append("SYSLOG_IDENTIFIER={}".format(identifier))
        reader.add_match(*args)

        def watch():
            if reader.process() != journal.APPEND:
                return
            for event in reader:
                callback(event)
        loop = asyncio.get_event_loop()
        return loop.add_reader(reader.fileno(), watch)

    def _write_config(self, path, config):
        with open(path, 'w') as conf:
            datestr = '# Autogenerated by SUbiquity: {} UTC\n'.format(
                str(datetime.datetime.utcnow()))
            conf.write(datestr)
            conf.write(yaml.dump(config))

    def _get_curtin_command(self):
        config_file_name = 'subiquity-curtin-install.conf'

        if self.opts.dry_run:
            config_location = os.path.join('.subiquity/', config_file_name)
            log_location = '.subiquity/install.log'
            event_file = "examples/curtin-events.json"
            if 'install-fail' in self.debug_flags:
                event_file = "examples/curtin-events-fail.json"
            curtin_cmd = [
                "python3", "scripts/replay-curtin-log.py", event_file,
                self._event_syslog_identifier, log_location,
                ]
        else:
            config_location = os.path.join('/var/log/installer',
                                           config_file_name)
            curtin_cmd = [sys.executable, '-m', 'curtin', '--showtrace', '-c',
                          config_location, 'install']
            log_location = INSTALL_LOG

        ident = self._event_syslog_identifier
        self._write_config(config_location,
                           self.model.render(syslog_identifier=ident))

        self.app.note_file_for_apport("CurtinConfig", config_location)
        self.app.note_file_for_apport("CurtinLog", log_location)
        self.app.note_file_for_apport("CurtinErrors", ERROR_TARFILE)

        return curtin_cmd

    async def curtin_install(self):
        log.debug('curtin_install')
        self.install_state = InstallState.RUNNING
        self.progress_view = ProgressView(self)

        self.journal_listener_handle = self.start_journald_listener(
            [self._event_syslog_identifier, self._log_syslog_identifier],
            self._journal_event)

        curtin_cmd = self._get_curtin_command()

        log.debug('curtin install cmd: {}'.format(curtin_cmd))

        cp = await utils.arun_command(
            self.logged_command(curtin_cmd), check=True)

        log.debug('curtin_install completed: %s', cp.returncode)

        self.install_state = InstallState.DONE
        log.debug('After curtin install OK')

    def cancel(self):
        pass

    async def install(self):

        await self.filesystem_event.wait()

        await self.curtin_install()

        await asyncio.wait(
            {e.wait() for e in self._postinstall_prerequisites.values()})

        @contextlib.contextmanager
        def install_event(label):
            self._install_event_start(label)
            try:
                yield
            finally:
                self._install_event_finish()

        await self.drain_curtin_events()
        with install_event("final system configuration"):
            with install_event("configuring cloud-init"):
                await run_in_thread(self.model.configure_cloud_init)
            if self.model.ssh.install_server:
                with install_event("installing openssh"):
                    await self.install_openssh()
            with install_event("restoring apt configuration"):
                await self.restore_apt_config()
        self.ui.set_header(_("Installation complete!"))
        self.progress_view.set_status(_("Finished install!"))
        self.progress_view.show_complete()
        if self.model.network.has_network:
            self.progress_view.update_running()
            with install_event("downloading and installing security updates"):
                await self.run_uu()
            self.progress_view.update_done()
        with install_event("copying logs to installed system"):
            await self.copy_logs_to_target()

        if not self.answers['reboot']:
            await self.reboot_clicked.wait()

        self.reboot()

    def start_postinstall_configuration(self):
        has_network = self.model.network.has_network

        def filter_task(func):
            if func._extra.get('net_only') and not has_network:
                return False
            if func._name == 'install_openssh' \
               and not self.model.ssh.install_server:
                return False
            return True

        log.debug("starting state machine")
        self.sm = StateMachine(self, collect_tasks(self, filter_task))
        self.sm.run()

    async def drain_curtin_events(self):
        waited = 0.0
        while self._event_indent and waited < 5.0:
            await asyncio.sleep(0.1)
            waited += 0.1
        log.debug("waited %s seconds for events to drain", waited)

    async def install_openssh(self):
        if self.opts.dry_run:
            cmd = ["sleep", str(2/self.app.scale_factor)]
        else:
            cmd = [
                sys.executable, "-m", "curtin", "system-install", "-t",
                "/target",
                "--", "openssh-server",
                ]
        await utils.arun_command(self.logged_command(cmd), check=True)

    async def restore_apt_config(self):
        if self.opts.dry_run:
            cmds = [["sleep", str(1/self.app.scale_factor)]]
        else:
            cmds = [
                ["umount", self.tpath('etc/apt')],
                ]
            if self.model.network.has_network:
                cmds.append([
                    sys.executable, "-m", "curtin", "in-target", "-t",
                    "/target", "--", "apt-get", "update",
                    ])
            else:
                cmds.append(["umount", self.tpath('var/lib/apt/lists')])
        for cmd in cmds:
            await utils.arun_command(self.logged_command(cmd), check=True)

    async def run_uu(self):
        target_tmp = os.path.join(self.model.target, "tmp")
        os.makedirs(target_tmp, exist_ok=True)
        apt_conf = tempfile.NamedTemporaryFile(
            dir=target_tmp, delete=False, mode='w')
        apt_conf.write(uu_apt_conf)
        apt_conf.close()
        env = os.environ.copy()
        env["APT_CONFIG"] = apt_conf.name[len(self.model.target):]
        if self.opts.dry_run:
            pass
            await utils.arun_command(self.logged_command([
                "sleep", "5"]), env=env, check=True)
        else:
            await utils.arun_command(self.logged_command([
                sys.executable, "-m", "curtin", "in-target", "-t", "/target",
                "--", "unattended-upgrades", "-v",
                ]), env=env, check=True)
        os.remove(apt_conf.name)

    async def stop_uu(self):
        await utils.arun_command(self.logged_command([
                'chroot', '/target',
                '/usr/share/unattended-upgrades/unattended-upgrade-shutdown',
                '--stop-only',
                ], check=True))

    async def copy_logs_to_target(self):
        if self.opts.dry_run:
            if 'copy-logs-fail' in self.debug_flags:
                raise PermissionError()
            return
        target_logs = self.tpath('var/log/installer')
        await utils.arun_command(['cp', '-aT', '/var/log/installer', target_logs])
        try:
            with open(os.path.join(target_logs,
                                   'installer-journal.txt'), 'w') as output:
                await utils.arun_command(
                    ['journalctl'],
                    stdout=output, stderr=subprocess.STDOUT)
        except Exception:
            log.exception("saving journal failed")

    def reboot(self):
        if self.opts.dry_run:
            log.debug('dry-run enabled, skipping reboot, quitting instead')
            self.signal.emit_signal('quit')
        else:
            # TODO Possibly run this earlier, to show a warning; or
            # switch to shutdown if chreipl fails
            if platform.machine() == 's390x':
                utils.run_command(["chreipl", "/target/boot"])
            # Should probably run curtin -c $CONFIG unmount -t TARGET first.
            utils.run_command(["/sbin/reboot"])

    async def _click_reboot(self):
        if self.uu_running:
            await self.stop_uu()
        self.reboot_clicked.set()

    def click_reboot(self):
        schedule_task(self._click_reboot())

    def quit(self):
        if not self.opts.dry_run:
            utils.disable_subiquity()
        self.signal.emit_signal('quit')

    def start_ui(self):
        if self.install_state == InstallState.RUNNING:
            self.progress_view.title = _("Installing system")
        elif self.install_state == InstallState.DONE:
            self.progress_view.title = _("Install complete!")
        elif self.install_state == InstallState.ERROR:
            self.progress_view.title = (
                _('An error occurred during installation'))
        self.ui.set_body(self.progress_view)


uu_apt_conf = """\
# Config for the unattended-upgrades run to avoid failing on battery power or
# a metered connection.
Unattended-Upgrade::OnlyOnACPower "false";
Unattended-Upgrade::Skip-Updates-On-Metered-Connections "true";
"""
