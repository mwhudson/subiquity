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

import copy
import enum
import ipaddress
import logging

from subiquitycore import netplan


NETDEV_IGNORED_IFACE_NAMES = ['lo']
NETDEV_IGNORED_IFACE_TYPES = ['lo', 'bridge', 'tun', 'tap', 'dummy', 'sit']
NETDEV_WHITELIST_IFACE_TYPES = ['vlan', 'bond']
NETDEV_ALLOWED_VIRTUAL_IFACE_TYPES = ['vlan', 'bond']
log = logging.getLogger('subiquitycore.models.network')


def ip_version(ip):
    return ipaddress.ip_interface(ip).version


class NetDevAction(enum.Enum):
    INFO = _("Info")
    EDIT_WLAN = _("Edit Wifi")
    EDIT_IPV4 = _("Edit IPv4")
    EDIT_IPV6 = _("Edit IPv6")
    EDIT_BOND = _("Edit bond")
    ADD_VLAN = _("Add a VLAN tag")
    DELETE = _("Delete")


def _sanitize_inteface_config(iface_config):
    for ap, ap_config in iface_config.get('access-points', {}).items():
        if 'password' in ap_config:
            ap_config['password'] = '<REDACTED>'


def sanitize_interface_config(iface_config):
    iface_config = copy.deepcopy(iface_config)
    _sanitize_inteface_config(iface_config)
    return iface_config


def sanitize_config(config):
    """Return a copy of config with passwords redacted."""
    config = copy.deepcopy(config)
    interfaces = config.get('network', {}).get('wifis', {}).items()
    for iface, iface_config in interfaces:
        _sanitize_inteface_config(iface_config)
    return config


class NetworkDev(object):

    def __init__(self, model, name, typ):
        self._model = model
        self.name = name
        self.type = typ
        self.config = {}
        self.info = None

    def supports_action(self, action):
        return getattr(self, "_supports_" + action.name)

    @property
    def is_virtual(self):
        return self.type in NETDEV_ALLOWED_VIRTUAL_IFACE_TYPES

    @property
    def is_bond_slave(self):
        for dev in self._model.get_all_netdevs():
            if dev.type == "bond" and self.name in dev.config.get('interfaces', []):
                return True
        return False

    @property
    def is_used(self):
        for dev in self._model.get_all_netdevs():
            if dev.type == "bond" and self.name in dev.config.get('interfaces', []):
                return True
            if dev.type == "vlan" and self.name == dev.config.get('link'):
                return True
        return False

    _supports_INFO = True
    _supports_EDIT_WLAN = property(lambda self: self.type == "wlan")
    _supports_EDIT_IPV4 = True
    _supports_EDIT_IPV6 = True
    _supports_EDIT_BOND = property(lambda self: self.type == "bond")
    _supports_ADD_VLAN = property(
        lambda self: self.type != "vlan" and not self.is_bond_slave)
    _supports_DELETE = property(lambda self: self.is_virtual)

    def remove_ip_networks_for_version(self, version):
        self.config.pop('dhcp{v}'.format(v=version), None)
        self.config.pop('gateway{v}'.format(v=version), None)
        addrs = []
        for ip in self.config.get('addresses', []):
            if ip_version(ip) != version:
                addrs.append(ip)
        if addrs:
            self.config['addresses'] = addrs
        else:
            self.config.pop('addresses', None)

    def add_network(self, version, network):
        # result = {
        #    'network': self.subnet_input.value,
        #    'address': self.address_input.value,
        #    'gateway': self.gateway_input.value,
        #    'nameserver': [nameservers],
        #    'searchdomains': [searchdomains],
        # }
        address = network['address'].split('/')[0]
        address += '/' + network['network'].split('/')[1]
        self.config.setdefault('addresses', []).append(address)
        gwkey = 'gateway{v}'.format(v=version)
        if network['gateway']:
            self.config[gwkey] = network['gateway']
        else:
            self.config.pop(gwkey, None)
        ns = self.config.setdefault('nameservers', {})
        if network['nameservers']:
            ns.setdefault('addresses', []).extend(network['nameservers'])
        if network['searchdomains']:
            ns.setdefault('search', []).extend(network['search'])


NETDEV_IGNORED_IFACE_TYPES = ['lo', 'bridge', 'tun', 'tap', 'dummy', 'sit']
NETDEV_ALLOWED_VIRTUAL_IFACE_TYPES = ['vlan', 'bond']


class NetworkModel(object):
    """ """

    def __init__(self, support_wlan=True):
        self.support_wlan = support_wlan
        self.devices_by_name = {}  # Maps interface names to NetworkDev

    def parse_netplan_configs(self, netplan_root):
        self.config = netplan.Config()
        self.config.load_from_root(netplan_root)
        for typ, key in ('vlan', 'vlans'), ('bond', 'bonds'):
            network = self.config.config.get('network', {})
            for name, config in network.get(key, {}).items():
                dev = self.devices_by_name[name]
                if dev is None:
                    dev = self.devices_by_name[name] = NetworkDev(self, name, typ)
                # XXX What to do if types don't match??
                dev.config = config

    def new_link(self, ifindex, link):
        if link.type in NETDEV_IGNORED_IFACE_TYPES:
            return
        if not self.support_wlan and link.type == "wlan":
            return
        if link.is_virtual and link.type not in NETDEV_ALLOWED_VIRTUAL_IFACE_TYPES:
            return
        dev = self.devices_by_name.get(link.name)
        if dev is not None:
            # XXX What to do if types don't match??
            if dev.info is not None:
                XXX # err what
            else:
                dev.info = link
        else:
            if link.is_virtual:
                # If we see a virtual device without there already
                # being a config for it, we just ignore it.
                return
            dev = NetworkDev(self, link.name, link.type)
            dev.info = link
            dev.config = self.config.config_for_device(link)
            log.debug("new_link %s %s with config %s",
                    ifindex, link.name, sanitize_interface_config(dev.config))
            self.devices_by_name[link.name] = dev
        return dev

    def update_link(self, ifindex):
        for name, dev in self.devices_by_name.items():
            if dev.ifindex == ifindex:
                return dev

    def del_link(self, ifindex):
        for name, dev in self.devices_by_name.items():
            if dev.ifindex == ifindex:
                dev.info = None
                if dev.is_virtual:
                    # We delete all virtual devices before running netplan apply.
                    # If a device has been deleted in the UI, we set dev.config to None.
                    # Now it's actually gone, forget we ever knew it existed.
                    if dev.config is None:
                        del self.devices_by_name[name]
                else:
                    # If a physical interface disappears on us, it's gone.
                    del self.devices_by_name[name]
                return dev

    def new_vlan(self, device, tag):
        name = "{name}.{tag}".format(name=device.name, tag=tag)
        dev = self.devices_by_name[name] = NetworkDev(self, name, 'vlan')
        dev.config = {
            'link': device.name,
            'id': tag,
            }
        return dev

    def new_bond(self, name, interfaces, params):
        dev = self.devices_by_name[name] = NetworkDev(self, name, 'bond')
        dev.config = {
            'interfaces': interfaces,
            'parameters': params,
            }
        return dev

    def get_all_netdevs(self, include_deleted=False):
        if include_deleted:
            return [v for k, v in sorted(self.devices_by_name.items())]
        else:
            return [v for k, v in sorted(self.devices_by_name.items()) if v.config is not None]

    def get_netdev_by_name(self, name):
        return self.devices_by_name[name]

    def render(self):
        config = {
            'network': {
                'version': 2,
            },
        }
        type_to_key = {
            'eth': 'ethernets',
            'bond': 'bonds',
            'wlan': 'wifis',
            'vlan': 'vlans',
            }
        for dev in self.get_all_netdevs():
            key = type_to_key[dev.type]
            configs = config['network'].setdefault(key, {})
            if dev.config or dev.is_used:
                configs[dev.name] = dev.config

        return config
