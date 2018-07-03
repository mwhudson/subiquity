# Copyright 2017 Canonical, Ltd.
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

from subiquitycore.ui.buttons import (
    back_btn,
    cancel_btn,
    ok_btn,
    )
from subiquitycore.ui.container import ListBox
from subiquitycore.ui.table import (
    ColSpec,
    TableListBox,
    TableRow,
    )
from subiquitycore.ui.utils import (
    button_pile,
    ClickableIcon,
    Color,
    Padding,
    screen,
    )
from subiquitycore.view import BaseView

from subiquity.models.filesystem import humanize_size

log = logging.getLogger("subiquity.ui.views.filesystem.guided")


text = _("""The installer can guide you through partitioning an entire disk \
or, if you prefer, you can do it manually.

If you choose to partition an entire disk you will still have a chance to \
review and modify the results.""")


class GuidedFilesystemView(BaseView):

    title = _("Filesystem setup")
    footer = _("Choose guided or manual partitioning")

    def __init__(self, controller):
        self.controller = controller
        direct = ok_btn(
            _("Use An Entire Disk"), on_press=self.guided, user_arg="direct")
        lvm = ok_btn(
            _("Use An Entire Disk And Set Up LVM"), on_press=self.guided,
            user_arg="lvm")
        manual = ok_btn(_("Manual"), on_press=self.manual)
        back = back_btn(_("Back"), on_press=self.cancel)
        lb = ListBox([
            Padding.center_70(Text("")),
            Padding.center_70(Text(_(text))),
            Padding.center_70(Text("")),
            button_pile([direct, lvm, manual, back]),
            ])
        super().__init__(lb)

    def manual(self, btn):
        self.controller.manual()

    def guided(self, btn, method):
        self.controller.guided(method)

    def cancel(self, btn=None):
        self.controller.cancel()


class GuidedDiskSelectionView(BaseView):

    title = _("Filesystem setup")
    footer = (_("Choose the installation target"))

    def __init__(self, model, controller, method):
        self.model = model
        self.controller = controller
        self.method = method
        cancel = cancel_btn(_("Cancel"), on_press=self.cancel)
        rows = []
        for disk in self.model.all_disks():
            if disk.size >= model.lower_size_limit:
                disk_btn = ClickableIcon(disk.label)
                connect_signal(
                    disk_btn, 'click', self.choose_disk, disk)
                attr = Color.done_button
            else:
                disk_btn = Text("  "+disk.label)
                attr = Color.info_minor
            rows.append(attr(TableRow([
                Text('['),
                disk_btn,
                Text(humanize_size(disk.size), align='right'),
                Text('\N{BLACK RIGHT-POINTING SMALL TRIANGLE}'),
                Text(']'),
                ])))
        super().__init__(screen(
            TableListBox(rows, spacing=1, colspecs={
                1: ColSpec(can_shrink=True, min_width=20, rpad=2),
                2: ColSpec(min_width=9),
                }),
            button_pile([cancel]),
            focus_buttons=False,
            excerpt=_("Choose the disk to install to:")))

    def cancel(self, btn=None):
        self.controller.default()

    def choose_disk(self, btn, disk):
        self.model.reset()
        if self.method == "direct":
            result = {
                "size": disk.free_for_partitions,
                "fstype": self.model.fs_by_name["ext4"],
                "mount": "/",
                }
            self.controller.partition_disk_handler(disk, None, result)
        else:
            self.controller.make_boot_disk(disk)
            part = self.controller.create_partition(
                device=disk, spec=dict(
                    size=disk.free_for_partitions,
                    fstype=None,
                    ))
            vg = self.controller.create_volgroup(
                spec=dict(
                    name="ubuntu-vg",
                    devices=set([part]),
                    ))
            self.controller.create_logical_volume(
                vg=vg, spec=dict(
                    size=vg.free_for_partitions*4//5,
                    name="ubuntu-lv",
                    fstype=self.model.fs_by_name['ext4'],
                    mount="/",
                    ))
        self.controller.manual()
