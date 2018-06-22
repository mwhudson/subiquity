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
import re

from urwid import (
    CheckBox,
    connect_signal,
    Padding as UrwidPadding,
    Text,
    )

from subiquitycore.ui.container import (
    Pile,
    WidgetWrap,
    )
from subiquitycore.ui.form import (
    ChoiceField,
    Form,
    ReadOnlyField,
    simple_field,
    StringField,
    Toggleable,
    WantsToKnowFormField,
    )
from subiquitycore.ui.selector import (
    Option,
    Selector,
    )
from subiquitycore.ui.stretchy import (
    Stretchy,
    )
from subiquitycore.ui.table import (
    TablePile,
    TableRow,
    )
from subiquitycore.ui.utils import (
    Color,
    )

from .filesystem.partition import FSTypeField
from ..mount import MountField
from subiquity.models.filesystem import (
    DeviceAction,
    get_raid_size,
    humanize_size,
    raidlevels,
    raidlevels_by_value,
    )

log = logging.getLogger('subiquity.ui.raid')


LABEL, DEVICE, PART = range(3)


class MultiDeviceChooser(WidgetWrap, WantsToKnowFormField):
    signals = ['change']

    def __init__(self):
        self.table = TablePile([], spacing=1)
        self.device_to_checkbox = {}
        self.device_to_selector = {}
        self.devices = {} # {device:active|spare}
        self.supports_spares = True
        super().__init__(self.table)

    @property
    def value(self):
        return self.devices

    @value.setter
    def value(self, value):
        self.devices = value
        for d, b in self.device_to_checkbox.items():
            b.set_state(d in self.devices)
        for d, s in self.device_to_selector.items():
            if d in self.devices:
                s.enable()
                s.base_widget.value = self.devices[d]
            else:
                s.disable()

    @property
    def active_devices(self):
        return [device for device, status in self.devices.items() if status == 'active']

    @property
    def spare_devices(self):
        return [device for device, status in self.devices.items() if status == 'spare']

    def set_supports_spares(self, val):
        if val == self.supports_spares:
            return
        self.supports_spares = val
        if val:
            for device in list(self.devices):
                self.device_to_selector[device].enable()
                self.devices[device] = self.device_to_selector[device].base_widget.value
        else:
            for device in list(self.devices):
                self.device_to_selector[device].disable()
                self.devices[device] = 'active'

    def _state_change_device(self, sender, state, device):
        if state:
            if self.supports_spares:
                self.device_to_selector[device].enable()
            self.devices[device] = self.device_to_selector[device].base_widget.value
        else:
            self.device_to_selector[device].disable()
            del self.devices[device]
        self._emit('change', self.devices)

    def _select_active_spare(self, sender, value, device):
        self.devices[device] = value
        self._emit('change', self.devices)

    def _summarize(self, prefix, device):
        if device.fs() is not None:
            fs = device.fs()
            text = prefix + _("formatted as {}").format(fs.fstype)
            if fs.mount():
                text += _(", mounted at {}").format(fs.mount().path)
            else:
                text += _(", not mounted")
        else:
            text = prefix + _("unused {}").format(device.desc())
        return TableRow([(2, Color.info_minor(Text(text)))])

    def set_bound_form_field(self, bff):
        super().set_bound_form_field(bff)
        bff.wibble = False
        rows = []
        for kind, device in bff.form.all_devices:
            if kind == LABEL:
                rows.append(TableRow([
                    Text("    " + device.label),
                    Text(humanize_size(device.size), align='right')
                ]))
                rows.append(TableRow([
                    (2, Color.info_minor(Text("      " + device.desc())))
                ]))
            else:
                if kind == DEVICE:
                    label = device.label
                    prefix = "    "
                elif kind == PART:
                    label = _("  partition {}").format(device._number)
                    prefix = "      "
                else:
                    1/0
                box = CheckBox(
                    label,
                    on_state_change=self._state_change_device,
                    user_data=device)
                self.device_to_checkbox[device] = box
                size = Text(humanize_size(device.size), align='right')
                rows.append(Color.menu_button(TableRow([box, size])))
                selector = Selector(['active', 'spare'])
                connect_signal(selector, 'select', self._select_active_spare, device)
                selector = Toggleable(UrwidPadding(Color.menu_button(selector), left=len(prefix)))
                selector.disable()
                self.device_to_selector[device] = selector
                rows.append(TableRow([(2, selector)]))
                rows.append(self._summarize(prefix, device))
        self.table.set_contents(rows)
        log.debug("%s", self.table._w.focus_position)


MultiDeviceField = simple_field(MultiDeviceChooser)
MultiDeviceField.takes_default_style = False


raidlevel_choices = [
    Option((_(level.name), True, level)) for level in raidlevels]


class RaidForm(Form):

    def __init__(self, mountpoint_to_devpath_mapping,
                 all_devices, initial, raid_names):
        self.mountpoint_to_devpath_mapping = mountpoint_to_devpath_mapping
        self.all_devices = all_devices
        self.raid_names = raid_names
        super().__init__(initial)
        connect_signal(self.fstype.widget, 'select', self.select_fstype)
        self.select_fstype(None, self.fstype.widget.value)

    name = StringField(_("Name:"))
    level = ChoiceField(_("RAID Level:"), choices=raidlevel_choices)
    devices = MultiDeviceField(_("Devices:"))
    size = ReadOnlyField(_("Size:"))

    def select_fstype(self, sender, fs):
        self.mount.enabled = fs.is_mounted

    fstype = FSTypeField(_("Format:"))
    mount = MountField(_("Mount:"))

    def clean_mount(self, val):
        if self.fstype.value.is_mounted:
            return val
        else:
            return None

    def clean_name(self, val):
        if not re.match('md[0-9]+', val):
            val = 'md/' + val
        return val

    def validate_name(self):
        if self.name.value in self.raid_names:
            return _("There is already a RAID named '{}'").format(
                self.name.value)

    def validate_devices(self):
        log.debug(
            'validate_devices %s %s',
            len(self.devices.value), self.level.value)
        if len(self.devices.widget.active_devices) < self.level.value.min_devices:
            return _('RAID Level "{}" requires at least {} active devices').format(
                self.level.value.name, self.level.value.min_devices)

    def validate_mount(self):
        mount = self.mount.value
        if mount is None:
            return
        # /usr/include/linux/limits.h:PATH_MAX
        if len(mount) > 4095:
            return _('Path exceeds PATH_MAX')
        dev = self.mountpoint_to_devpath_mapping.get(mount)
        if dev is not None:
            return _("{} is already mounted at {}").format(dev, mount)


class RaidStretchy(Stretchy):
    def __init__(self, parent, existing=None):
        self.parent = parent
        mountpoint_to_devpath_mapping = (
            self.parent.model.get_mountpoint_to_devpath_mapping())
        self.existing = existing
        raid_names = {raid.name for raid in parent.model.all_raids()}
        if existing is None:
            title = _('Create software RAID ("MD") disk')
            x = 0
            while True:
                name = 'md{}'.format(x)
                if name not in raid_names:
                    break
                x += 1
            initial = {
                'devices': {},
                'name': name,
                'level': raidlevels_by_value[1],
                'size': '-',
                }
        else:
            raid_names.remove(existing.name)
            title = _('Edit software RAID disk "{}"').format(existing.name)
            f = existing.fs()
            if f is None:
                fs = parent.model.fs_by_name[None]
                m = None
            else:
                fs = parent.model.fs_by_name[f.fstype]
                m = f.mount()
                if m:
                    m = m.path
                    if m in mountpoint_to_devpath_mapping:
                        del mountpoint_to_devpath_mapping[m]
            name = existing.name
            if name.startswith('md/'):
                name = name[3:]
            devices = {}
            for d in existing.devices:
                devices[d] = 'active'
            for d in existing.spare_devices:
                devices[d] = 'spare'
            initial = {
                'devices': devices,
                'fstype': fs,
                'mount': m,
                'name': name,
                'raidlevels': raidlevels_by_value[existing.raidlevel]
                }

        all_devices = []

        # We mustn't allow the user to add a device to this raid if it
        # is built out of this raid!
        omits = set()

        def _walk_down(o):
            if o is None:
                return
            if o in omits:
                raise Exception(
                    "block device cycle detected involving {}".format(o))
            omits.add(o)
            _walk_down(o.constructed_device())
            for p in o.partitions():
                _walk_down(p)

        _walk_down(existing)

        cur_devices = []
        if existing:
            cur_devices = existing.devices

        def device_ok(dev):
            return (dev not in omits
                    and (dev.supports_action(DeviceAction.FORMAT)
                         or dev in cur_devices))

        for dev in self.parent.model.all_devices():
            if device_ok(dev):
                all_devices.append((DEVICE, dev))
            else:
                ok_parts = []
                for part in dev.partitions():
                    if device_ok(part):
                        ok_parts.append((PART, part))
                if len(ok_parts) > 0:
                    all_devices.append((LABEL, dev))
                    all_devices.extend(ok_parts)

        form = self.form = RaidForm(
            mountpoint_to_devpath_mapping, all_devices, initial, raid_names)

        self.form.devices.widget.set_supports_spares(initial['level'].supports_spares)

        connect_signal(form.level.widget, 'select', self._select_level)
        connect_signal(form.devices.widget, 'change', self._change_devices)
        connect_signal(form, 'submit', self.done)
        connect_signal(form, 'cancel', self.cancel)

        rows = form.as_rows()

        if existing is not None:
            rows[0:0] = [
                Text("You cannot save edit to RAIDs just yet."),
                Text(""),
                ]
            self.form.validated = lambda *args: self.form.done_btn.disable()
            self.form.validated()

        super().__init__(
            title,
            [Pile(rows), Text(""), self.form.buttons],
            0, 0)

    def _select_level(self, sender, new_level):
        if len(self.form.devices.widget.active_devices) >= new_level.min_devices:
            self.form.size.value = humanize_size(
                get_raid_size(new_level.value, self.form.devices.value))
        else:
            self.form.size.value = '-'
        self.form.devices.widget.set_supports_spares(new_level.supports_spares)
        self.form.level.widget._index = raidlevels.index(new_level)  # *cough*
        self.form.devices.showing_extra = False
        self.form.devices.validate()

    def _change_devices(self, sender, new_devices):
        if len(sender.active_devices) >= self.form.level.value.min_devices:
            self.form.size.value = humanize_size(
                get_raid_size(self.form.level.value.value, new_devices))
        else:
            self.form.size.value = '-'

    def done(self, sender):
        result = self.form.as_data()
        result['devices'] = self.form.widget.active_devices
        result['spare_devices'] = self.form.widget.active_devices
        log.debug('raid_done: result = {}'.format(result))
        self.parent.controller.raid_handler(self.existing, result)
        self.parent.refresh_model_inputs()
        self.parent.remove_overlay()

    def cancel(self, sender):
        self.parent.remove_overlay()
