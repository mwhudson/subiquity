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

import contextlib
import inspect

import aiohttp

from subiquity.common.serialize import Serializer
from .defs import Payload


def _wrap(make_request, path, meth, serializer, path_args):
    sig = inspect.signature(meth)
    meth_params = sig.parameters
    payload_arg = None
    for name, param in meth_params.items():
        if getattr(param.annotation, '__origin__', None) is Payload:
            payload_arg = name
            payload_ann = param.annotation.__args__[0]
    r_ann = sig.return_annotation

    async def impl(*args, **kw):
        args = sig.bind(*args, **kw)
        query_args = {}
        data = None
        for arg_name, value in args.arguments.items():
            if arg_name == payload_arg:
                data = serializer.serialize(payload_ann, value)
            else:
                query_args[arg_name] = serializer.to_json(
                        meth_params[arg_name].annotation, value)
        async with make_request(
                meth.__name__, path.format(**path_args),
                json=data, params=query_args) as resp:
            resp.raise_for_status()
            return serializer.deserialize(r_ann, await resp.json())
    return impl


def make_getitem(make_request, serializer, path_args, v):
    def gi(self, item):
        new_args = path_args.copy()
        new_args[v.__shortname__] = item
        return make_client(v, make_request, serializer, new_args)
    return gi


def make_client(endpoint_cls, make_request, serializer=None, path_args=None):
    if serializer is None:
        serializer = Serializer()

    if path_args is None:
        path_args = {}

    inst_vars = {}
    ns = {}

    for k, v in endpoint_cls.__dict__.items():
        if isinstance(v, type):
            if getattr(v, '__parameter__', False):
                ns['__getitem__'] = make_getitem(
                    make_request, serializer, path_args, v)
            else:
                inst_vars[k] = make_client(
                    v, make_request, serializer, path_args)
        elif callable(v):
            inst_vars[k] = staticmethod(
                _wrap(
                    make_request,
                    endpoint_cls.fullpath,
                    v,
                    serializer,
                    path_args))

    cls = type('C', (object,), ns)
    inst = cls()
    inst.__dict__.update(inst_vars)
    return inst


def make_client_for_conn(
        endpoint_cls, conn, resp_hook=lambda r: r, serializer=None,
        header_func=None):
    session = aiohttp.ClientSession(
        connector=conn, connector_owner=False)

    @contextlib.asynccontextmanager
    async def make_request(method, path, *, params, json):
        # session.request needs a full URL with scheme and host even though
        # that's in some ways a bit silly with a unix socket, so we just
        # hardcode something here (I guess the "a" gets sent along to the
        # server in the Host: header and the server could in principle do
        # something like virtual host based selection but well....)
        url = 'http://a' + path
        if header_func is not None:
            headers = header_func()
        else:
            headers = None
        async with session.request(
                method, url, json=json, params=params,
                headers=headers, timeout=0) as response:
            yield resp_hook(response)

    return make_client(endpoint_cls, make_request, serializer)
