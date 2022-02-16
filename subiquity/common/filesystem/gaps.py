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
from typing import Optional

import attr

from subiquity.models.filesystem import (
    align_down,
    Disk,
    LVM_CHUNK_SIZE,
    LVM_VolGroup,
    GPT_OVERHEAD,
    Raid,
    )


@attr.s(auto_attribs=True)
class Gap:
    device: object
    start: Optional[int]
    size: int
    in_extended: bool = False

    type: str = 'gap'

    @property
    def id(self):
        return 'gap-' + self.device.id


@functools.singledispatch
def parts_and_gaps(device):
    raise NotImplementedError(device)


ALIGN = 1 << 20
EBR_SPACE = 1 << 20
MIN_GAP_SIZE = 1 << 20


@attr.s(auto_attribs=True)
class ParttableInfo:
    part_align: int
    min_gap_size: int
    min_start_offset: int
    min_end_offset: int
    ebr_space: int = 0


ONE_MB = 1 << 20

gpt_info = ParttableInfo(
    part_align=ONE_MB,
    min_gap_size=ONE_MB,
    min_start_offset=GPT_OVERHEAD//2,
    min_end_offset=GPT_OVERHEAD//2)

dos_info = ParttableInfo(
    part_align=ONE_MB,
    min_gap_size=ONE_MB,
    min_start_offset=GPT_OVERHEAD//2,
    min_end_offset=0,
    ebr_space=ONE_MB)


@parts_and_gaps.register(Disk)
@parts_and_gaps.register(Raid)
def find_disk_gaps(device, info=None):
    if info is None:
        if device.ptable in [None, 'gpt']:
            info = gpt_info
        elif device.ptable in ['dos', 'msdos']:
            info = dos_info

    result = []
    extended_end = None

    def au(v):  # au == "align up"
        r = v % info.part_align
        if r:
            return v + info.part_align - r
        else:
            return v

    def ad(v):  # ad == "align down"
        return v - v % info.part_align

    def maybe_add_gap(start, end, in_extended):
        if end - start >= info.min_gap_size:
            result.append(Gap(device, start, end - start, in_extended))

    prev_end = info.min_start_offset

    parts = sorted(device._partitions, key=lambda p: p.offset)
    extended_end = None

    for part in parts + [None]:
        if part is None:
            gap_end = ad(device.size - info.min_end_offset)
        else:
            gap_end = ad(part.offset)

        gap_start = au(prev_end)

        if extended_end is not None:
            gap_start = min(
                extended_end, au(gap_start + info.ebr_space))

        if extended_end is not None and gap_end >= extended_end:
            maybe_add_gap(gap_start, ad(extended_end), True)
            maybe_add_gap(au(extended_end), gap_end, False)
            extended_end = None
        else:
            maybe_add_gap(gap_start, gap_end, extended_end is not None)

        if part is None:
            break

        result.append(part)

        if part.flag == "extended":
            prev_end = part.offset
            extended_end = part.offset + part.size
        else:
            prev_end = part.offset + part.size

    return result


@parts_and_gaps.register(LVM_VolGroup)
def _parts_and_gaps_vg(device):
    used = 0
    r = []
    for lv in device._partitions:
        r.append(lv)
        used += lv.size
    if device.preserve:
        return r
    remaining = align_down(device.size - used, LVM_CHUNK_SIZE)
    if remaining >= LVM_CHUNK_SIZE:
        r.append(Gap(device, None, remaining))
    return r


def largest_gap(device):
    largest_size = 0
    largest = None
    for pg in parts_and_gaps(device):
        if isinstance(pg, Gap):
            if pg.size > largest_size:
                largest = pg
                largest_size = pg.size
    return largest


def largest_gap_size(device):
    largest = largest_gap(device)
    if largest is not None:
        return largest.size
    return 0
