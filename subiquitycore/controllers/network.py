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

from subiquitycore.async_helpers import SingleInstanceTask
from subiquitycore.context import with_context
from subiquitycore.file_util import write_file
from subiquitycore.models.network import (
    BondConfig,
    DHCPState,
    NetDevAction,
    NetDevInfo,
    StaticConfig,
    VLANConfig,
    WLANConfig,
    )
from subiquitycore import netplan
from subiquitycore.controller import BaseController
from subiquitycore.tuicontroller import TuiController
from subiquitycore.ui.stretchy import StretchyOverlay
from subiquitycore.ui.views.network import (
    NetworkView,
    )
from subiquitycore.utils import (
    arun_command,
    run_command,
    )


log = logging.getLogger("subiquitycore.controller.network")


class SubiquityNetworkEventReceiver(NetworkEventReceiver):
    def __init__(self, controller):
        self.controller = controller
        self.model = controller.model
        self.default_routes = set()

    def new_link(self, ifindex, link):
        netdev = self.model.new_link(ifindex, link)
        if netdev is not None:
            self.controller.new_link(netdev)

    def del_link(self, ifindex):
        netdev = self.model.del_link(ifindex)
        if ifindex in self.default_routes:
            self.default_routes.remove(ifindex)
            self.controller.update_default_routes(self.default_routes)
        if netdev is not None:
            self.controller.del_link(netdev)

    def update_link(self, ifindex):
        netdev = self.model.update_link(ifindex)
        if netdev is None:
            return
        flags = getattr(netdev.info, "flags", 0)
        if not (flags & IFF_UP) and ifindex in self.default_routes:
            self.default_routes.remove(ifindex)
            self.controller.update_default_routes(self.default_routes)
        self.controller.update_link(netdev)

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
        log.debug('default routes %s', self.default_routes)
        self.controller.update_default_routes(self.default_routes)


default_netplan = '''
network:
  version: 2
  ethernets:
    "all-en":
       match:
         name: "en*"
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
    "all-eth":
       match:
         name: "eth*"
       dhcp4: true
  wifis:
    "wlsp4":
       dhcp4: true
       access-points:
         "some-ap":
            password: password
'''


class BaseNetworkController(BaseController):

    model_name = "network"
    root = "/"

    def __init__(self, app):
        super().__init__(app)
        self.view = None
        self.apply_config_task = SingleInstanceTask(self._apply_config)
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
        self.parse_netplan_configs()

        self._watching = False
        self.network_event_receiver = SubiquityNetworkEventReceiver(self)

    def parse_netplan_configs(self):
        self.model.parse_netplan_configs(self.root)

    def update_default_routes(self, routes):
        if routes:
            self.signal.emit_signal('network-change')

    def new_link(self, netdev):
        pass

    def update_link(self, netdev):
        for v, e in netdev.dhcp_events.items():
            if netdev.dhcp_addresses()[v]:
                netdev.set_dhcp_state(v, DHCPState.CONFIGURED)
                e.set()

    def del_link(self, netdev):
        pass

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
            loop.add_reader(fd, self._data_ready, fd)
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

    def _action_clean_interfaces(self, devices):
        r = [self._action_get(device).name for device in devices]
        log.debug("%s", r)
        return r

    def _answers_action(self, action):
        log.debug("_answers_action %r", action)
        if 'obj' in action:
            obj = self._action_get(action['obj']).netdev_info()
            meth = getattr(
                self.ui.body,
                "_action_{}".format(action['action']))
            action_obj = getattr(NetDevAction, action['action'])
            table = self.ui.body.dev_name_to_table[obj.name]
            self.ui.body._action(None, (action_obj, meth), table)
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
            data = action['data'].copy()
            if 'devices' in data:
                data['interfaces'] = data.pop('devices')
            yield from self._enter_form_data(
                body.stretchy.form,
                data,
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

    @property
    def netplan_path(self):
        if self.opts.project == "subiquity":
            netplan_config_file_name = '00-installer-config.yaml'
        else:
            netplan_config_file_name = '00-snapd-config.yaml'
        return os.path.join(self.root, 'etc/netplan', netplan_config_file_name)

    def apply_config(self, context=None, silent=False):
        self.apply_config_task.start_sync(context=context, silent=silent)

    async def _down_devs(self, devs):
        for dev in devs:
            try:
                log.debug('downing %s', dev.name)
                self.observer.rtlistener.unset_link_flags(dev.ifindex, IFF_UP)
            except RuntimeError:
                # We don't actually care very much about this
                log.exception('unset_link_flags failed for %s', dev.name)

    async def _delete_devs(self, devs):
        for dev in devs:
            # XXX would be nicer to do this via rtlistener eventually.
            log.debug('deleting %s', dev.name)
            cmd = ['ip', 'link', 'delete', 'dev', dev.name]
            try:
                await arun_command(cmd, check=True)
            except subprocess.CalledProcessError as cp:
                log.info("deleting %s failed with %r", dev.name, cp.stderr)

    def _write_config(self):
        config = self.model.render_config()

        log.debug("network config: \n%s",
                  yaml.dump(
                      netplan.sanitize_config(config),
                      default_flow_style=False))

        for p in netplan.configs_in_root(self.root, masked=True):
            if p == self.netplan_path:
                continue
            os.rename(p, p + ".dist-" + self.opts.project)

        write_file(
            self.netplan_path,
            self.model.stringify_config(config),
            omode="w")

        self.parse_netplan_configs()

    def apply_starting(self):
        pass

    def apply_stopping(self):
        pass

    def apply_error(self, stage):
        pass

    @with_context(
        name="apply_config", description="silent={silent}", level="INFO")
    async def _apply_config(self, *, context, silent):
        devs_to_delete = []
        devs_to_down = []
        dhcp_device_versions = []
        dhcp_events = set()
        for dev in self.model.get_all_netdevs(include_deleted=True):
            dev.dhcp_events = {}
            for v in 4, 6:
                if dev.dhcp_enabled(v):
                    if not silent:
                        dev.set_dhcp_state(v, DHCPState.PENDING)
                        self.network_event_receiver.update_link(
                            dev.ifindex)
                    else:
                        dev.set_dhcp_state(v, DHCPState.RECONFIGURE)
                    dev.dhcp_events[v] = e = asyncio.Event()
                    dhcp_events.add(e)
            if dev.info is None:
                continue
            if dev.config != self.model.config.config_for_device(dev.info):
                if dev.is_virtual:
                    devs_to_delete.append(dev)
                else:
                    devs_to_down.append(dev)

        self._write_config()

        if not silent and self.view:
            self.apply_starting()

        try:
            def error(stage):
                if not silent and self.view:
                    self.view.show_network_error(stage)

            if self.opts.dry_run:
                delay = 1/self.app.scale_factor
                await arun_command(['sleep', str(delay)])
                if os.path.exists('/lib/netplan/generate'):
                    # If netplan appears to be installed, run generate to
                    # at least test that what we wrote is acceptable to
                    # netplan.
                    await arun_command(
                        ['netplan', 'generate', '--root', self.root],
                        check=True)
            else:
                if devs_to_down or devs_to_delete:
                    try:
                        await arun_command(
                            ['systemctl', 'mask', '--runtime',
                             'systemd-networkd.service',
                             'systemd-networkd.socket'],
                            check=True)
                        await arun_command(
                            ['systemctl', 'stop',
                             'systemd-networkd.service',
                             'systemd-networkd.socket'],
                            check=True)
                    except subprocess.CalledProcessError:
                        error("stop-networkd")
                        raise
                if devs_to_down:
                    await self._down_devs(devs_to_down)
                if devs_to_delete:
                    await self._delete_devs(devs_to_delete)
                if devs_to_down or devs_to_delete:
                    await arun_command(
                        ['systemctl', 'unmask', '--runtime',
                         'systemd-networkd.service',
                         'systemd-networkd.socket'],
                        check=True)
                try:
                    await arun_command(['netplan', 'apply'], check=True)
                except subprocess.CalledProcessError:
                    error("apply")
                    raise
                if devs_to_down or devs_to_delete:
                    # It's probably running already, but just in case.
                    await arun_command(
                        ['systemctl', 'start', 'systemd-networkd.socket'],
                        check=False)
        finally:
            if not silent:
                self.apply_stopping()

        # if self.answers.get('accept-default', False):
        #     self.done()
        # elif self.answers.get('actions', False):
        #     actions = self.answers['actions']
        #     self.answers.clear()
        #     self._run_iterator(self._run_actions(actions))

        if not dhcp_events:
            return

        try:
            await asyncio.wait_for(
                asyncio.wait({e.wait() for e in dhcp_events}),
                10)
        except asyncio.TimeoutError:
            pass

        for dev, v in dhcp_device_versions:
            dev.dhcp_events = {}
            if not dev.dhcp_addresses()[v]:
                dev.set_dhcp_state(v, DHCPState.TIMED_OUT)
                self.network_event_receiver.update_link(dev.ifindex)

    def set_static_config(self, dev_info: NetDevInfo, ip_version: int,
                          static_config: StaticConfig) -> None:
        setattr(dev_info, 'static' + str(ip_version), static_config)
        getattr(dev_info, 'dhcp' + str(ip_version)).enabled = False

        dev = self.model.get_netdev_by_name(dev_info.name)
        dev.remove_ip_networks_for_version(ip_version)
        dev.config.setdefault('addresses', []).extend(static_config.addresses)
        gwkey = 'gateway{v}'.format(v=ip_version)
        if static_config.gateway:
            dev.config[gwkey] = static_config.gateway
        else:
            dev.config.pop(gwkey, None)
        ns = dev.config.setdefault('nameservers', {})
        ns.setdefault('addresses', []).extend(static_config.nameservers)
        ns.setdefault('search', []).extend(static_config.searchdomains)
        self.update_link(dev)
        self.apply_config()

    def enable_dhcp(self, dev_info: NetDevInfo, ip_version: int) -> None:
        setattr(dev_info, 'static' + str(ip_version), StaticConfig())
        getattr(dev_info, 'dhcp' + str(ip_version)).enabled = True
        getattr(dev_info, 'dhcp' + str(ip_version)).state = DHCPState.PENDING

        dev = self.model.get_netdev_by_name(dev_info.name)
        dev.remove_ip_networks_for_version(ip_version)
        dhcpkey = 'dhcp{v}'.format(v=ip_version)
        dev.config[dhcpkey] = True
        self.apply_config()

    def disable_network(self, dev_info: NetDevInfo, ip_version: int) -> None:
        setattr(dev_info, 'static' + str(ip_version), StaticConfig())
        getattr(dev_info, 'dhcp' + str(ip_version)).enabled = False

        dev = self.model.get_netdev_by_name(dev_info.name)
        dev.remove_ip_networks_for_version(ip_version)

        self.apply_config()

    def add_vlan(self, dev_info: NetDevInfo, vlan_config: VLANConfig):
        new = self.model.new_vlan(dev_info.name, vlan_config)
        dev = self.model.get_netdev_by_name(dev_info.name)
        self.update_link(dev)
        self.apply_config()
        return new.netdev_info()

    def delete_link(self, dev_info: NetDevInfo):
        touched_devices = set()
        if dev_info.type == "bond":
            for device_name in dev_info.bond.interfaces:
                interface = self.model.get_netdev_by_name(device_name)
                touched_devices.add(interface)
        elif dev_info.type == "vlan":
            link = self.model.get_netdev_by_name(dev_info.vlan.link)
            touched_devices.add(link)
        dev_info.has_config = False

        device = self.model.get_netdev_by_name(dev_info.name)
        self.del_link(device)
        device.config = None
        for dev in touched_devices:
            self.update_link(dev)
        self.apply_config()

    def add_or_update_bond(self, existing_name: NetDevInfo, new_name: str,
                           new_info: BondConfig) -> None:
        get_netdev_by_name = self.model.get_netdev_by_name
        touched_devices = set()
        for device_name in new_info.interfaces:
            device = get_netdev_by_name(device_name)
            device.config = {}
            touched_devices.add(device)
        if existing_name is None:
            new_dev = self.model.new_bond(new_name, new_info)
            self.new_link(new_dev)
        else:
            existing = get_netdev_by_name(existing_name)
            for interface in existing.config['interfaces']:
                touched_devices.add(get_netdev_by_name(interface))
            existing.config.update(new_info.to_config())
            if existing.name != new_name:
                config = existing.config
                existing.config = None
                self.del_link(existing)
                existing.config = config
                existing.name = new_name
                self.new_link(existing)
            else:
                touched_devices.add(existing)
        self.apply_config()
        for dev in touched_devices:
            self.update_link(dev)

    def get_info_for_netdev(self, dev_info: NetDevInfo) -> str:
        device = self.model.get_netdev_by_name(dev_info.name)
        if device.info is not None:
            return yaml.dump(
                device.info.serialize(), default_flow_style=False)
        else:
            return "Configured but not yet created {type} interface.".format(
                type=device.type)

    def set_wlan(self, dev_info: NetDevInfo, wlan: WLANConfig) -> None:
        dev_info.wlan = wlan

        device = self.model.get_netdev_by_name(dev_info.name)
        device.set_ssid_psk(wlan.ssid, wlan.psk)
        self.update_link(device)

    def start_scan(self, dev_info: NetDevInfo) -> None:
        device = self.model.get_netdev_by_name(dev_info.name)
        self.observer.trigger_scan(device.ifindex)
        self.update_link(device)


class NetworkController(BaseNetworkController, TuiController):

    def __init__(self, app):
        super().__init__(app)
        self.view = None
        self.view_shown = False

    def apply_starting(self):
        super().apply_starting()
        if self.view is not None:
            self.view.show_apply_spinner()

    def apply_stopping(self):
        super().apply_stopping()
        if self.view is not None:
            self.view.hide_apply_spinner()

    def apply_error(self, stage):
        super().apply_error()
        if self.view is not None:
            self.view.show_network_error(stage)

    def update_default_routes(self, routes):
        super().update_default_routes(routes)
        if self.view is not None:
            self.view.update_default_routes(routes)

    def new_link(self, netdev):
        super().new_link(netdev)
        if self.view is not None:
            self.view.new_link(netdev.netdev_info())

    def update_link(self, netdev):
        super().update_link(netdev)
        if self.view is not None:
            self.view.update_link(netdev.netdev_info())

    def del_link(self, netdev):
        super().del_link(netdev)
        if self.view is not None:
            self.view.del_link(netdev.netdev_info())

    def start_ui(self):
        if not self.view_shown:
            self.update_initial_configs()
        netdev_infos = [
            dev.netdev_info() for dev in self.model.get_all_netdevs()
            ]
        self.view = NetworkView(self, netdev_infos)
        if not self.view_shown:
            self.apply_config(silent=True)
            self.view_shown = True
        self.view.update_default_routes(
            self.network_event_receiver.default_routes)
        self.ui.set_body(self.view)

    def end_ui(self):
        self.view = None

    def done(self):
        log.debug("NetworkController.done next_screen")
        self.model.has_network = bool(
            self.network_event_receiver.default_routes)
        self.app.next_screen()

    def cancel(self):
        self.app.prev_screen()
