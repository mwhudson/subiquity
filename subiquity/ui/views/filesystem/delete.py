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
from urwid import Text, WidgetDisable

from subiquitycore.ui.buttons import danger_btn, other_btn
from subiquitycore.ui.utils import button_pile, Color
from subiquitycore.ui.stretchy import Stretchy

from subiquity.models.filesystem import (
    _Device,
    get_raid_size,
    get_lvm_size,
    humanize_size,
    LVM_VolGroup,
    Raid,
    raidlevels_by_value,
)


log = logging.getLogger('subiquity.ui.filesystem.disk_info')


def check_size_reduction_ok(obj, new_sizes):
    # log.debug(
    #     "checking size reduction of %s with %s",
    #     obj.id,
    #     {k.id: "{} vs {}".format(humanize_size(v), humanize_size(k.size))
    #          for k,v in new_sizes.items()})
    if obj.fs():
        return True, ""
    cd = obj.constructed_device()
    if isinstance(cd, Raid):
        newer_sizes = new_sizes.copy()
        newer_sizes[cd] = get_raid_size(cd.raidlevel, cd.devices, new_sizes)
        return check_size_reduction_ok(cd, newer_sizes)
    elif isinstance(cd, LVM_VolGroup):
        newer_sizes = new_sizes.copy()
        newer_sizes[cd] = get_lvm_size(cd.devices, new_sizes)
        return check_size_reduction_ok(cd, newer_sizes)
    if not hasattr(obj, 'free_for_partitions'):
        return True, ""
    shrinkage = obj.size - new_sizes.get(obj)
    # log.debug("%s will shrink by %s vs free %s",
    #           obj.id, shrinkage, obj.free_for_partitions)
    if obj.free_for_partitions >= shrinkage:
        return True, ""
    else:
        if obj.free_for_partitions == 0:
            free = "no space"
        else:
            free = humanize_size(obj.free_for_partitions)
        return False, _("{} would shrink by {}, but it has {} free").format(
            obj.label, humanize_size(shrinkage), free)


def can_delete(obj, obj_desc=_("it")):
    if isinstance(obj, _Device):
        for p in obj.partitions():
            ok, reason = can_delete(p, obj_desc=p.short_label)
            if not ok:
                return False, reason
    cd = obj.constructed_device()
    if cd is None:
        return True, ""
    if isinstance(cd, Raid):
        rl = raidlevels_by_value[cd.raidlevel]
        if len(cd.devices) > rl.min_devices:
            new_devices = set(cd.devices) - set([obj])
            new_size = get_raid_size(cd.raidlevel, new_devices)
            if new_size == cd.size:
                return True, ""
            return check_size_reduction_ok(cd, {cd: new_size})
        else:
            reason = _("deleting {obj} would leave the {desc} {label} with "
                       "less than {min_devices} devices.").format(
                        obj=_(obj_desc),
                        desc=cd.desc(),
                        label=cd.label,
                        min_devices=rl.min_devices)
            return False, reason
    elif isinstance(cd, LVM_VolGroup):
        if len(cd.devices) > 1:
            new_devices = set(cd.devices) - set([obj])
            new_size = get_lvm_size(new_devices)
            return check_size_reduction_ok(cd, {cd: new_size})
        reason = _("deleting {obj} would leave the {desc} {label} with "
                   "no devices.").format(
                       obj=_(obj_desc),
                       desc=cd.desc(),
                       label=cd.label)
        return False, reason
    else:
        raise Exception("unexpected constructed device {}".format(cd.label))


def make_device_remover(cd, obj, spare=False):

    def remover():
        if spare:
            cd.spare_devices.remove(obj)
        else:
            cd.devices.remove(obj)
        obj._constructed_device = None
    return remover


def make_device_deleter(controller, obj):
    meth = getattr(controller, 'delete_' + obj.type)

    def remover():
        meth(obj)
    return remover


def delete_consequences(controller, obj, obj_desc=_("It")):
    log.debug("building consequences for deleting %s", obj.label)
    deleter = (
        "delete {} {}".format(obj.type, obj.label),
        make_device_deleter(controller, obj),
    )
    if isinstance(obj, _Device):
        if len(obj.partitions()) > 0:
            lines = [_("Proceeding will delete the following partitions:"), ""]
            delete_funcs = []
            for p in obj.partitions():
                desc = _("{}, which").format(p.short_label.title())
                new_lines, new_delete_funcs = delete_consequences(
                    controller, p, desc)
                lines.extend(new_lines)
                lines.append("")
                delete_funcs.extend(new_delete_funcs)
            return lines[:-1], delete_funcs + [deleter]
        if isinstance(obj, LVM_VolGroup):
            unused_desc = _("{} has no logical volumes.").format(obj_desc)
        else:
            unused_desc = _("{} is not formatted, partitioned, or part of any "
                            "constructed device.").format(obj_desc)
    else:
        unused_desc = _("{} is not formatted or part of any constructed "
                        "device.").format(obj_desc)
    fs = obj.fs()
    cd = obj.constructed_device()
    if fs is not None:
        desc = _("{} is formatted as {}").format(obj_desc, fs.fstype)
        if fs.mount():
            desc += _(" and mounted at {}.").format(fs.mount().path)
        else:
            desc += _(" and not mounted.")
        return [desc], [deleter]
    elif cd is not None:
        if isinstance(cd, Raid):
            delete_funcs = [(
                "remove {} from {}".format(obj.label, cd.name),
                make_device_remover(cd, obj, spare=obj in cd.spare_devices),
                ),
                deleter,
            ]
            return [
                _("{} is part of the {} {}. {} will be left with {} "
                  "devices.").format(
                    obj_desc,
                    cd.desc(),
                      cd.label,
                      cd.label,
                      len(cd.devices) - 1),
                ], delete_funcs
        if isinstance(cd, LVM_VolGroup):
            delete_funcs = [(
                "remove {} from {}".format(obj.label, cd.name),
                make_device_remover(cd, obj),
                ),
                deleter,
            ]
            return [
                _("{} is part of the {} {}. {} will be left with {} "
                  "devices.").format(
                    obj_desc,
                    cd.desc(),
                      cd.label,
                      cd.label,
                      len(cd.devices) - 1),
                ], delete_funcs
        else:
            raise Exception(
                "unexpected constructed device {}".format(cd.label))
    else:
        return [unused_desc], [deleter]


class ConfirmDeleteStretchy(Stretchy):

    def __init__(self, parent, obj):
        self.parent = parent
        self.obj = obj

        delete_ok, reason = can_delete(obj)
        if delete_ok:
            title = _("Confirm deletion of {}").format(obj.desc())

            lines = [
                _("Do you really want to delete {}?").format(obj.label),
                "",
            ]
            new_lines, delete_funcs = delete_consequences(
                self.parent.controller, obj)
            lines.extend(new_lines)
            self.delete_funcs = delete_funcs
        else:
            title = "Cannot delete {}".format(obj.desc())
            lines = [
                _("Cannot delete {} because {}").format(obj.label, reason)]
        delete_btn = danger_btn(label=_("Delete"), on_press=self.confirm)
        if not delete_ok:
            delete_btn = WidgetDisable(
                Color.info_minor(
                    delete_btn.original_widget))
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
        for desc, func in self.delete_funcs:
            log.debug("executing delete_func %s", desc)
            func()
        self.parent.refresh_model_inputs()
        self.parent.remove_overlay()

    def cancel(self, sender=None):
        self.parent.remove_overlay()
