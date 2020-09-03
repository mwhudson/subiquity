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

import enum
from typing import List, Optional

from subiquitycore.models.network import (
    BondConfig,
    NetDevInfo,
    StaticConfig,
    )

from .defs import api, simple_endpoint, Payload
from subiquity.common.types import (
    ApplicationState,
    ApplicationStatus,
    ErrorReportRef,
    IdentityData,
    InstallState,
    InstallStatus,
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
            def GET(cur: Optional[ApplicationStatus] = None) \
                -> ApplicationState: ...

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
        def GET() -> List[NetDevInfo]: ...
        def POST() -> None: ...

        class subscription:
            def PUT(socket_path: str) -> None: ...
            def DELETE(socket_path: str) -> None: ...

        class set_static_config:
            def POST(dev_name: str, ip_version: int,
                     static_config: Payload[StaticConfig]) -> None: ...

        class enable_dhcp:
            def POST(dev_name: str, ip_version: int) -> None: ...

        class disable:
            def POST(dev_name: str, ip_version: int) -> None: ...

        class vlan:
            def PUT(dev_name: str, vlan_id: int) -> None: ...

        class add_or_edit_bond:
            def POST(existing_name: Optional[str], new_name: str,
                     bond_config: BondConfig) -> None: ...

        class delete:
            def POST(dev_name: str) -> None: ...

        class info:
            def GET(dev_name: str) -> str: ...

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
            def GET(cur: Optional[InstallState] = None) -> InstallStatus: ...

    class reboot:
        def POST(): ...


class LinkAction(enum.Enum):
    NEW = enum.auto()
    CHANGE = enum.auto()
    DEL = enum.auto()


@api
class NetEventAPI:
    class update_link:
        def POST(act: LinkAction, info: Payload[NetDevInfo]) -> None: ...

    class route_watch:
        def POST(routes: List[int]) -> None: ...

    class apply_starting:
        def POST() -> None: ...

    class apply_stopping:
        def POST() -> None: ...

    class apply_error:
        def POST(stage: str) -> None: ...
