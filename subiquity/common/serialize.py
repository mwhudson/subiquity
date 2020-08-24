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

import datetime
import enum
import inspect
import typing

import attr

# This is basically a half-assed version of
# https://pypi.org/project/cattrs/ but that's not packaged and it's
# enough for our needs.


def serialize(annotation, value, metadata={}):
    if annotation is inspect.Signature.empty:
        return value
    elif attr.has(annotation):
        return {
            field.name: serialize(
                field.type,
                getattr(value, field.name),
                field.metadata)
            for field in attr.fields(annotation)
            }
    elif typing.get_origin(annotation):
        t = typing.get_origin(annotation)
        if t is list:
            list_anns = typing.get_args(annotation)
            if list_anns:
                return [serialize(list_anns[0], v) for v in value]
            else:
                return value
        elif t is typing.Union:
            pass
        else:
            raise Exception("don't understand {}".format(t))
    elif annotation in (str, int, bool):
        return annotation(value)
    elif annotation is datetime.datetime:
        if 'time_fmt' in metadata:
            return value.strftime(metadata['time_fmt'])
        else:
            return str(value)
    elif isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        return value.name
    else:
        raise Exception(str(annotation))


def deserialize(annotation, value, metadata={}):
    if annotation is inspect.Signature.empty:
        return value
    elif attr.has(annotation):
        return annotation(**{
            field.name: deserialize(
                field.type,
                value[field.name],
                field.metadata)
            for field in attr.fields(annotation)
            if field.name in value
            })
    elif typing.get_origin(annotation):
        t = typing.get_origin(annotation)
        if t is list:
            list_ann = typing.get_args(annotation)[0]
            return [deserialize(list_ann, v) for v in value]
        elif t is typing.Union:
            return value
        else:
            raise Exception("don't understand {}".format(t))
    elif annotation in (str, int, bool):
        return annotation(value)
    elif annotation is datetime.datetime:
        if 'time_fmt' in metadata:
            return datetime.datetime.strptime(value, metadata['time_fmt'])
        else:
            1/0
    elif isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        return getattr(annotation, value)
    else:
        raise Exception(str(annotation))
