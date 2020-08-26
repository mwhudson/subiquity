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

from aiohttp import web

from subiquity.common.serialize import Serializer

from .defs import Payload


def trim(text):
    if len(text) > 80:
        return text[:77] + '...'
    else:
        return text


def _make_handler(controller, definition, implementation, serializer):
    def_sig = inspect.signature(definition)
    def_ret_ann = def_sig.return_annotation
    def_params = def_sig.parameters

    impl_sig = inspect.signature(implementation)
    impl_params = impl_sig.parameters

    data_annotation = None
    data_arg = None
    query_args_anns = []

    check_def_params = []

    for param_name, param in def_params.items():
        if param_name in ('request', 'context'):
            raise Exception(
                "api method {} cannot have parameter called request or "
                "context".format(definition))
        if typing.get_origin(param.annotation) is Payload:
            data_arg = param_name
            data_annotation = typing.get_args(param.annotation)[0]
            check_def_params.append(param.replace(annotation=data_annotation))
        else:
            query_args_anns.append(
                (param_name, param.annotation, param.default))
            check_def_params.append(param)

    check_impl_params = [
        p for p in impl_params.values()
        if p.name not in ('context', 'request')
        ]
    check_impl_sig = impl_sig.replace(parameters=check_impl_params)

    check_def_sig = def_sig.replace(parameters=check_def_params)

    assert check_impl_sig == check_def_sig, \
        "implementation of {} has wrong signature, should be {}, is {}".format(
          definition.__qualname__, check_def_sig, check_impl_sig)

    async def handler(request):
        context = controller.context.child(
            implementation.__name__, trim(await request.text()))
        with context:
            context.set('request', request)
            args = {}
            if data_annotation is not None:
                payload = json.loads(await request.text())
                args[data_arg] = serializer.deserialize(
                    data_annotation, payload['data'])
            for arg, ann, default in query_args_anns:
                if arg in request.query:
                    v = serializer.deserialize(
                        ann, json.loads(request.query[arg]))
                elif default != inspect._empty:
                    v = default
                else:
                    1/0
                args[arg] = v
            if 'context' in impl_params:
                args['context'] = context
            if 'request' in impl_params:
                args['request'] = request
            result = await implementation(**args)
            resp = {
                'result': serializer.serialize(def_ret_ann, result),
                }
            resp.update(controller.generic_result())
            resp = web.json_response(resp)
            context.description = trim(resp.text)
            return resp

    return handler


def bind(router, endpoint, controller, serializer=None, _depth=None):
    if serializer is None:
        serializer = Serializer()
    if _depth is None:
        _depth = len(endpoint.fullname)

    for v in endpoint.__dict__.values():
        if isinstance(v, type):
            bind(router, v, controller, serializer, _depth)
        elif callable(v):
            method = v.__name__
            impl_name = "_".join(endpoint.fullname[_depth:] + (method,))
            impl = getattr(controller, impl_name)
            router.add_route(
                method=method,
                path=endpoint.fullpath,
                handler=_make_handler(controller, v, impl, serializer))
