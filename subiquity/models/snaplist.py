# Copyright 2015 Canonical, Ltd.
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
import logging

import attr


log = logging.getLogger("subiquity.models.snaplist")


TIME_FMT = '%Y-%m-%dT%H:%M:%S.%fZ'


@attr.s(cmp=False)
class SnapInfo:
    name = attr.ib()
    summary = attr.ib(default='')
    publisher = attr.ib(default='')
    verified = attr.ib(default=False)
    description = attr.ib(default='')
    confinement = attr.ib(default='')
    license = attr.ib(default='')
    channels = attr.ib(default=attr.Factory(list))
    partial = attr.ib(default=True)

    def update(self, data):
        self.summary = data['summary']
        self.publisher = data['developer']
        self.verified = data['publisher']['validation'] == "verified"
        self.description = data['description']
        self.confinement = data['confinement']
        self.license = data['license']
        self.partial = False

    def serialize(self):
        r = attr.asdict(self)
        for d in r['channels']:
            d['released_at'] = d['released_at'].strftime(TIME_FMT)
        return r

    @classmethod
    def deserialize(cls, data):
        inst = cls(**data)
        inst.channels = [
            ChannelSnapInfo.deserialize(chan) for chan in inst.channels
            ]
        return inst


class SnapInfoList(list):

    def serialize(self):
        return [snap.serialize() for snap in self]

    @classmethod
    def deserialize(cls, data):
        return cls([SnapInfo.deserialize(datum) for datum in data])


@attr.s(cmp=False)
class ChannelSnapInfo:
    channel_name = attr.ib()
    revision = attr.ib()
    confinement = attr.ib()
    version = attr.ib()
    size = attr.ib()
    released_at = attr.ib()

    @classmethod
    def deserialize(cls, data):
        data = data.copy()
        data['released-at'] = datetime.datetime.strptime(
            data['released-at'], TIME_FMT)
        return cls(**data)


@attr.s(cmp=False)
class SnapSelection:
    name = attr.ib()
    channel = attr.ib()
    is_classic = attr.ib()

    def serialize(self):
        return attr.asdict(self)

    @classmethod
    def deserialize(cls, data):
        inst = cls(**data)
        inst.channels = [
            ChannelSnapInfo.deserialize(chan) for chan in inst.channels
            ]
        return inst


class SnapSelectionDict(dict):

    def serialize(self):
        return {k: v.serialize() for k, v in self.items()}

    @classmethod
    def deserialize(cls, data):
        return cls({k: SnapSelection.deserialize(v) for k, v in data.items()})


risks = ["stable", "candidate", "beta", "edge"]


class SnapListModel:

    def __init__(self):
        self._snap_info = SnapInfoList()
        self._snaps_by_name = {}
        self.to_install = SnapSelectionDict()  # snap_name -> SnapSelection

    def _snap_for_name(self, name):
        s = self._snaps_by_name.get(name)
        if s is None:
            s = self._snaps_by_name[name] = SnapInfo(name=name)
            self._snap_info.append(s)
        return s

    def load_find_data(self, data):
        for info in data['result']:
            self._snap_for_name(info['name']).update(info)

    def add_partial_snap(self, name):
        self._snaps_for_name(name)

    def load_info_data(self, data):
        info = data['result'][0]
        snap = self._snaps_by_name.get(info['name'])
        if snap is None:
            return
        if snap.partial:
            snap.update(info)
        channel_map = info['channels']
        for track in info['tracks']:
            for risk in risks:
                channel_name = '{}/{}'.format(track, risk)
                if channel_name in channel_map:
                    channel_data = channel_map[channel_name]
                    if track == "latest":
                        channel_name = risk
                    snap.channels.append(ChannelSnapInfo(
                        channel_name=channel_name,
                        revision=channel_data['revision'],
                        confinement=channel_data['confinement'],
                        version=channel_data['version'],
                        size=channel_data['size'],
                        released_at=datetime.datetime.strptime(
                            channel_data['released-at'], TIME_FMT),
                    ))
        return snap

    def get_snap_list(self):
        return self._snap_info

    def set_installed_list(self, to_install):
        for name in to_install.keys():
            self._snap_for_name(name)
        self.to_install = to_install
