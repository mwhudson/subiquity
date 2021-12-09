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

import attr

from subiquity.models.filesystem import (
    align_down,
    align_up,
    Disk,
    LVM_CHUNK_SIZE,
    LVM_VolGroup,
    GPT_OVERHEAD,
    Raid,
    )


@attr.s(auto_attribs=True)
class Gap:
    start: int
    size: int
    in_extended: bool = False


@functools.singledispatch
def parts_and_gaps(device):
    raise NotImplementedError(device)


ALIGN = 1 << 20
EBR_SPACE = 1 << 20
MIN_GAP_SIZE = 1 << 20


@parts_and_gaps.register(Disk)
@parts_and_gaps.register(Raid)
def _parts_and_gaps_raid_disk(device):
    prev_end = GPT_OVERHEAD // 2
    r = []

    def maybe_add_gap(start, end, in_extended):
        if end - start >= MIN_GAP_SIZE:
            r.append(Gap(start, end - start, in_extended))

    parts = sorted(device._partitions, key=lambda p: p.offset)
    extended_end = None

    for p in parts + [None]:
        if p is None:
            offset = align_down(device.size - GPT_OVERHEAD // 2)
        else:
            offset = p.offset

        aligned_gap_start = align_up(prev_end, ALIGN)
        if extended_end is not None:
            aligned_gap_start = min(
                extended_end, align_up(aligned_gap_start + EBR_SPACE, ALIGN))
        aligned_gap_end = align_down(offset, ALIGN)

        if extended_end is not None and aligned_gap_end >= extended_end:
            aligned_down_extended_end = align_down(extended_end, ALIGN)
            aligned_up_extended_end = align_up(extended_end, ALIGN)
            maybe_add_gap(aligned_gap_start, aligned_down_extended_end, True)
            maybe_add_gap(aligned_up_extended_end, aligned_gap_end, False)
        else:
            maybe_add_gap(
                aligned_gap_start,
                aligned_gap_end, extended_end is not None)

        if p is not None:
            r.append(p)
            if p.flag == "extended":
                prev_end = offset
                extended_end = offset + p.size
            else:
                prev_end = offset + p.size

    return r


@parts_and_gaps.register(LVM_VolGroup)
def _parts_and_gaps_vg(device):
    used = 0
    r = []
    for lv in device._partitions:
        r.append(lv)
        used += lv.size
    remaining = align_down(device.size - used, LVM_CHUNK_SIZE)
    if remaining >= LVM_CHUNK_SIZE:
        r.append(Gap(0, device.size - used))
    return r
