# Copyright 2019 Canonical, Ltd.
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

import attr
import inspect
import logging

from subiquitycore.context import with_context
from subiquitycore.tuicontroller import (
    RepeatedController,
    Skip,
    TuiController,
    )

from subiquity.common.api import deserializer, serializer

log = logging.getLogger("subiquity.controller")


def make_client(app, endpoint_cls, path_prefix=''):
    class C:
        pass

    n = getattr(endpoint_cls, 'path', endpoint_cls.__name__)
    path = path_prefix + '/' + n

    if hasattr(endpoint_cls, 'get'):
        sig = inspect.signature(endpoint_cls.get)
        conv_r = deserializer(sig.return_annotation)

        async def impl_get(**args):
            r = await app.get(path.format(**args))
            if not r['interactive']:
                raise Skip
            return conv_r(r['result'])
        C.get = staticmethod(impl_get)

    if hasattr(endpoint_cls, 'post'):
        sig = inspect.signature(endpoint_cls.post)
        conv_r_p = deserializer(sig.return_annotation)
        arg_name = list(sig.parameters.keys())[0]
        conv_arg = serializer(sig.parameters[arg_name].annotation)

        async def impl_post(data, **args):
            r = await app.post(path.format(**args), conv_arg(data))
            if not r['interactive']:
                raise Skip
            return conv_r_p(r['result'])
        C.post = staticmethod(impl_post)

    for k, v in endpoint_cls.__dict__.items():
        if isinstance(v, type):
            setattr(C, k, make_client(app, v, path))
    return C


class SubiquityTuiController(TuiController):

    endpoint_cls = None

    def __init__(self, app):
        super().__init__(app)
        self.answers = app.answers.get(self.name, {})
        if self.endpoint_cls is not None:
            self.endpoint = make_client(app, self.endpoint_cls)

    async def post(self, data):
        response = await self.app.post(self.endpoint, data)
        if response['confirmation-needed']:
            self.app.show_confirm_install()

    @with_context()
    async def start_ui(self, context, **kw):
        status = await self.app.get(self.endpoint)
        if not status['interactive']:
            raise Skip
        await self._start_ui(status, **kw)


class RepeatedController(RepeatedController):

    @with_context()
    async def start_ui(self, context):
        return await self.orig.start_ui(context=context, index=2)


def run_in_task(meth):
    def w(self, *args, **kw):
        self.aio_loop.create_task(meth(self, *args, **kw))
    return w
