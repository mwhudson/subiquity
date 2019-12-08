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
import subprocess

import yaml

from probert.network import IFF_UP, NetworkEventReceiver

from subiquitycore.models.network import BondParameters, sanitize_config
from subiquitycore.ui.views.network import (
    NetworkView,
    )
from subiquitycore.controller import BaseController
from subiquitycore.utils import (
    arun_command,
    run_command,
    )
from subiquitycore.file_util import write_file
from subiquitycore import netplan

from subiquity.async_helpers import schedule_task


log = logging.getLogger("subiquitycore.controller.network")


class SubiquityNetworkEventReceiver(NetworkEventReceiver):
    def __init__(self, model):
        self.model = model
        self.view = None
        self.default_route_watchers = []
        self.default_routes = set()

    def new_link(self, ifindex, link):
        netdev = self.model.new_link(ifindex, link)
        if self.view is not None and netdev is not None:
            self.view.new_link(netdev)

    def del_link(self, ifindex):
        netdev = self.model.del_link(ifindex)
        if ifindex in self.default_routes:
            self.default_routes.remove(ifindex)
        if self.view is not None and netdev is not None:
            self.view.del_link(netdev)

    def update_link(self, ifindex):
        netdev = self.model.update_link(ifindex)
        if netdev is None:
            return
        if not (netdev.info.flags & IFF_UP) and ifindex in self.default_routes:
            self.default_routes.remove(ifindex)
            for watcher in self.default_route_watchers:
                watcher(self.default_routes)
        if self.view is not None:
            self.view.update_link(netdev)

    def route_change(self, action, data):
        super().route_change(action, data)
        if data['dst'] != 'default':
            return
        if data['table'] != 254:
            return
        ifindex = data['ifindex']
        if action == "NEW" or action == "CHANGE":
            self.default_routes.add(ifindex)
        elif action == "DEL" and ifindex in self.default_routes:
            self.default_routes.remove(ifindex)
        for watcher in self.default_route_watchers:
            watcher(self.default_routes)
        log.debug('default routes %s', self.default_routes)

    def add_default_route_watcher(self, watcher):
        self.default_route_watchers.append(watcher)
        watcher(self.default_routes)

    def remove_default_route_watcher(self, watcher):
        if watcher in self.default_route_watchers:
            self.default_route_watchers.remove(watcher)


default_netplan = '''
network:
  version: 2
  ethernets:
    "en*":
       addresses:
         - 10.0.2.15/24
       gateway4: 10.0.2.2
       nameservers:
         addresses:
           - 8.8.8.8
           - 8.4.8.4
         search:
           - foo
           - bar
    "eth*":
       dhcp4: true
  wifis:
    "wl*":
       dhcp4: true
       access-points:
         "some-ap":
            password: password
'''


class NetworkController(BaseController):

    autoinstall_key = 'network'

    root = "/"

    def __init__(self, app):
        self.model = app.base_model.network
        super().__init__(app)
        self.view = None
        self.view_shown = False
        self.apply_config_task = async_helpers.SingleInstanceTask()

        self._watching = False
        self.network_event_receiver = SubiquityNetworkEventReceiver(self.model)
        self.network_event_receiver.add_default_route_watcher(
            self.route_watcher)

        if self.opts.dry_run:
            self.root = os.path.abspath(".subiquity")
            netplan_path = self.netplan_path
            netplan_dir = os.path.dirname(netplan_path)
            if os.path.exists(netplan_dir):
                import shutil
                shutil.rmtree(netplan_dir)
            os.makedirs(netplan_dir)
            with open(netplan_path, 'w') as fp:
                fp.write(default_netplan)

        if not self.autoinstall_data:
            self.model.parse_netplan_configs(self.root)
        else:
            self.model.load_autoinstall(self.autoinstall_data)

    def load_autoinstall(self):
        pass

    async def apply_autoinstall_config(self):
        # oh boy
        # await self.apply_config(silent=True)
        pass

    def route_watcher(self, routes):
        if routes:
            self.signal.emit_signal('network-change')

    def start(self):
        self._observer_handles = []
        self.observer, self._observer_fds = (
            self.app.prober.probe_network(self.network_event_receiver))
        self.start_watching()

    def stop_watching(self):
        if not self._watching:
            return
        loop = asyncio.get_event_loop()
        for fd in self._observer_fds:
            loop.remove_reader(fd)
        self._watching = False

    def start_watching(self):
        if self._watching:
            return
        loop = asyncio.get_event_loop()
        for fd in self._observer_fds:
            loop.add_reader(self._data_ready, fd)
        self._watching = True

    def _data_ready(self, fd):
        cp = run_command(['udevadm', 'settle', '-t', '0'])
        if cp.returncode != 0:
            log.debug("waiting 0.1 to let udev event queue settle")
            self.stop_watching()
            loop = asyncio.get_event_loop()
            loop.call_later(0.1, self.start_watching)
            return
        self.observer.data_ready(fd)
        v = self.ui.body
        if hasattr(v, 'refresh_model_inputs'):
            v.refresh_model_inputs()

    def start_scan(self, dev):
        self.observer.trigger_scan(dev.ifindex)

    def done(self):
        log.debug("NetworkController.done next-screen")
        self.model.has_network = bool(
            self.network_event_receiver.default_routes)
        self.signal.emit_signal('next-screen')

    def cancel(self):
        self.signal.emit_signal('prev-screen')

    def _action_get(self, id):
        dev_spec = id[0].split()
        dev = None
        if dev_spec[0] == "interface":
            if dev_spec[1] == "index":
                dev = self.model.get_all_netdevs()[int(dev_spec[2])]
            elif dev_spec[1] == "name":
                dev = self.model.get_netdev_by_name(dev_spec[2])
        if dev is None:
            raise Exception("could not resolve {}".format(id))
        if len(id) > 1:
            part, index = id[1].split()
            if part == "part":
                return dev.partitions()[int(index)]
        else:
            return dev
        raise Exception("could not resolve {}".format(id))

    def _action_clean_devices(self, devices):
        return [self._action_get(device) for device in devices]

    def _answers_action(self, action):
        from subiquitycore.ui.stretchy import StretchyOverlay
        log.debug("_answers_action %r", action)
        if 'obj' in action:
            obj = self._action_get(action['obj'])
            meth = getattr(
                self.ui.body,
                "_action_{}".format(action['action']))
            meth(obj)
            yield
            body = self.ui.body._w
            if not isinstance(body, StretchyOverlay):
                return
            for k, v in action.items():
                if not k.endswith('data'):
                    continue
                form_name = "form"
                submit_key = "submit"
                if '-' in k:
                    prefix = k.split('-')[0]
                    form_name = prefix + "_form"
                    submit_key = prefix + "-submit"
                yield from self._enter_form_data(
                    getattr(body.stretchy, form_name),
                    v,
                    action.get(submit_key, True))
        elif action['action'] == 'create-bond':
            self.ui.body._create_bond()
            yield
            body = self.ui.body._w
            yield from self._enter_form_data(
                body.stretchy.form,
                action['data'],
                action.get("submit", True))
        elif action['action'] == 'done':
            self.ui.body.done()
        else:
            raise Exception("could not process action {}".format(action))

    def update_initial_configs(self):
        # Any device that does not have a (global) address by the time
        # we get to the network screen is marked as disabled, with an
        # explanation.
        log.debug("updating initial NIC config")
        for dev in self.model.get_all_netdevs():
            has_global_address = False
            if dev.info is None or not dev.config:
                continue
            for a in dev.info.addresses.values():
                if a.scope == "global":
                    has_global_address = True
                    break
            if not has_global_address:
                dev.remove_ip_networks_for_version(4)
                dev.remove_ip_networks_for_version(6)
                log.debug("disabling %s", dev.name)
                dev.disabled_reason = _("autoconfiguration failed")

    def start_ui(self):
        if not self.view_shown:
            self.update_initial_configs()
        self.view = NetworkView(self.model, self)
        if not self.view_shown:
            self.apply_config_start()
            self.view_shown = True
        self.network_event_receiver.view = self.view
        self.ui.set_body(self.view)

    def end_ui(self):
        self.view = self.network_event_receiver.view = None

    @property
    def netplan_path(self):
        if self.opts.project == "subiquity":
            netplan_config_file_name = '00-installer-config.yaml'
        else:
            netplan_config_file_name = '00-snapd-config.yaml'
        return os.path.join(self.root, 'etc/netplan', netplan_config_file_name)

    def apply_config_start(self, silent=False):
        self.apply_config_task.start_sync(self.apply_config(silent))

    async def apply_config(self, silent):
        log.debug("apply_config silent=%s", silent)

        config = self.model.render()

        devs_to_delete = []
        devs_to_down = []
        dhcp_device_versions = []
        for dev in self.model.get_all_netdevs(include_deleted=True):
            for v in 4, 6:
                if dev.dhcp_enabled(v):
                    if not silent:
                        dev.set_dhcp_state(v, "PENDING")
                        self.network_event_receiver.update_link(dev.ifindex)
                    else:
                        dev.set_dhcp_state(v, "RECONFIGURE")
                    dhcp_device_versions.append((dev, v))
            if dev.info is None:
                continue
            if dev.is_virtual:
                devs_to_delete.append(dev)
                continue
            if dev.config != self.model.config.config_for_device(dev.info):
                devs_to_down.append(dev)

        log.debug("network config: \n%s",
                  yaml.dump(sanitize_config(config), default_flow_style=False))

        for p in netplan.configs_in_root(self.root, masked=True):
            if p == self.netplan_path:
                continue
            os.rename(p, p + ".dist-" + self.opts.project)

        write_file(self.netplan_path, '\n'.join((
            ("# This is the network config written by '%s'" %
             self.opts.project),
            yaml.dump(config, default_flow_style=False))), omode="w")

        self.model.parse_netplan_configs(self.root)

        if not silent and self.view:
            self.view.show_apply_spinner()

        def error(stage):
            if not silent and self.view:
                self.view.show_network_error(stage)

        if self.opts.dry_run:
            delay = 1/self.app.scale_factor
            await arun_command(['sleep', str(delay)])
            if os.path.exists('/lib/netplan/generate'):
                # If netplan appears to be installed, run generate to at
                # least test that what we wrote is acceptable to netplan.
                await arun_command(
                    ['netplan', 'generate', '--root', self.root], check=True)
        else:
            try:
                await arun_command(
                    ['systemctl', 'stop', 'systemd-networkd.service'], check=True)
            except subprocess.CalledProcessError:
                error("stop-networkd")
                raise
            for dev in devs_to_down:
                try:
                    log.debug('downing %s', dev.name)
                    self.rtlistener.unset_link_flags(dev.ifindex, IFF_UP)
                except RuntimeError:
                    # We don't actually care very much about this
                    log.exception('unset_link_flags failed for %s', dev.name)
            for dev in self.devs_to_delete:
                # XXX would be nicer to do this via rtlistener eventually.
                log.debug('deleting %s', dev.name)
                cmd = ['ip', 'link', 'delete', 'dev', dev.name]
                try:
                    await arun_command(cmd, check=True)
                except subprocess.CalledProcessError as cp:
                    log.info("deleting %s failed with %r", dev.name, cp.stderr)
            try:
                await arun_command(['netplan', 'apply'], check=True)
            except subprocess.CalledProcessError:
                error("apply")
                raise

        if not silent and self.view:
            self.view.hide_apply_spinner()

        await asyncio.sleep(10)

        for dev, v in dhcp_device_versions:
            if not dev.dhcp_addresses()[v]:
                dev.set_dhcp_state(v, "TIMEDOUT")
                self.network_event_receiver.update_link(dev.ifindex)

    def add_vlan(self, device, vlan):
        return self.model.new_vlan(device, vlan)

    def add_or_update_bond(self, existing, result):
        mode = result['mode']
        params = {
            'mode': mode,
            }
        if mode in BondParameters.supports_xmit_hash_policy:
            params['transmit-hash-policy'] = result['xmit_hash_policy']
        if mode in BondParameters.supports_lacp_rate:
            params['lacp-rate'] = result['lacp_rate']
        for device in result['devices']:
            device.config = {}
        interfaces = [d.name for d in result['devices']]
        if existing is None:
            return self.model.new_bond(result['name'], interfaces, params)
        else:
            existing.config['interfaces'] = interfaces
            existing.config['parameters'] = params
            existing.name = result['name']
            return existing
