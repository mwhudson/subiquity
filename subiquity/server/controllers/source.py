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

from subiquitycore.lsb_release import lsb_release

from subiquity.server.controller import NonInteractiveController


class SourceController(NonInteractiveController):

    model_name = "source"


    def load_autoinstall_data(self, data):
        if data is None:
            return
        package = data.get('package')
        flavor = data.get('flavor')
        if package is None:
            if flavor is None or flavor == 'generic':
                package = 'linux-generic'
            else:
                if flavor is None:
                    package = 'generic'
                else:
                    if flavor == 'hwe':
                        flavor = 'generic-hwe'
                    # Should check this package exists really but
                    # that's a bit tricky until we get cleverer about
                    # the apt config in general.
                    package = 'linux-{flavor}-{release}'.format(
                        flavor=flavor, release=lsb_release()['release'])
        self.model.metapkg_name = package

    def make_autoinstall(self):
        return {
            'kernel': {
                'package': self.model.metapkg_name,
                },
            }
