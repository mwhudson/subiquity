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

import logging
import math

import attr

log = logging.getLogger('subiquity.common.filesystem.fsutils')


@attr.s(cmp=False)
class RaidLevel:
    name = attr.ib()
    value = attr.ib()
    min_devices = attr.ib()
    supports_spares = attr.ib(default=True)


raidlevels = [
    # for translators: this is a description of a RAID level
    RaidLevel(_("0 (striped)"),  "raid0",  2, False),
    # for translators: this is a description of a RAID level
    RaidLevel(_("1 (mirrored)"), "raid1",  2),
    RaidLevel(_("5"),            "raid5",  3),
    RaidLevel(_("6"),            "raid6",  4),
    RaidLevel(_("10"),           "raid10", 4),
    ]


def _raidlevels_by_value():
    r = {level.value: level for level in raidlevels}
    for n in 0, 1, 5, 6, 10:
        r[str(n)] = r[n] = r["raid"+str(n)]
    r["stripe"] = r["raid0"]
    r["mirror"] = r["raid1"]
    return r


raidlevels_by_value = _raidlevels_by_value()

HUMAN_UNITS = ['B', 'K', 'M', 'G', 'T', 'P']


def humanize_size(size):
    if size == 0:
        return "0B"
    p = int(math.floor(math.log(size, 2) / 10))
    # We want to truncate the non-integral part, not round to nearest.
    s = "{:.17f}".format(size / 2 ** (10 * p))
    i = s.index('.')
    s = s[:i + 4]
    return s + HUMAN_UNITS[int(p)]


def dehumanize_size(size):
    # convert human 'size' to integer
    size_in = size

    if not size:
        # Attempting to convert input to a size
        raise ValueError(_("input cannot be empty"))

    if not size[-1].isdigit():
        suffix = size[-1].upper()
        size = size[:-1]
    else:
        suffix = None

    parts = size.split('.')
    if len(parts) > 2:
        raise ValueError(
            # Attempting to convert input to a size
            _("{input!r} is not valid input").format(input=size_in))
    elif len(parts) == 2:
        div = 10 ** len(parts[1])
        size = parts[0] + parts[1]
    else:
        div = 1

    try:
        num = int(size)
    except ValueError:
        raise ValueError(
            # Attempting to convert input to a size
            _("{input!r} is not valid input").format(input=size_in))

    if suffix is not None:
        if suffix not in HUMAN_UNITS:
            raise ValueError(
                # Attempting to convert input to a size
                "unrecognized suffix {suffix!r} in {input!r}".format(
                    suffix=size_in[-1], input=size_in))
        mult = 2 ** (10 * HUMAN_UNITS.index(suffix))
    else:
        mult = 1

    if num < 0:
        # Attempting to convert input to a size
        raise ValueError("{input!r}: cannot be negative".format(input=size_in))

    return num * mult // div


DEFAULT_CHUNK = 512


# The calculation of how much of a device mdadm uses for raid is more than a
# touch ridiculous. What follows is a translation of the code at:
# https://git.kernel.org/pub/scm/utils/mdadm/mdadm.git/tree/super1.c,
# specifically choose_bm_space and the end of validate_geometry1. Note that
# that calculations are in terms of 512-byte sectors.
#
# We make some assumptions about the defaults mdadm uses but mostly that the
# default metadata version is 1.2, and other formats use less space.
#
# Note that data_offset is computed for the first disk mdadm examines and then
# used for all devices, so the order matters! (Well, if the size of the
# devices vary, which is not normal but also not something we prevent).
#
# All this is tested against reality in ./scripts/get-raid-sizes.py
def calculate_data_offset_bytes(devsize):
    # Convert to sectors to make it easier to compare this code to mdadm's (we
    # convert back at the end)
    devsize >>= 9

    devsize = align_down(devsize, DEFAULT_CHUNK)

    # conversion of choose_bm_space:
    if devsize < 64*2:
        bmspace = 0
    elif devsize - 64*2 >= 200*1024*1024*2:
        bmspace = 128*2
    elif devsize - 4*2 > 8*1024*1024*2:
        bmspace = 64*2
    else:
        bmspace = 4*2

    # From the end of validate_geometry1, assuming metadata 1.2.
    headroom = 128*1024*2
    while (headroom << 10) > devsize and headroom / 2 >= DEFAULT_CHUNK*2*2:
        headroom >>= 1

    data_offset = 12*2 + bmspace + headroom
    log.debug(
        "get_raid_size: adjusting for %s sectors of overhead", data_offset)
    data_offset = align_up(data_offset, 2*1024)

    # convert back to bytes
    return data_offset << 9


def raid_device_sort(devices):
    # Because the device order matters to mdadm, we sort consistently but
    # arbitrarily when computing the size and when rendering the config (so
    # curtin passes the devices to mdadm in the order we calculate the size
    # for)
    return sorted(devices, key=lambda d: d.id)


def get_raid_size(level, devices):
    from subiquity.common.filesystem import fsops
    if len(devices) == 0:
        return 0
    devices = raid_device_sort(devices)
    data_offset = calculate_data_offset_bytes(fsops.size(devices[0]))
    sizes = [align_down(fsops.size(dev) - data_offset) for dev in devices]
    min_size = min(sizes)
    if min_size <= 0:
        return 0
    if level == "raid0":
        return sum(sizes)
    elif level == "raid1":
        return min_size
    elif level == "raid5":
        return min_size * (len(devices) - 1)
    elif level == "raid6":
        return min_size * (len(devices) - 2)
    elif level == "raid10":
        return min_size * (len(devices) // 2)
    else:
        raise ValueError("unknown raid level %s" % level)


# These are only defaults but curtin does not let you change/specify
# them at this time.
LVM_OVERHEAD = (1 << 20)
LVM_CHUNK_SIZE = 4 * (1 << 20)


def get_lvm_size(devices, size_overrides={}):
    from subiquity.common.filesystem import fsops
    r = 0
    for d in devices:
        r += align_down(
            size_overrides.get(d, fsops.size(d)) - LVM_OVERHEAD,
            LVM_CHUNK_SIZE)
    return r


def align_up(size, block_size=1 << 20):
    return (size + block_size - 1) & ~(block_size - 1)


def align_down(size, block_size=1 << 20):
    return size & ~(block_size - 1)
