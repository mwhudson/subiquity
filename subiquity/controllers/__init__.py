# Copyright 2015 Canonical, Ltd.
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

from .filesystem import FilesystemController
from .identity import IdentityController
from .installpath import InstallpathController
from .installprogress import InstallProgressController
from .keyboard import KeyboardController
from .proxy import ProxyController
from .mirror import MirrorController
from .refresh import RefreshController

class Refresh2Controller:
    def __init__(self, common):
        self.controller = common['controllers']['Refresh']
    def default(self):
        self.controller.default(2)
    def register_signals(self):
        pass

from subiquitycore.controllers.login import LoginController
from subiquitycore.controllers.network import NetworkController
from .snaplist import SnapListController
from .ssh import SSHController
from .welcome import WelcomeController
__all__ = [
    'FilesystemController',
    'IdentityController',
    'InstallpathController',
    'InstallProgressController',
    'KeyboardController',
    'ProxyController',
    'MirrorController',
    'LoginController',
    'NetworkController',
    'RefreshController',
    'Refresh2Controller',
    'SnapListController',
    'SSHController',
    'WelcomeController',
]
