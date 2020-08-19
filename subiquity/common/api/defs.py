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


def api(cls, name_prefix=(), path_prefix=''):
    for k, v in cls.__dict__.items():
        if isinstance(v, type):
            v.__name__ = k
            v.fullname = name_prefix + (k,)
            n = getattr(v, 'path', k)
            v.fullpath = path_prefix + '/' + n
            api(v, v.fullname, v.fullpath)
    return cls


def simple_endpoint(typ):
    class endpoint:
        def get() -> typ: pass
        def post(data: typ): pass
    return endpoint
