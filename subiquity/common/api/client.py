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

from subiquity.common.serialize import serialize, deserialize


def _wrap_get(getter, path, meth):
    sig = inspect.signature(meth)
    r_ann = sig.return_annotation

    async def impl_get(**args):
        r = await getter(path.format(**args))
        return deserialize(r_ann, r['result'])

    return impl_get


def _wrap_post(poster, path, meth):
    sig = inspect.signature(meth)
    r_ann = sig.return_annotation
    arg_name = list(sig.parameters.keys())[0]
    arg_ann = sig.parameters[arg_name].annotation

    async def impl_post(data, **args):
        data = {'data': serialize(arg_ann, data)}
        r = await poster(path.format(**args), data)
        return deserialize(r_ann, r['result'])
    return impl_post


def make_client(endpoint_cls, getter, poster):
    class C:
        pass

    if hasattr(endpoint_cls, 'get'):
        C.get = staticmethod(_wrap_get(
            getter,
            endpoint_cls.fullpath,
            endpoint_cls.get))

    if hasattr(endpoint_cls, 'post'):
        C.post = staticmethod(_wrap_post(
            poster,
            endpoint_cls.fullpath,
            endpoint_cls.post))

    for k, v in endpoint_cls.__dict__.items():
        if isinstance(v, type):
            setattr(C, k, make_client(v, getter, poster))
    return C
