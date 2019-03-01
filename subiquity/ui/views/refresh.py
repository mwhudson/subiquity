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

import logging

from urwid import Text

from subiquitycore.view import BaseView
from subiquitycore.ui.buttons import forward_btn, done_btn, cancel_btn
from subiquitycore.ui.utils import button_pile, screen

log = logging.getLogger('subiquity.refresh')


class RefreshView(BaseView):

    title = _("Installer update available")
    excerpt = _("A new version of the installer is available.")

    def __init__(self, controller):
        self.controller = controller

        rows = [Text("hi")]

        buttons = button_pile([
            forward_btn(_("Update"), on_press=self.update),
            done_btn(_("Continue without updating"), on_press=self.done),
            cancel_btn(_("Back"), on_press=self.cancel),
            ])
        buttons.base_widget.focus_position = 1

        super().__init__(screen(rows, buttons, excerpt=_(self.excerpt)))

    def update(self, sender=None):
        pass

    def done(self, result=None):
        self.controller.done()

    def cancel(self, result=None):
        self.controller.cancel()
