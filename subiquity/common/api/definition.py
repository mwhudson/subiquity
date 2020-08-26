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
    ErrorReportRef,
    IdentityData,
    InstallState,
    KeyboardSetting,
    RefreshStatus,
    SSHData,
    SnapInfo,
    SnapListResponse,
    SnapSelection,
    StorageResponse,
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
            def GET() -> ApplicationState: ...

            class wait_early:
                def GET() -> ApplicationState: ...

        class confirm:
            def POST(): ...

    class dry_run:
        class make_error:
            def POST() -> ErrorReportRef: ...

    class errors:
        class wait:
            def GET(error_ref: ErrorReportRef) -> ErrorReportRef: ...

    class refresh:
        def GET(wait: bool = False) -> RefreshStatus: ...
        def POST() -> str: ...

        class progress:
            def GET(change_id: str) -> dict: ...

    class network:
        def GET() -> dict: ...
        def POST(data: dict): ...

        class nic:
            class ifindex:
                def GET(ifindex: int) -> dict: ...

        class new:
            def GET() -> dict: ...

    class storage:
        def GET(wait: bool = False) -> StorageResponse: ...
        def POST(config: Payload[list]): ...

        class reset:
            def POST() -> StorageResponse: ...

    class snaplist:
        def GET(wait: bool = False) -> SnapListResponse: ...
        def POST(data: Payload[List[SnapSelection]]): ...

        class snap_info:
            def GET(snap_name: str) -> SnapInfo: ...

    class install:
        class status:
            def GET(cur: Optional[InstallState] = None) -> InstallState: ...

    class reboot:
        def POST(data): ...
