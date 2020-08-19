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


def make_get_handler(controller, definition, implementation):
    r_ann = inspect.signature(definition).return_annotation

    impl_params = inspect.signature(implementation).parameters

    async def handler(request):
        context = controller.context.child(
            implementation.__name__, trim(await request.text()))
        with context:
            context.set('request', request)
            args = {}
            if 'context' in impl_params:
                args['context'] = context
            if 'request' in impl_params:
                args['request'] = request
            result = await implementation(**args)
            resp = {
                'result': serialize(r_ann, result),
                }
            resp.update(controller.generic_result())
            resp = web.json_response(resp)
            context.description = trim(resp.text)
            return resp

    return handler


def make_post_handler(controller, definition, implementation):
    sig = inspect.signature(definition)
    r_ann = sig.return_annotation
    arg_name = list(sig.parameters.keys())[0]
    arg_ann = sig.parameters[arg_name].annotation

    impl_params = inspect.signature(implementation).parameters

    async def handler(request):
        context = controller.context.child(
            implementation.__name__, trim(await request.text()))
        with context:
            context.set('request', request)
            args = {}
            payload = await request.text()
            payload = json.loads(payload)
            args[arg_name] = deserialize(arg_ann, payload['data'])
            if 'context' in impl_params:
                args['context'] = context
            if 'request' in impl_params:
                args['request'] = request
            result = await implementation(**args)
            resp = {
                'result': serialize(r_ann, result),
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
            handler=make_get_handler(controller, endpoint.get, meth))

    if hasattr(endpoint, 'post'):
        meth_name = "_".join(endpoint.fullname[depth:] + ('post',))
        meth = getattr(controller, meth_name)
        router.add_route(
            method="POST",
            path=endpoint.fullpath,
            handler=make_post_handler(controller, endpoint.post, meth))

    for v in endpoint.__dict__.values():
        if isinstance(v, type):
            bind(router, v, controller, depth)
