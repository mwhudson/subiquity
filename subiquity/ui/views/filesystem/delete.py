# Copyright 2018 Canonical, Ltd.
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
from urwid import Text

from subiquitycore.ui.buttons import danger_btn, other_btn
from subiquitycore.ui.table import ColSpec, TablePile, TableRow
from subiquitycore.ui.utils import button_pile
from subiquitycore.ui.stretchy import Stretchy

from subiquity.models.filesystem import humanize_size


log = logging.getLogger('subiquity.ui.filesystem.disk_info')


def summarize(obj):
    # [ label, size, annotations, usage comment ]
    rows = []
    for p in obj.partitions():
        row = [
            Text(p.short_label),
            Text(humanize_size(p.size), align='right'),
            ]
        usage = p.annotations[1:]
        fs = p.fs()
        if fs is not None:
            usage.append(fs.fstype)
            m = fs.mount()
            if m is not None:
                usage.append( _("mounted at {}".format(m.path)))
            elif fs._available():
                usage.append(_("not mounted"))
        cd = p.constructed_device()
        if cd is not None:
            usage.append(_("part of {desc} {label}").format(desc=cd.desc(), label=cd.label))
        if not usage:
            usage = ["unused"]
        row.append(Text(", ".join(usage)))
        rows.append(TableRow(row))
    return TablePile(rows, colspecs={2: ColSpec(can_shrink=True)})


class ConfirmDeleteStretchy(Stretchy):

    def __init__(self, parent, obj):
        self.parent = parent
        self.obj = obj

        title = _("Confirm deletion of {}").format(obj.desc())

        lines = [
            _("Do you really want to delete {}?").format(obj.label),
            "",
        ]
        fs = obj.fs()
        if fs is not None:
            m = fs.mount()
            if m is not None:
                lines.append(_(
                    "It is formatted as {fstype} and mounted at "
                    "{path}").format(
                        fstype=fs.fstype,
                        path=m.path))
            else:
                lines.append(_(
                    "It is formatted as {fstype} and not mounted.").format(
                        fstype=fs.fstype))
        else:
            lines.append(_("It is not formatted or mounted."))
        delete_btn = danger_btn(label=_("Delete"), on_press=self.confirm)
        widgets = [
            Text("\n".join(lines)),
            Text(""),
            button_pile([
                delete_btn,
                other_btn(label=_("Cancel"), on_press=self.cancel),
                ]),
        ]
        super().__init__(title, widgets, 0, 2)

    def confirm(self, sender=None):
        self.parent.controller.delete(self.obj)
        self.parent.refresh_model_inputs()
        self.parent.remove_overlay()

    def cancel(self, sender=None):
        self.parent.remove_overlay()



class ConfirmReformatStretchy(Stretchy):

    def __init__(self, parent, obj):
        self.parent = parent
        self.obj = obj

        fs = obj.fs()
        if fs is not None:
            title = _("Remove filesystem from {}").format(obj.desc())
            lines = [
                Text(_("Do you really want to remove the existing filesystem from {}?").format(obj.label)),
                Text(""),
            ]
            m = fs.mount()
            if m is not None:
                lines.append(Text(_(
                    "It is formatted as {fstype} and mounted at "
                    "{path}").format(
                        fstype=fs.fstype,
                        path=m.path)))
            else:
                lines.append(Text(_(
                    "It is formatted as {fstype} and not mounted.").format(
                        fstype=fs.fstype)))
        else:
            if obj.type == "lvm_volgroup":
                things = _("logical volumes")
            else:
                things = _("partitions")
            title = _("Remove all {things} from {obj}").format(things=things, obj=obj.desc())
            lines = [
                Text(_("Do you really want to remove all {things} from {obj}?").format(
                    things=things, obj=obj.label)),
                Text(""),
            ]
            lines.append(summarize(obj))

        delete_btn = danger_btn(label=_("Reformat"), on_press=self.confirm)
        widgets = lines + [
            Text(""),
            button_pile([
                delete_btn,
                other_btn(label=_("Cancel"), on_press=self.cancel),
                ]),
        ]
        super().__init__(title, widgets, 0, len(lines) + 1)

    def confirm(self, sender=None):
        self.parent.controller.reformat(self.obj)
        self.parent.refresh_model_inputs()
        self.parent.remove_overlay()

    def cancel(self, sender=None):
        self.parent.remove_overlay()
