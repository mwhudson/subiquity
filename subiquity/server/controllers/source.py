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

from subiquity.common.apidef import API
from subiquity.common.types import (
    SourceSelection,
    SourceSelectionAndSetting,
    )
from subiquity.server.controller import SubiquityController


class SourceController(SubiquityController):

    model_name = "source"

    endpoint = API.source

    def start(self):
        path = '/cdrom/casper/install-source.yaml'
        if self.app.opts.source_catalog is not None:
            path = self.app.opts.source_catalog
        if not os.path.exists(path):
            return
        with open(path) as fp:
            self.model.load_from_file(fp)

    def interactive(self):
        if len(self.model.sources) <= 1:
            return False
        return super().interactive()

    async def GET(self) -> SourceSelectionAndSetting:
        r = []
        for source in self.model.sources:
            name = source.name['en']
            cur_lang = self.app.base_model.locale.selected_language
            if cur_lang:
                cur_lang = cur_lang.rsplit('.', 1)[0]
                for lang in cur_lang, cur_lang.split('_', 1)[0]:
                    if lang in source.name:
                        name = source.name[lang]
                        break
            r.append(SourceSelection(
                name=name,
                id=source.id,
                size=source.size,
                flavor=source.flavor,
                default=source.default))
        return SourceSelectionAndSetting(r, self.model.current.id)

    async def POST(self, source_id: str) -> None:
        for source in self.model.sources:
            if source.id == source_id:
                self.model.current = source
        self.configured()
