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


@attr.s(auto_attribs=True)
class GapFinder:
    part_align: int
    min_gap_size: int
    min_start_offset: int
    min_end_offset: int
    ebr_space: int = 0

    def au(self, v):  # au == "align up"
        r = v % self.part_align
        if r:
            return v + self.part_align - r
        else:
            return v

    def ad(self, v):  # ad == "align down"
        return v - v % self.part_align

    def maybe_add_gap(self, start, end):
        if end - start >= self.min_gap_size:
            self.result.append(Gap(start, end - start, self.in_extended))

    def find_gaps(self, device):
        self.result = []
        self.in_extended = False
        prev_end = self.min_start_offset

        parts = sorted(device._partitions, key=lambda p: p.offset)
        extended_end = None

        for part in parts + [None]:
            if part is None:
                gap_end = self.ad(device.size - self.min_end_offset)
            else:
                gap_end = self.ad(part.offset)

            gap_start = self.au(prev_end)

            if self.in_extended:
                gap_start = min(
                    extended_end, self.au(gap_start + self.ebr_space))

            if self.in_extended and gap_end >= extended_end:
                self.maybe_add_gap(gap_start, self.ad(extended_end))
                self.in_extended = False
                self.maybe_add_gap(self.au(extended_end), gap_end)
                extended_end = None
            else:
                self.maybe_add_gap(gap_start, gap_end)

            if part is None:
                break
            self.result.append(part)
            if part.flag == "extended":
                self.in_extended = True
                prev_end = part.offset
                extended_end = part.offset + part.size
            else:
                prev_end = part.offset + part.size

        return self.result


@parts_and_gaps.register(Disk)
@parts_and_gaps.register(Raid)
def _parts_and_gaps_raid_disk(device):
    finder = GapFinder(
        part_align=1 << 20,
        min_gap_size=1 << 20,
        min_start_offset=GPT_OVERHEAD // 2,
        min_end_offset=GPT_OVERHEAD // 2,
        ebr_space=1 << 20)
    return finder.find_gaps(device)


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
