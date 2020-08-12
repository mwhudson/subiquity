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

from subiquity.common.api import asdict

log = logging.getLogger("subiquity.controller")


def identity(x):
    return x


def instantiator(cls):
    return lambda x: cls(**x)


def make_client(app, endpoint_cls, prefix=None):
    if prefix is None:
        prefix = []

    class C:
        pass

    n = getattr(endpoint_cls, 'path', endpoint_cls.__name__)
    path = '/' + '/'.join(prefix + [n])

    if hasattr(endpoint_cls, 'get'):
        sig = inspect.signature(endpoint_cls.get)
        r_ann = sig.return_annotation
        if r_ann is inspect.Signature.empty:
            conv_r = identity
        elif attr.has(r_ann):
            conv_r = instantiator(r_ann)
        else:
            1/0

        async def impl_get():
            return conv_r(await app.get(path))
        C.get = staticmethod(impl_get)
    if hasattr(endpoint_cls, 'post'):
        sig = inspect.signature(endpoint_cls.post)
        r_ann = sig.return_annotation
        if r_ann is inspect.Signature.empty:
            conv_r_p = identity
        elif attr.has(r_ann):
            conv_r_p = instantiator(r_ann)
        else:
            1/0
        arg_name = list(sig.parameters.keys())[0]
        arg_ann = sig.parameters[arg_name].annotation
        if arg_ann is inspect.Signature.empty:
            conv_arg = identity
        elif attr.has(arg_ann):
            conv_arg = asdict
        else:
            1/0

        async def impl_post(data):
            return conv_r_p(await app.post(path, conv_arg(data)))
        C.post = staticmethod(impl_post)
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
