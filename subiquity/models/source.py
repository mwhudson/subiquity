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
import os
import typing
import yaml

import attr

from subiquity.common.serialize import Serializer

log = logging.getLogger('subiquity.models.source')


@attr.s(auto_attribs=True)
class CatalogEntryVariation:
    path: str
    size: int
    snapd_system_label: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class CatalogEntry:
    variant: str
    id: str
    name: typing.Dict[str, str]
    description: typing.Dict[str, str]
    path: str
    size: int
    type: str
    default: bool = False
    locale_support: str = attr.ib(default="locale-only")
    preinstalled_langs: typing.List[str] = attr.Factory(list)
    snapd_system_label: typing.Optional[str] = None
    variations: typing.Dict[str: CatalogEntryVariation] = attr.Factory(dict)


legacy_server_entry = CatalogEntry(
    variant='server',
    id='synthesized',
    name={'en': 'Ubuntu Server'},
    description={'en': 'the default'},
    path='/media/filesystem',
    type='cp',
    default=True,
    size=2 << 30,
    locale_support="locale-only")


class SourceModel:

    def __init__(self):
        self._dir = '/cdrom/casper'
        self.current = legacy_server_entry
        self.sources = [self.current]
        self.lang = None
        self.search_drivers = False

    def load_from_file(self, fp):
        self._dir = os.path.dirname(fp.name)
        self.sources = []
        self.current = None
        self.sources = Serializer().deserialize(
            typing.List[CatalogEntry],
            yaml.safe_load(fp))
        for entry in self.sources:
            if not entry.variations:
                entry.variations['default'] = CatalogEntryVariation(
                    path=entry.path,
                    size=entry.size,
                    snapd_system_label=entry.snapd_system_label)
            if entry.default:
                self.current = entry
        log.debug("loaded %d sources from %r", len(self.sources), fp.name)
        if self.current is None:
            self.current = self.sources[0]

    def get_matching_source(self, id_: str) -> CatalogEntry:
        """ Return a source object that has the ID requested. """
        for source in self.sources:
            if source.id == id_:
                return source
        raise KeyError

    def get_source(self):
        path = os.path.join(self._dir, self.current.path)
        if self.current.preinstalled_langs:
            base, ext = os.path.splitext(path)
            if self.lang in self.current.preinstalled_langs:
                suffix = self.lang
            else:
                suffix = 'no-languages'
            path = base + '.' + suffix + ext
        scheme = self.current.type
        return f'{scheme}://{path}'

    def render(self):
        return {}
