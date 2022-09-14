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

import typing


def api(cls, prefix_names=(), prefix_path=(), path_params=()):
    cls.fullpath = '/' + '/'.join(prefix_path)
    cls.fullname = prefix_names
    for k, v in cls.__dict__.items():
        if isinstance(v, type):
            v.__name__ = cls.__name__ + '.' + k
            path_part = k
            path_param = ()
            if getattr(v, '__parameter__', False):
                path_part = '{' + path_part + '}'
                path_param = (k,)
            api(
                v,
                prefix_names + (k,),
                prefix_path + (path_part,),
                path_params + path_param)
        if callable(v):
            v.__qualname__ = cls.__name__ + '.' + k
            v.__path_params__ = path_params
    return cls


T = typing.TypeVar("T")


class Payload(typing.Generic[T]):
    pass


def simple_endpoint(typ):
    class endpoint:
        def GET() -> typ: ...
        def POST(data: Payload[typ]): ...
    return endpoint
