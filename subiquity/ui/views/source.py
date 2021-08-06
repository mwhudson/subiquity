# Copyright 2021 Canonical, Ltd.
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

import logging
from urwid import connect_signal

from subiquitycore.view import BaseView
from subiquitycore.ui.form import (
    Form,
    RadioButtonField,
)

from subiquity.models.filesystem import align_up, humanize_size

log = logging.getLogger('subiquity.ui.views.source')


class SourceView(BaseView):

    title = _("Choose type of install")

    def __init__(self, controller, sources, current_id):
        self.controller = controller

        group = []

        ns = {
            'cancel_label': _("Back"),
            }
        initial = {}

        for default in True, False:
            for source in sorted(sources, key=lambda s: s.id):
                if source.default != default:
                    continue
                i = 2
                while (2 << i) < source.size:
                    i += 1
                size = humanize_size(align_up(source.size, 2 << (i-3)))
                base = size[:-1].rstrip('0')
                if base.endswith('.'):
                    base = base[:-1]
                size = base + ' ' + size[-1] + 'iB'
                help = "\n" + source.description + "\n\n" + _(
                    "This variant will occopy approximately "
                    "{size} of disk when installed.").format(size=size)
                ns[source.id] = RadioButtonField(group, source.name, help)
                initial[source.id] = source.id == current_id

        SourceForm = type(Form)('SourceForm', (Form,), ns)
        log.debug('%r %r', ns, current_id)

        self.form = SourceForm(initial=initial)

        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)

        excerpt = _("Choose the base for the installation.")

        super().__init__(self.form.as_screen(excerpt=excerpt))

    def done(self, result):
        log.debug("User input: {}".format(result.as_data()))
        for k, v in result.as_data().items():
            if v:
                self.controller.done(k)

    def cancel(self, result=None):
        self.controller.cancel()
