# Copyright 2018 Canonical, Ltd.
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
""" Mirror View.
Select the Ubuntu archive mirror.

"""
import logging
from urwid import connect_signal, Text

from subiquitycore.view import BaseView
from subiquitycore.ui.buttons import other_btn
from subiquitycore.ui.form import (
    Form,
    URLEditor,
    simple_field,
)
from subiquitycore.ui.spinner import Spinner
from subiquitycore.ui.table import TablePile, TableRow


log = logging.getLogger('subiquity.ui.mirror')

mirror_help = _(
    "You may provide an archive mirror that will be used instead "
    "of the default.")


class MirrorURLEditor(URLEditor):

    def set_bound_form_field(self, bff):
        self.bff = bff
        bff.validating = False
        self.controller = bff.form.controller
        self.spinner = Spinner(self.controller.app.aio_loop)

    async def _check_url(self, url):
        self.spinner.start()
        r = await self.controller.app._wait_with_indication(
            self.controller.check_url(url), self._show_validating)
        self.spinner.stop()
        self.bff.validating = False
        self.bff._table.base_widget.focus_position = 0
        if r:
            self.bff.show_extra(Text([
                _("Mirror could not be used: "),
                ('info_error', r),
                ]))
        else:
            self.bff.under_text._w = Text(self.bff.help)
            self.bff.in_error = False
            self.bff.form.validated()
            self.bff.form.buttons.base_widget.focus_position = 0

    def _show_validating(self):
        self.bff.in_error = True
        self.bff.show_extra(
            TablePile([TableRow([
                Text(_("Checking mirror")),
                self.spinner,
                ])]))
        self.bff._table.base_widget.focus_position = 1
        self.bff.form.validated()

    def lost_focus(self):
        try:
            url = self.bff.value
        except ValueError:
            return
        self.bff.validating = True
        self.controller.app.aio_loop.create_task(self._check_url(url))


MirrorURLField = simple_field(MirrorURLEditor)


class MirrorForm(Form):

    inited = False

    def __init__(self, controller, initial):
        self.controller = controller
        super().__init__(initial=initial)
        self.inited = True

    cancel_label = _("Back")

    url = MirrorURLField(_("Mirror address:"), help=mirror_help)


class MirrorView(BaseView):

    title = _("Configure Ubuntu archive mirror")
    excerpt = _("If you use an alternative mirror for Ubuntu, enter its "
                "details here.")

    def __init__(self, controller, mirror):
        self.controller = controller

        self.form = MirrorForm(controller, initial={'url': mirror})

        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)

        self.form.screen = self.form.as_screen(excerpt=_(self.excerpt))

        super().__init__(self.form.screen)

    def done(self, result):
        log.debug("User input: {}".format(result.as_data()))
        self.controller.done(result.url.value)

    def cancel(self, result=None):
        self.controller.cancel()
