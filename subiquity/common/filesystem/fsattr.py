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

import attr

from curtin.util import human2bytes


def _conv_size(s):
    if isinstance(s, str):
        if '%' in s:
            return s
        return int(human2bytes(s))
    return s


def ref(*, backlink=None):
    metadata = {'ref': True}
    if backlink:
        metadata['backlink'] = backlink
    return attr.ib(metadata=metadata)


def reflist(*, backlink=None, default=attr.NOTHING):
    metadata = {'reflist': True}
    if backlink:
        metadata['backlink'] = backlink
    return attr.ib(metadata=metadata, default=default)


def backlink(*, default=None):
    return attr.ib(
        init=False, default=default, metadata={'is_backlink': True})


def const(value):
    return attr.ib(default=value)


def size():
    return attr.ib(converter=_conv_size)


def ptable():

    def conv(val):
        if val == "dos":
            val = "msdos"
        return val
    return attr.ib(default=None, converter=conv)
