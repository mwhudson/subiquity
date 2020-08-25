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

from aiohttp import web

from subiquity.common.serialize import deserialize, serialize


def trim(text):
    if len(text) > 80:
        return text[:77] + '...'
    else:
        return text


def make_handler(controller, definition, implementation):
    def_sig = inspect.signature(definition)
    def_ret_ann = def_sig.return_annotation
    def_params = def_sig.parameters

    impl_sig = inspect.signature(implementation)
    impl_params = impl_sig.parameters

    data_annotation = None
    query_args_anns = []

    for param_name, param in def_params.items():
        if param_name in ('request', 'context'):
            raise Exception(
                "api method {} cannot have parameter called request or "
                "context".format(definition))
        if param_name not in impl_params:
            raise Exception("{}, implementing {} missing param {}".format(
                implementation, definition, param_name))
        if param_name == 'data':
            data_annotation = param.annotation
        else:
            query_args_anns.append(
                (param_name, param.annotation, param.default))

    impl_params = inspect.signature(implementation).parameters

    async def handler(request):
        context = controller.context.child(
            implementation.__name__, trim(await request.text()))
        with context:
            context.set('request', request)
            args = {}
            if data_annotation is not None:
                payload = await request.text()
                payload = json.loads(payload)
                args['data'] = deserialize(data_annotation, payload['data'])
            for arg, ann, default in query_args_anns:
                if arg in request.query:
                    v = deserialize(ann, json.loads(request.query[arg]))
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
                'result': serialize(def_ret_ann, result),
                }
            resp.update(controller.generic_result())
            resp = web.json_response(resp)
            context.description = trim(resp.text)
            return resp

    return handler


def bind(router, endpoint, controller, depth=None):
    if depth is None:
        depth = len(endpoint.fullname)

    if hasattr(endpoint, 'get'):
        meth_name = "_".join(endpoint.fullname[depth:] + ('get',))
        meth = getattr(controller, meth_name)
        router.add_route(
            method="GET",
            path=endpoint.fullpath,
            handler=make_handler(controller, endpoint.get, meth))

    if hasattr(endpoint, 'post'):
        meth_name = "_".join(endpoint.fullname[depth:] + ('post',))
        meth = getattr(controller, meth_name)
        router.add_route(
            method="POST",
            path=endpoint.fullpath,
            handler=make_handler(controller, endpoint.post, meth))

    for v in endpoint.__dict__.values():
        if isinstance(v, type):
            bind(router, v, controller, depth)
