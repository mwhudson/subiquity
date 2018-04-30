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

import attr

from urwid import CheckBox, Text, WidgetWrap

from subiquitycore.view import BaseView
from subiquitycore.ui.buttons import cancel_btn, done_btn, menu_btn, ok_btn
from subiquitycore.ui.container import Pile
from subiquitycore.ui.form import (
    ChoiceField,
    Form,
    simple_field,
    WantsToKnowFormField,
    )
from subiquitycore.ui.interactive import (
    IntegerEditor,
    )
from subiquitycore.ui.selector import (
    Option,
    )
from subiquitycore.ui.utils import button_pile, Color
from subiquitycore.ui.stretchy import (
    Stretchy,
    )

from subiquity.models.filesystem import humanize_size, Partition

log = logging.getLogger('subiquity.ui.raid')

@attr.s
class RaidLevel:
    name = attr.ib()
    value = attr.ib()
    spares_allowed = attr.ib()
    min_devices = attr.ib()

levels = [
    RaidLevel(_("0 (striped)"), 0, False, 2),
    RaidLevel(_("1 (mirrored)"), 1, True, 2),
    RaidLevel(_("5"), 5, True, 3),
    RaidLevel(_("6"), 6, True, 4),
    RaidLevel(_("10"), 10, True, 2),
    ]



class BlockDevicePicker(Stretchy):

    def __init__(self, chooser, parent, devices):
        self.parent = parent
        self.chooser = chooser
        self.devices = devices
        device_widgets = []
        max_label_width = max([40] + [len(device.label) for device, checked, disable_reason in devices])
        for device, checked, disable_reason in devices:
            disk_sz = humanize_size(device.size)
            disk_string = "{:{}} {}".format(device.label, max_label_width, disk_sz)
            if disable_reason is None:
                device_widgets.append(CheckBox(disk_string, state=checked))
            else:
                device_widgets.append(Color.info_minor(Text("    " + disk_string)))
        self.pile = Pile(device_widgets)
        widgets = [
            self.pile,
            Text(""),
            button_pile([
                ok_btn(label=_("OK"), on_press=self.ok),
                cancel_btn(label=_("Cancel"), on_press=self.cancel),
                ]),
            ]
        super().__init__(
            _("Select block devices"),
            widgets,
            stretchy_index=0,
            focus_index=0)

    def ok(self, sender):
        selected_devs = []
        for i in range(len(self.devices)):
            dev, was_checked, disable_reason = self.devices[i]
            if disable_reason is not None:
                continue
            w, o = self.pile.contents[i]
            if w.state:
                selected_devs.append(dev)
        self.chooser.value = selected_devs
        self.parent.remove_overlay()

    def cancel(self, sender):
        self.parent.remove_overlay()


class MultiDeviceChooser(WidgetWrap, WantsToKnowFormField):
    def __init__(self):
        self.button = menu_btn(label=_("Select"), on_press=self.click)
        self.devices = []
        self.pile = Pile([self.button])
        super().__init__(self.pile)
    @property
    def value(self):
        return self.devices
    @value.setter
    def value(self, value):
        self.devices = value
        w = []
        for dev in self.devices:
            w.append((Text(dev.label), self.pile.options('pack')))
        if len(w) > 0:
            self.button.base_widget.set_label(_("Edit"))
        else:
            self.button.base_widget.set_label(_("Select"))
        w.append((self.button, self.pile.options('pack')))
        self.pile.contents[:] = w
        self.pile.focus_item = self.button
    def click(self, sender):
        view = self.bff.parent_view
        model = view.model
        avail_disks = [disk for disk in model.all_disks() if disk.ok_for_raid]
        avail_parts = [part for part in model.all_partitions() if part.ok_for_raid]

        devs = []
        for device in avail_disks + avail_parts:
            devs.append((device, device in self.devices, None))
        view.show_stretchy_overlay(BlockDevicePicker(self, view, devs))


MultiDeviceField = simple_field(MultiDeviceChooser)


class RaidForm(Form):

    level = ChoiceField(choices=["dummy"])
    devices = MultiDeviceField(_("Devices:"))
    spares = MultiDeviceField(_("Spares:"))

class RaidView(BaseView):
    def __init__(self, model, controller):
        self.model = model
        self.controller = controller
        self.hot_spares = IntegerEditor()
        #self.chunk_size = StringEditor(edit_text="4K")
        self.selected_disks = []
        self.form = RaidForm()
        opts = []
        for level in levels:
            opts.append(Option((_(level.name), True, level.value)))
        self.form.level.widget._options = opts
        self.form.level.widget.index = 0
        super().__init__(self.form.as_screen(self, focus_buttons=False))

    def _build_disk_selection(self):
        log.debug('raid: _build_disk_selection')
        items = [
            Text(_("DISK SELECTION"))
        ]

        # raid can use empty whole disks, or empty partitions
        avail_disks = [disk for disk in self.model.all_disks() if disk.ok_for_raid]
        avail_parts = [part for part in self.model.all_partitions() if part.ok_for_raid]
        if len(avail_disks + avail_parts) == 0:
            return items.append(
                [Color.info_minor(Text("No available disks."))])

        for device in avail_disks + avail_parts:

            if isinstance(device, Partition):
                name = "partition %s of %s" % (device._number, device.device.label)
            else:
                name = device.label
            disk_sz = humanize_size(device.size)
            disk_string = "{}     {}".format(name, disk_sz)
            log.debug('raid: disk_string={}'.format(disk_string))
            self.selected_disks.append(CheckBox(disk_string))

        items += self.selected_disks

        return Pile(items)

    def _build_buttons(self):
        log.debug('raid: _build_buttons')
        cancel = cancel_btn(label=_("Cancel"), on_press=self.cancel)
        done = done_btn(label=_("Create"), on_press=self.done)

        buttons = [
            Color.button(done),
            Color.button(cancel)
        ]
        return Pile(buttons)

    def done(self, result):
        result = {
            'devices': [x.get_label() for x in self.selected_disks if x.state],
            'raid_level': self.raid_level.value,
            'hot_spares': self.hot_spares.value,
            'chunk_size': self.chunk_size.value,
        }
        log.debug('raid_done: result = {}'.format(result))
        self.signal.emit_signal('filesystem:add-raid-dev', result)

    def cancel(self, button):
        log.debug('raid: button_cancel')
        self.signal.prev_signal()
