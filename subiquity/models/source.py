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

import os
import typing
import yaml

import attr


@attr.s(auto_attribs=True)
class CatalogEntry:
    flavor: str
    id: str
    name: typing.Dict[str, str]
    path: str
    size: int
    type: str
    default: bool = False


class SourceModel:

    def __init__(self):
        self._dir = '/cdrom/casper'
        self.current = CatalogEntry(
            flavor='server',
            id='synthesized',
            name={'en': 'Ubuntu Server'},
            path='/media/filesystem',
            type='cp',
            default=True,
            size=2 << 30)
        self.sources = [self.current]

    def load_from_file(self, fp):
        self.dir = os.path.dirname(fp.name)
        self.sources = []
        self.current = None
        entries = yaml.safe_load(fp)
        for entry in entries:
            c = CatalogEntry(**entry)
            self.sources.append(c)
            if c.default:
                self.current = c
        if self.current is None:
            self.current = self.sources[0]

    def render(self):
        path = os.path.join(self._dir, self.current.path)
        scheme = self.current.type
        return {
            'sources': {
                'ubuntu00': f'{scheme}://{path}',
                },
            }
