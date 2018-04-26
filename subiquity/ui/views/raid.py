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
from urwid import Text, CheckBox

from subiquitycore.view import BaseView
from subiquitycore.ui.buttons import cancel_btn, done_btn
from subiquitycore.ui.container import Columns, ListBox, Pile
from subiquitycore.ui.interactive import (
    ChoiceField,
    Form,
    IntegerEditor,
    )
from subiquitycore.ui.interactive import (StringEditor, IntegerEditor,
                                          Selector)
from subiquitycore.ui.utils import Color, Padding

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


class RaidForm(Form):

    level = ChoiceField()
    spares = IntegerField()


class RaidView(BaseView):
    def __init__(self, model, controller):
        self.model = model
        self.controller = controller
        self.raid_level = Selector(self.model.raid_levels)
        self.hot_spares = IntegerEditor()
        self.chunk_size = StringEditor(edit_text="4K")
        self.selected_disks = []
        body = [
            Padding.center_50(self._build_disk_selection()),
            Padding.line_break(""),
            Padding.center_50(self._build_raid_configuration()),
            Padding.line_break(""),
            Padding.fixed_10(self._build_buttons())
        ]
        super().__init__(ListBox(body))

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

    def _build_raid_configuration(self):
        log.debug('raid: _build_raid_config')
        items = [
            Text("RAID CONFIGURATION"),
            Columns(
                [
                    ("weight", 0.2, Text("RAID Level", align="right")),
                    ("weight", 0.3, Color.string_input(self.raid_level))
                ],
                dividechars=4
            ),
            Columns(
                [
                    ("weight", 0.2, Text("Hot spares",
                                         align="right")),
                    ("weight", 0.3, Color.string_input(self.hot_spares))
                ],
                dividechars=4
            ),
            Columns(
                [
                    ("weight", 0.2, Text("Chunk size", align="right")),
                    ("weight", 0.3, Color.string_input(self.chunk_size))
                ],
                dividechars=4
            )
        ]
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
