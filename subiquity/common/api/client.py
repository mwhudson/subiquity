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

import inspect
import json
import typing

from subiquity.common.serialize import serialize, deserialize
from .defs import Payload


def _wrap(make_request, path, meth):
    sig = inspect.signature(meth)
    meth_params = sig.parameters
    payload_arg = None
    for name, param in meth_params.items():
        if typing.get_origin(param.annotation) is Payload:
            payload_arg = name
            payload_ann = typing.get_args(param.annotation)[0]
    r_ann = sig.return_annotation

    async def impl(*args, **kw):
        args = sig.bind(*args, **kw)
        params = {
            k: json.dumps(serialize(meth_params[k].annotation, v))
            for (k, v) in args.arguments.items() if k != payload_arg
            }
        if payload_arg in args.arguments:
            v = args.arguments[payload_arg]
            data = {'data': serialize(payload_ann, v)}
        else:
            data = None
        r = await make_request(meth.__name__, path, json=data, params=params)
        return deserialize(r_ann, r['result'])
    return impl


def make_client(endpoint_cls, make_request):
    class C:
        pass

    for k, v in endpoint_cls.__dict__.items():
        if isinstance(v, type):
            setattr(C, k, make_client(v, make_request))
        elif callable(v):
            setattr(C, k, _wrap(make_request, endpoint_cls.fullpath, v))
    return C
