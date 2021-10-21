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
import asyncio
import logging
from urwid import connect_signal, Text

from subiquitycore.ui.container import Columns
from subiquitycore.ui.form import (
    Form,
    URLField,
)
from subiquitycore.ui.spinner import Spinner
from subiquitycore.ui.utils import screen
from subiquitycore.view import BaseView

from subiquity.common.types import MirrorCheckStatus

log = logging.getLogger('subiquity.ui.mirror')

mirror_help = _(
    "You may provide an archive mirror that will be used instead "
    "of the default.")


class MirrorForm(Form):

    cancel_label = _("Back")

    url = URLField(_("Mirror address:"), help=mirror_help)


class MirrorView(BaseView):

    title = _("Configure Ubuntu archive mirror")
    excerpt = _("If you use an alternative mirror for Ubuntu, enter its "
                "details here.")

    def __init__(self, controller, mirror, check_state):
        self.controller = controller

        self.form = MirrorForm(initial={'url': mirror})

        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)

        self.status_text = Text("")
        self.status_spinner = Spinner(self.controller.app.aio_loop)
        self.output_text = Text("")

        self.update_status(check_state)

        rows = self.form.as_rows() + [
            Text(""),
            Columns([self.status_text, self.status_spinner]),
            Text(""),
            self.output_text,
            ]

        super().__init__(screen(
            rows,
            buttons=self.form.buttons,
            excerpt=_(self.excerpt)))

    def update_status(self, check_state):
        self.status_text.set_text(str(check_state.status))
        self.output_text.set_text(check_state.output)

        async def cb():
            await asyncio.sleep(1)
            status = await self.controller.endpoint.check.GET()
            self.update_status(status)

        if check_state.status in [
                MirrorCheckStatus.NOT_STARTED, MirrorCheckStatus.RUNNING]:
            self.controller.app.aio_loop.create_task(cb())
        if check_state.status == MirrorCheckStatus.RUNNING:
            self.status_spinner.start()
        else:
            self.status_spinner.stop()

    def done(self, result):
        log.debug("User input: {}".format(result.as_data()))
        self.controller.done(result.url.value)

    def cancel(self, result=None):
        self.controller.cancel()
