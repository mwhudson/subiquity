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

from urwid import (
    connect_signal,
    Text,
    )

from subiquitycore.ui.container import (
    Pile,
    )
from subiquitycore.ui.form import (
    Form,
    ReadOnlyField,
    StringField,
    )
from subiquitycore.ui.stretchy import (
    Stretchy,
    )

from .raid import MultiDeviceField, DEVICE, LABEL, PART
from subiquity.models.filesystem import (
    DeviceAction,
    get_lvm_size,
    humanize_size,
    )

log = logging.getLogger('subiquity.ui.views.filesystem.lvm')


class VolGroupForm(Form):

    def __init__(self, mountpoint_to_devpath_mapping,
                 all_devices, initial, lvm_names):
        self.mountpoint_to_devpath_mapping = mountpoint_to_devpath_mapping
        self.all_devices = all_devices
        self.lvm_names = lvm_names
        super().__init__(initial)

    name = StringField(_("Name:"))
    devices = MultiDeviceField(_("Devices:"))
    size = ReadOnlyField(_("Size:"))

    def validate_name(self):
        if self.name.value in self.lvm_names:
            return _("There is already a volume group named '{}'").format(
                self.name.value)

    def validate_devices(self):
        active_device_count = len(self.devices.widget.active_devices)
        if active_device_count < 1:
            return _("Select at least one device")


class VolGroupStretchy(Stretchy):
    def __init__(self, parent, existing=None):
        self.parent = parent
        mountpoint_to_devpath_mapping = (
            self.parent.model.get_mountpoint_to_devpath_mapping())
        self.existing = existing
        lvm_names = {vg.name for vg in parent.model.all_volgroups()}
        if existing is None:
            title = _('Create volume group (LVM)')
            x = 0
            while True:
                name = 'vg-{}'.format(x)
                if name not in lvm_names:
                    break
                x += 1
            initial = {
                'devices': {},
                'name': name,
                'size': '-',
                }
        else:
            lvm_names.remove(existing.name)
            title = _('Edit volume group "{}"').format(existing.name)
            name = existing.name
            devices = {}
            for d in existing.devices:
                devices[d] = 'active'
            initial = {
                'devices': devices,
                'name': name,
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

        cur_devices = set()
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

        form = self.form = VolGroupForm(
            mountpoint_to_devpath_mapping, all_devices, initial, lvm_names)

        self.form.devices.widget.set_supports_spares(
            initial['level'].supports_spares)

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

    def _change_devices(self, sender, new_devices):
        if len(sender.active_devices) >= 1:
            self.form.size.value = humanize_size(get_lvm_size(sender.active_devices))
        else:
            self.form.size.value = '-'

    def done(self, sender):
        result = self.form.as_data()
        mdc = self.form.devices.widget
        result['devices'] = mdc.active_devices
        log.debug('vg_done: result = {}'.format(result))
        self.parent.controller.raid_handler(self.existing, result)
        self.parent.refresh_model_inputs()
        self.parent.remove_overlay()

    def cancel(self, sender):
        self.parent.remove_overlay()
