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
    Gap,
    GPT_OVERHEAD,
    parts_and_gaps,
    )
from subiquity.models.tests.test_filesystem import (
    make_model,
    make_model_and_disk,
    make_model_and_partition,
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
        p_size = d.free_for_partitions//4
        p1 = make_partition(
            m, d, offset=GPT_OVERHEAD//2, size=p_size)
        p2 = make_partition(
            m, d, offset=d.size - GPT_OVERHEAD//2 - p_size, size=p_size)
        self.assertEqual(
            parts_and_gaps(d),
            [
                p1,
                Gap(GPT_OVERHEAD//2 + p_size, p_size*2),
                p2,
            ])

    
