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


def api(cls, name_prefix=(), path_prefix=()):
    cls.fullpath = '/' + '/'.join(path_prefix)
    cls.fullname = name_prefix
    for k, v in cls.__dict__.items():
        if isinstance(v, type):
            v.__name__ = k
            n = getattr(v, 'path', k)
            api(v, name_prefix + (k,), path_prefix + (n,))
    return cls


def simple_endpoint(typ):
    class endpoint:
        def get() -> typ: pass
        def post(data: typ): pass
    return endpoint