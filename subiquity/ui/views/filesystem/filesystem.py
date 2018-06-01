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

""" Filesystem

Provides storage device selection and additional storage
configuration.

"""
import logging

import attr

from urwid import (
    connect_signal,
    Text,
    WidgetWrap,
    )

from subiquitycore.ui.actionmenu import ActionMenu, ActionMenuButton
from subiquitycore.ui.buttons import (
    back_btn,
    cancel_btn,
    danger_btn,
    done_btn,
    menu_btn,
    reset_btn,
)
from subiquitycore.ui.container import Columns, ListBox, Pile
from subiquitycore.ui.form import Toggleable
from subiquitycore.ui.stretchy import Stretchy
from subiquitycore.ui.utils import button_pile, Color, Padding
from subiquitycore.view import BaseView

from subiquity.models.filesystem import humanize_size, Disk, Partition, Raid


log = logging.getLogger('subiquity.ui.filesystem.filesystem')


confirmation_text = _(
    "Selecting Continue below will begin the installation process and "
    "result in the loss of data on the disks selected to be formatted.\n"
    "\n"
    "You will not be able to return to this or a previous screen once "
    "the installation has started.\n"
    "\n"
    "Are you sure you want to continue?")


class FilesystemConfirmation(Stretchy):
    def __init__(self, parent, controller):
        self.parent = parent
        self.controller = controller
        widgets = [
            Text(_(confirmation_text)),
            Text(""),
            button_pile([
                cancel_btn(_("No"), on_press=self.cancel),
                danger_btn(_("Continue"), on_press=self.ok)]),
        ]
        super().__init__(
            _("Confirm destructive action"),
            widgets,
            stretchy_index=0,
            focus_index=2)

    def ok(self, sender):
        self.controller.finish()

    def cancel(self, sender):
        self.parent.remove_overlay()

@attr.s
class MountInfo:
    mount = attr.ib(default=None)

    @property
    def path(self):
        return self.mount.path

    @property
    def split_path(self):
        return self.mount.path.split('/')

    @property
    def size(self):
        return humanize_size(self.mount.device.volume.size)

    @property
    def fstype(self):
        return self.mount.device.fstype

    @property
    def desc(self):
        return self.mount.device.volume.desc()

    def startswith(self, other):
        i = 0
        for a, b in zip(self.split_path, other.split_path):
            if a != b:
                break
            i += 1
        return i >= len(other.split_path)


class MountList(WidgetWrap):
    def __init__(self, parent):
        self.parent = parent
        self._mounts = [
            MountInfo(mount=m)
            for m in sorted(self.parent.model._mounts, key=lambda m: m.path)
        ]
        pile = Pile([])
        self._no_mounts_content = (
            Color.info_minor(Text(_("No disks or partitions mounted."))),
            pile.options('pack'))
        super().__init__(pile)
        parent.controller.signal.connect_signals([
            ('fs:add-mount', self._add_mount),
            ('fs:remove-mount', self._remove_mount),
            ])
        self._compute_contents()

    def _add_mount(self, mount):
        self._mounts.append(MountInfo(mount=mount))

    def _remove_mount(self, mount):
        self._mounts = [mi for mi in self._mounts if mi.mount is not mount]
        last = (self._w.focus_position ==
                    len(self._w.contents) - 1)
        self._compute_contents()
        if len(self._mounts) == 0:
            self.parent.keypress((10, 10), 'tab')  # hmm
        elif last:
            self._w.focus_position -= 1

    def _mount_action(self, sender, action, mount):
        log.debug('_mount_action %s %s', action, mount)
        if action == 'unmount':
            self.parent.model.remove_mount(mount)

    def _compute_contents(self):
        if len(self._mounts) == 0:
            self._w.contents[:] = [self._no_mounts_content]
            return
        log.debug('FileSystemView: building part list')
        mount_point_text = _("MOUNT POINT")
        longest_path = max([len(mount_point_text)] + [len(m.mount.path) for m in self._mounts])
        cols = []
        def col(action_menu, path, size, fstype, desc):
            c = Columns([
                (4,            action_menu),
                (longest_path, Text(path)),
                (size_width,   size),
                (type_width,   Text(fstype)),
                Text(desc),
            ], dividechars=1)
            cols.append((c, self._w.options('pack')))

        size_text = _("SIZE")
        type_text = _("TYPE")
        size_width = max(len(size_text), 9)
        type_width = max(len(type_text), self.parent.model.longest_fs_name)
        col(
            Text(""),
            mount_point_text,
            Text(size_text, align='center'),
            type_text,
            _("DEVICE TYPE"))

        actions = [(_("Unmount"), True, 'unmount')]
        for i, m1 in enumerate(self._mounts):
            path_markup = m1.path
            for j in range(i-1, -1, -1):
                m2 = self._mounts[j]
                if m1.startswith(m2):
                    path_markup = [
                        ('info_minor', "/".join(m1.split_path[:len(m2.split_path)])),
                        "/".join([''] + m1.split_path[len(m2.split_path):]),
                        ]
                    break
                if j == 0 and m2.split_path == ['', '']:
                    path_markup = [
                        ('info_minor', "/"),
                        "/".join(m1.split_path[1:]),
                        ]
            menu = ActionMenu(actions)
            connect_signal(menu, 'action', self._mount_action, m1.mount)
            col(
                menu,
                path_markup,
                Text(m1.size, align='right'),
                m1.fstype,
                m1.desc)
        self._w.contents[:] = cols

class FilesystemView(BaseView):
    title = _("Filesystem setup")
    footer = _("Select available disks to format and mount")

    def __init__(self, model, controller):
        log.debug('FileSystemView init start()')
        self.model = model
        self.controller = controller
        self.items = []

        self.raid_btn = Toggleable(
            menu_btn(
                label=_("Create software RAID (MD)"),
                on_press=self._click_raid))
        self._buttons = [self.raid_btn]
        # self._disable(self.raid_btn)

        body = [
            Text(_("FILE SYSTEM SUMMARY")),
            Text(""),
            MountList(self),
            Text(""),
            Text(_("AVAILABLE DEVICES AND PARTITIONS")),
            Text(""),
        ] + self._build_available_inputs() + [
            Text(""),
            Text(_("USED DEVICES AND PARTITIONS")),
            Text(""),
        ] + self._build_used_inputs() + [
            Text(""),
            button_pile([reset_btn(
                _("Reset all configuration"), on_press=self.reset)]),
        ]

        self._selected_devices = set()

        self.lb = Padding.center_95(ListBox(body))
        bottom = Pile([
            Text(""),
            self._build_buttons(),
            Text(""),
        ])
        self.frame = Pile([
            ('pack', Text("")),
            self.lb,
            ('pack', bottom)])
        if self.model.can_install():
            self.frame.focus_position = 2
        super().__init__(self.frame)
        log.debug('FileSystemView init complete()')

    def _build_used_disks(self):
        log.debug('FileSystemView: building used disks')
        return Color.info_minor(
            Text("No disks have been used to create a constructed disk."))

    def _build_buttons(self):
        log.debug('FileSystemView: building buttons')
        buttons = []

        # don't enable done botton if we can't install
        # XXX should enable/disable button rather than having it
        # appear/disappear I think
        if self.model.can_install():
            buttons.append(
                done_btn(_("Done"), on_press=self.done))

        buttons.append(back_btn(_("Back"), on_press=self.cancel))

        return button_pile(buttons)

    def _enable(self, btn):
        btn.enable()
        btn._original_widget.set_attr_map({None: 'menu'})

    def _disable(self, btn):
        btn.disable()
        btn._original_widget._original_widget.set_attr_map(
            {None: 'info_minor'})

    def _action(self, sender, action, obj):
        log.debug("_action %r %r", action, obj)
        if isinstance(obj, Disk):
            if action == 'info':
                from .disk_info import DiskInfoStretchy
                self.show_stretchy_overlay(DiskInfoStretchy(self, obj))
            elif action == 'partition':
                from .partition import PartitionStretchy
                self.show_stretchy_overlay(PartitionStretchy(self, obj))
            elif action == 'format':
                pass
        elif isinstance(obj, Partition):
            if action == 'edit':
                from .partition import PartitionStretchy
                self.show_stretchy_overlay(
                    PartitionStretchy(self, obj.device, obj))
            elif action == 'delete':
                pass
        elif isinstance(obj, Raid):
            if action == 'edit':
                from ..raid import RaidStretchy
                self.show_stretchy_overlay(RaidStretchy(self, obj))
            elif action == 'partition':
                from .partition import PartitionStretchy
                self.show_stretchy_overlay(PartitionStretchy(self, obj))

    def _build_device_rows(self, dev, available):
        label = Text(dev.label)
        size = Text(humanize_size(dev.size).rjust(9))
        typ = Text(dev.desc())
        device_actions = [
            (_("Information"), 'info'),
            (_("Edit"), 'edit'),
            (_("Add Partition"), 'partition'),
            (_("Format / Mount"), 'format'),
            (Color.danger_button(ActionMenuButton(_("Delete"))), 'delete'),
        ]
        action_menu = ActionMenu(
            [(label, dev.supports_action(action), action)
             for label, action in device_actions])
        connect_signal(action_menu, 'action', self._action, dev)
        r = [Columns([
            (3, action_menu),
            (42, label),
            (10, size),
            typ,
        ], 1)]
        if dev.fs() is not None or dev.raid() is not None:
            label = _("entire device")
            fs = dev.fs()
            if fs is not None:
                label += _(", formatted as: {}").format(fs.fstype)
                m = fs.mount()
                if m:
                    if available:
                        return []
                    label += _(", mounted at: {}").format(m.path)
                else:
                    label += _(", not mounted")
            if dev.raid() is not None:
                if available:
                    return []
                label += _(" is part of {} ({})").format(
                    dev.raid().name, dev.raid().desc())
            r.append(Columns([
                (3, Text("")),
                Text(label),
            ], 1))
            return r
        has_unavailable_partition = False
        has_available_partition = False
        for partition in dev.partitions():
            if partition.available:
                has_available_partition = True
            else:
                has_unavailable_partition = True
            if available != partition.available:
                continue
            part_label = _("  partition {}, ").format(partition._number)
            fs = partition.fs()
            if fs is not None:
                if fs.mount():
                    part_label += ("%-*s" % (
                        self.model.longest_fs_name + 2, fs.fstype + ',') +
                        fs.mount().path)
                else:
                    part_label += fs.fstype
            elif partition.raid() is not None:
                part_label += _("part of {}").format(partition.raid().name)
            elif partition.flag == "bios_grub":
                part_label += "bios_grub"
            else:
                part_label += _("unformatted")
            part_label = Text(part_label)
            part_size = Text("{:>9} ({}%)".format(
                humanize_size(partition.size),
                int(100 * partition.size / dev.size)))
            action_menu = ActionMenu(
                [(_(label), partition.supports_action(action), action)
                 for label, action in device_actions]
            )
            connect_signal(action_menu, 'action', self._action, partition)
            r.append(Columns([
                (3, action_menu),
                (42, part_label),
                part_size,
            ], 1))
        if not available and not has_unavailable_partition:
            return []
        if available and 0 < dev.used < dev.size:
            size = dev.size
            free = dev.free
            percent = str(int(100 * free / size))
            if percent == "0":
                percent = "%.2f" % (100 * free / size,)
            r.append(Columns([
                (3, Text("")),
                (42, Text(_("  free space"))),
                Text("{:>9} ({}%)".format(humanize_size(free), percent)),
            ], 1))
        elif (available and len(dev.partitions()) > 0 and
              not has_available_partition):
            return []
        return r

    def _build_available_inputs(self):
        r = []

        def col3(col1, col2, col3):
            col0 = Text("")
            inputs.append(
                Columns([(3, col0), (42, col1), (10, col2), col3], 1))

        def col2(col1, col2):
            inputs.append(Columns([(42, col1), col2], 1))

        def col1(col1):
            inputs.append(Columns([(42, col1)], 1))

        inputs = []
        col3(
            Text(_("DEVICE")),
            Text(_("SIZE"), align="center"),
            Text(_("TYPE")))
        r.append(Pile(inputs))

        for disk in self.model.all_devices():
            if disk.size < self.model.lower_size_limit:
                disk_label = Text(disk.label)
                size = Text(humanize_size(disk.size).rjust(9))
                typ = Text(disk.desc())
                col3(disk_label, size, typ)
                r.append(Color.info_minor(Pile(inputs)))
                continue
            r.extend(self._build_device_rows(disk, True))

        if len(r) == 1:
            return [
                Padding.push_3(
                    Color.info_minor(Text(_("No disks available."))))
            ]

        bp = button_pile(self._buttons)
        bp.align = 'left'
        r.append(Text(""))
        r.append(bp)

        return r

    def _build_used_inputs(self):
        r = []

        def col3(col1, col2, col3):
            col0 = Text("")
            inputs.append(
                Columns([(3, col0), (42, col1), (10, col2), col3], 1))

        def col2(col1, col2):
            inputs.append(Columns([(42, col1), col2], 1))

        def col1(col1):
            inputs.append(Columns([(42, col1)], 1))

        inputs = []
        col3(
            Text(_("DEVICE")),
            Text(_("SIZE"), align="center"),
            Text(_("TYPE")))
        r.append(Pile(inputs))

        for disk in self.model.all_devices():
            if disk.size < self.model.lower_size_limit:
                disk_label = Text(disk.label)
                size = Text(humanize_size(disk.size).rjust(9))
                typ = Text(disk.desc())
                col3(disk_label, size, typ)
                r.append(Color.info_minor(Pile(inputs)))
                continue
            r.extend(self._build_device_rows(disk, False))

        if len(r) == 1:
            return [
                Padding.push_3(
                    Color.info_minor(Text(_("No disks used yet."))))
            ]

        return r

    def _click_raid(self, sender):
        from ..raid import RaidStretchy
        self.show_stretchy_overlay(RaidStretchy(self, []))

    def cancel(self, button=None):
        self.controller.default()

    def reset(self, button):
        self.controller.reset()

    def done(self, button):
        self.show_stretchy_overlay(
            FilesystemConfirmation(self, self.controller))
