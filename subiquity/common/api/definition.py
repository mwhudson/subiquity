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

from typing import List, Optional

from .defs import api, simple_endpoint, Payload
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
            def GET() -> ApplicationState: pass

            class wait_early:
                def GET() -> ApplicationState: pass

        class confirm:
            def POST(): pass

    class refresh:
        def GET() -> RefreshStatus: pass
        def POST() -> str: pass

        class progress:
            def GET(change_id: str): pass

        class wait:
            def GET() -> RefreshStatus: pass

    class network:
        def GET() -> dict: pass
        def POST(data: dict): pass

        class nic:
            class ifindex:
                def GET(ifindex: int) -> dict: pass

        class new:
            def GET() -> dict: pass

    class storage:
        def GET(): pass
        def POST(config: Payload[dict]): pass

        class wait:
            def GET(): pass

    class snaplist:
        def GET() -> SnapListResponse: pass
        def POST(data: Payload[List[SnapSelection]]): pass

        class snap_info:
            def GET(snap_name: str) -> SnapInfo: pass

        class wait:
            def GET() -> SnapListResponse: pass

    class install:
        class status:
            def GET(cur: Optional[InstallState] = None) -> InstallState: pass

    class reboot:
        def POST(data): pass
