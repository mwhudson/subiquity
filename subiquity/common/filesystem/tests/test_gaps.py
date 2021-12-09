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


import unittest

from subiquity.common.filesystem.gaps import (
    ALIGN,
    EBR_SPACE,
    Gap,
    parts_and_gaps,
    )
from subiquity.models.filesystem import (
    align_down,
    align_up,
    GPT_OVERHEAD,
    )
from subiquity.models.tests.test_filesystem import (
    make_model_and_disk,
    make_partition,
    )


class TestDiskGaps(unittest.TestCase):

    def test_no_partition(self):
        size = 1 << 30
        m, d = make_model_and_disk(size=size)
        self.assertEqual(
            parts_and_gaps(d),
            [Gap(GPT_OVERHEAD//2, size - GPT_OVERHEAD, False)])

    def test_all_partition(self):
        size = 1 << 30
        m, d = make_model_and_disk(size=size)
        p = make_partition(
            m, d, offset=GPT_OVERHEAD//2, size=d.free_for_partitions)
        self.assertEqual(
            parts_and_gaps(d),
            [p])

    def test_half_partition(self):
        size = 1 << 30
        m, d = make_model_and_disk(size=size)
        p = make_partition(
            m, d, offset=GPT_OVERHEAD//2, size=d.free_for_partitions//2)
        self.assertEqual(
            parts_and_gaps(d),
            [
                p,
                Gap(GPT_OVERHEAD//2 + p.size, p.size),
            ])

    def test_gap_in_middle(self):
        size = 1 << 30
        m, d = make_model_and_disk(size=size)
        p_size = align_down(d.free_for_partitions//4, ALIGN)
        p1 = make_partition(
            m, d, offset=GPT_OVERHEAD//2, size=p_size)
        p2 = make_partition(
            m, d, offset=d.size - GPT_OVERHEAD//2 - p_size, size=p_size)
        self.assertEqual(
            parts_and_gaps(d),
            [
                p1,
                Gap(
                    GPT_OVERHEAD//2 + p_size,
                    d.available_for_partitions - p_size*2),
                p2,
            ])

    def test_all_extended(self):
        size = 1 << 30
        m, d = make_model_and_disk(size=size, ptable='dos')
        p = make_partition(
            m, d, offset=GPT_OVERHEAD//2, size=d.free_for_partitions,
            flag='extended')
        self.assertEqual(
            parts_and_gaps(d),
            [
                p,
                Gap(
                    GPT_OVERHEAD//2 + EBR_SPACE,
                    p.size - EBR_SPACE,
                    True),
            ])

    def test_half_extended(self):
        size = 1 << 30
        m, d = make_model_and_disk(size=size, ptable='dos')
        p = make_partition(
            m, d, offset=GPT_OVERHEAD//2, size=d.free_for_partitions//2,
            flag='extended')
        self.assertEqual(
            parts_and_gaps(d),
            [
                p,
                Gap(
                    GPT_OVERHEAD//2 + EBR_SPACE,
                    p.size - EBR_SPACE,
                    True),
                Gap(
                    GPT_OVERHEAD//2 + p.size,
                    d.available_for_partitions - p.size,
                    False),
            ])

    def test_half_extended_one_logical(self):
        size = 1 << 30
        m, d = make_model_and_disk(size=size, ptable='dos')
        p1 = make_partition(
            m, d, offset=GPT_OVERHEAD//2, size=d.free_for_partitions//2,
            flag='extended')
        p2 = make_partition(
            m, d, offset=GPT_OVERHEAD//2 + EBR_SPACE, size=p1.size,
            flag='logical')
        self.assertEqual(
            parts_and_gaps(d),
            [
                p1,
                p2,
                Gap(
                    GPT_OVERHEAD//2 + p1.size,
                    d.available_for_partitions - p1.size,
                    False),
            ])

    def test_half_extended_one_logical(self):
        size = 1 << 30
        m, d = make_model_and_disk(size=size, ptable='dos')
        p1 = make_partition(
            m, d, offset=GPT_OVERHEAD//2, size=d.free_for_partitions//2,
            flag='extended')
        p2 = make_partition(
            m, d, offset=GPT_OVERHEAD//2 + EBR_SPACE, size=p1.size,
            flag='logical')
        self.assertEqual(
            parts_and_gaps(d),
            [
                p1,
                p2,
                Gap(
                    GPT_OVERHEAD//2 + p1.size,
                    d.available_for_partitions - p1.size,
                    False),
            ])

    def test_half_extended_half_logical(self):
        size = 1 << 30
        m, d = make_model_and_disk(size=size, ptable='dos')
        p1 = make_partition(
            m, d, offset=GPT_OVERHEAD//2, size=d.free_for_partitions//2,
            flag='extended')
        p2 = make_partition(
            m, d, offset=GPT_OVERHEAD//2 + EBR_SPACE,
            size=align_down(p1.size//2), flag='logical')
        self.assertEqual(
            parts_and_gaps(d),
            [
                p1,
                p2,
                Gap(
                    GPT_OVERHEAD//2 + EBR_SPACE + p2.size + EBR_SPACE,
                    p1.size - p2.size - 2*EBR_SPACE,
                    True),
                Gap(
                    GPT_OVERHEAD//2 + p1.size,
                    d.available_for_partitions - p1.size,
                    False),
            ])
