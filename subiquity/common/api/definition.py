# Copyright 2020 Canonical, Ltd.
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

from typing import List

from .defs import api, simple_endpoint
from subiquity.common.types import (
    ApplicationState,
    IdentityData,
    InstallState,
    KeyboardSetting,
    RefreshStatus,
    SSHData,
    SnapInfo,
    SnapListResponse,
    SnapSelection,
    )


@api
class API:
    # Simple endpoints, that just take and give a single data type:

    locale = simple_endpoint(str)
    keyboard = simple_endpoint(KeyboardSetting)
    proxy = simple_endpoint(str)
    mirror = simple_endpoint(str)
    identity = simple_endpoint(IdentityData)
    ssh = simple_endpoint(SSHData)

    # More complex cases:

    class meta:

        class status:
            def get() -> ApplicationState: pass

            class wait_early:
                def get() -> ApplicationState: pass

        class confirm:
            def post(data: None): pass

    class refresh:
        def get() -> RefreshStatus: pass
        def post(data) -> str: pass

        class progress:
            class id:
                path = '{id}'
                def get(self): pass

        class wait:
            def get(self) -> RefreshStatus: pass

    class network:
        def get(self) -> dict: pass
        def post(self, data: dict): pass

        class nic:
            class ifindex:
                path = '{ifindex}'
                def get(self) -> dict: pass

        class new:
            def get(self) -> dict: pass

    class storage:
        def get(self): pass
        def post(self): pass

        class wait:
            def get(self): pass

    class snaplist:
        def get() -> SnapListResponse: pass
        def post(data: List[SnapSelection]): pass

        class info:
            class snap_name:
                path = '{snap}'
                def get() -> SnapInfo: pass

        class wait:
            def get() -> SnapListResponse: pass

    class install:
        class status:
            def get() -> InstallState: pass

    class reboot:
        def post(self, data): pass
