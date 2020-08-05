# Copyright 2018 Canonical, Ltd.
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

from subiquity.server.controller import SubiquityController

log = logging.getLogger('subiquity.controllers.ssh')


class SSHController(SubiquityController):

    endpoint = '/ssh'

    autoinstall_key = model_name = "ssh"
    autoinstall_schema = {
        'type': 'object',
        'properties': {
            'install-server': {'type': 'boolean'},
            'authorized-keys': {
                'type': 'array',
                'items': {'type': 'string'},
                },
            'allow-pw': {'type': 'boolean'},
        },
    }

    def __init__(self, app):
        super().__init__(app)

    def load_autoinstall_data(self, data):
        if data is None:
            return
        self.model.install_server = data.get('install-server', False)
        self.model.authorized_keys = data.get('authorized-keys', [])
        self.model.pwauth = data.get(
            'allow-pw', not self.model.authorized_keys)

    def make_autoinstall(self):
        return {
            'install-server': self.model.install_server,
            'authorized-keys': self.model.authorized_keys,
            'allow-pw': self.model.pwauth,
            }

    async def _get(self):
        return {
            'install-server': self.model.install_server,
            'allow-pw': self.model.pwauth,
            }

    async def _post(self, data):
        self.model.install_server = data['install-server']
        self.model.authorized_keys = data['authorized-keys']
        self.model.pwauth = data['allow-pw']

