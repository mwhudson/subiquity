# Copyright 2019 Canonical, Ltd.
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

from urwid import Text

from subiquitycore.ui.utils import (
    Color,
    )

from subiquity.common.filesystem import labels
from subiquity.models.filesystem import (
    humanize_size,
    )


def summarize_device(device, part_filter=lambda p: True):
    """Return content for a table summarizing device.

    This (obj, cells) where obj is either device itself, a partition of
    device or None and cells is part of an argument to TableRow that
    will span 4 columns that describes device or a partition of
    device. This sounds a bit strange but hopefully you can figure it
    out by looking at the uses of this function.
    """
    label = labels.label(device)
    anns = labels.annotations(device)
    if anns:
        label = "{} ({})".format(label, ", ".join(anns))
    rows = [(device, [
        (2, Text(label)),
        Text(labels.desc(device)),
        Text(humanize_size(device.size), align="right"),
        ])]
    partitions = device.parts_and_gaps()
    if partitions:
        for part in partitions:
            if not part_filter(part):
                continue
            if isinstance(part, list):
                label = "free space"
                size = part[1] - part[0]
                details = ''
            else:
                label = labels.label(part, short=True)
                size = part.size
                details = ", ".join(
                    labels.annotations(part) + labels.usage_labels(part))
            rows.append((part, [
                Text(label),
                (2, Text(details)),
                Text(humanize_size(size), align="right"),
                ]))
    else:
        rows.append((None, [
            (4, Color.info_minor(Text(", ".join(labels.usage_labels(device)))))
            ]))
    return rows
