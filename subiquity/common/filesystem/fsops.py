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

from subiquity.common.filesystem import fsutils
from subiquity.models.filesystem import (
    Disk,
    DM_Crypt,
    GPT_OVERHEAD,
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
    return fsutils.align_down(disk._info.size)


@size.register(Partition)
@size.register(LVM_LogicalVolume)
def _attr_size(device):
    return device.size


@size.register(Raid)
def _raid_size(raid):
    return fsutils.get_raid_size(raid.raidlevel, raid.devices)


@size.register(LVM_VolGroup)
def _vg_size(vg):
    return fsutils.get_lvm_size(vg.devices)


@size.register(DM_Crypt)
def _crypt_size(crypt):
    return size(crypt.volume) - LUKS_OVERHEAD


def _used_generic(device):
    r = 0
    for p in device._partitions:
        if p.flag == "extended":
            continue
        r += p.size
    return r


@functools.singledispatch
def used(device):
    raise NotImplementedError(repr(device))


@used.register(Disk)
@used.register(Raid)
def _used_formattable(device):
    if device._fs is not None or device._constructed_device is not None:
        return size(device)
    return _used_generic(device)


used.register(LVM_VolGroup, _used_generic)


@functools.singledispatch
def available_for_partitions(device):
    raise NotImplementedError(repr(device))


@available_for_partitions.register(Disk)
@available_for_partitions.register(Raid)
def _available_for_partitions_gpt(device):
    return size(device) - GPT_OVERHEAD


@available_for_partitions.register(LVM_VolGroup)
def _available_for_partitions_vg(vg):
    return size(vg)


def free_for_partitions(device):
    return available_for_partitions(device) - used(device)


@functools.singledispatch
def ptable_for_new_partition(device):
    if device.ptable is not None:
        return device.ptable
    return 'gpt'


@ptable_for_new_partition.register(Disk)
def _ptable_for_new_partition_disk(disk):
    if disk.ptable is not None:
        return disk.ptable
    dasd_config = disk._m._probe_data.get('dasd', {}).get(disk.path)
    if dasd_config is not None:
        if dasd_config['type'] == "FBA":
            return 'msdos'
        else:
            return 'vtoc'
    return 'gpt'


@functools.singledispatch
def available(device):
    # A _Device is available if:
    # 1) it is not part of a device like a RAID or LVM or zpool or ...
    # 2) if it is formatted, it is available if it is formatted with fs
    #    that needs to be mounted and is not mounted
    # 3) if it is not formatted, it is available if it has free
    #    space OR at least one partition is not formatted or is formatted
    #    with a fs that needs to be mounted and is not mounted
    raise NotImplementedError(repr(device))


def _available_formattable(device):
    # A _Device is available if:
    # 1) it is not part of a device like a RAID or LVM or zpool or ...
    # 2) if it is formatted, it is available if it is formatted with fs
    #    that needs to be mounted and is not mounted
    # 3) if it is not formatted, it is available if it has free
    #    space OR at least one partition is not formatted or is formatted
    #    with a fs that needs to be mounted and is not mounted
    if device._constructed_device is not None:
        return False
    if device._fs is not None:
        return device._fs._available()
    return True


def _available_partitionable(device):
    if free_for_partitions(device) > 0:
        if not has_preexisting_partition(device):
            return True
    return any(available(p) for p in device._partitions)


available.register(LVM_VolGroup, _available_partitionable)
available.register(LVM_LogicalVolume, _available_formattable)


@available.register(Partition)
def _available_partition(partition):
    if partition.flag in ['bios_grub', 'prep'] or partition.grub_device:
        return False
    return _available_formattable(partition)


@available.register(Disk)
@available.register(Raid)
def _available_formattable_partitionable(device):
    if device._constructed_device is not None:
        return False
    if device._fs is not None:
        return device._fs._available()
    if free_for_partitions(device) > 0:
        if not has_preexisting_partition(device):
            return True
    return any(available(p) for p in device._partitions)


def has_preexisting_partition(device):
    return any(p.preserve for p in device._partitions)


def has_unavailable_partition(device):
    return any(not available(p) for p in device._partitions)


@functools.singledispatch
def ok_for_raid(device):
    raise NotImplementedError(repr(device))


@ok_for_raid.register(Disk)
@ok_for_raid.register(Raid)
def _ok_for_raid_disk_raid(device):
    if device._fs is not None:
        if device._fs.preserve:
            return device._fs._mount is None
        return False
    if device._constructed_device is not None:
        return False
    if len(device._partitions) > 0:
        return False
    return True


@ok_for_raid.register(Partition)
def _ok_for_raid_partition(partition):
    from subiquity.common.filesystem import boot
    if boot.is_bootloader_partition(partition):
        return False
    if partition._fs is not None:
        if partition._fs.preserve:
            return partition._fs._mount is None
        return False
    if partition._constructed_device is not None:
        return False
    return True


@ok_for_raid.register(LVM_VolGroup)
@ok_for_raid.register(LVM_LogicalVolume)
def _ok_for_raid_no(device):
    return False


ok_for_lvm_vg = ok_for_raid


def original_fstype(device):
    for action in device._m._orig_config:
        if action['type'] == 'format' and action['volume'] == device.id:
            return action['fstype']
    for action in device._m._orig_config:
        if action['id'] == device.id and action.get('flag') == 'swap':
            return 'swap'
    return None
