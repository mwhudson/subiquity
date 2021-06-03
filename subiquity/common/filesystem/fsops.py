# Copyright 2021 Canonical, Ltd.
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

import functools

from subiquity.models.filesystem import (
    align_down,
    Disk,
    get_lvm_size,
    get_raid_size,
    DM_Crypt,
    LUKS_OVERHEAD,
    LVM_LogicalVolume,
    LVM_VolGroup,
    Partition,
    Raid,
    )


@functools.singledispatch
def size(device):
    raise NotImplementedError(repr(device))


@size.register(Disk)
def _disk_size(disk):
    return align_down(disk._info.size)


@size.register(Partition)
@size.register(LVM_LogicalVolume)
def _attr_size(device):
    return device.size


@size.register(Raid)
def _raid_size(raid):
    return get_raid_size(raid.raidlevel, raid.devices)


@size.register(LVM_VolGroup)
def _vg_size(vg):
    return get_lvm_size(vg.devices)


@size.register(DM_Crypt)
def _crypt_size(crypt):
    return size(crypt.volume) - LUKS_OVERHEAD


def used(device):
    if device._fs is not None or device._constructed_device is not None:
        return size(device)
    r = 0
    for p in device._partitions:
        if p.flag == "extended":
            continue
        r += p.size
    return r
