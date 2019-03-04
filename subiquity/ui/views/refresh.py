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

from urwid import (
    ProgressBar,
    Text,
    )

from subiquitycore.view import BaseView
from subiquitycore.ui.buttons import forward_btn, done_btn, cancel_btn
from subiquitycore.ui.utils import button_pile, screen

from subiquity.controllers.refresh import CHECK_STATE
from subiquity.ui.spinner import Spinner

log = logging.getLogger('subiquity.refresh')


class SnapdProgressBar(ProgressBar):
    def __init__(self):
        self.label = ""
        self.done = ""
        self.total = ""
        super().__init__(
            normal='progress_incomplete',
            complete='progress_complete')

    def get_text(self):
        return "{} {} / {}" % (self.label, self.done, self.total)


class RefreshView(BaseView):

    title = _(
        "Installer update available"
        )
    offer_excerpt = _(
        "A new version of the installer is available."
        )
    progress_excerpt = _(
        "Please wait while the updated installer is being downloaded. The "
        "installer will restart automatically when the download is complete."
        )
    still_checking_excerpt = _(
        "Contacting the snap store to check if a new version of the "
        "installer is available."
        )
    check_failed_excerpt = _(
        "Contacting the snap store failed:"
        )

    def __init__(self, controller, still_checking=False):
        self.controller = controller
        self.spinner = None

        if self.controller.update_state == CHECK_STATE.CHECKING:
            self.still_checking()
        else:
            self.offer_update()

        super().__init__(self._w)

    def update_check_status(self):
        if self.controller.update_state == CHECK_STATE.UNAVAILABLE:
            self.done()
        elif self.controller.update_state == CHECK_STATE.FAILED:
            self.check_failed()
        elif self.controller.update_state == CHECK_STATE.AVAILABLE:
            self.offer_update()
        else:
            pass

    def still_checking(self):
        self.spinner = Spinner(self.controller.loop, style="texts")
        self.spinner.start()
        rows = [self.spinner]

        buttons = [
            done_btn(_("Continue without updating"), on_press=self.done),
            ]

        self._w = screen(rows, buttons, excerpt=_(self.progress_excerpt))

    def offer_update(self, sender=None):
        if self.spinner is not None:
            self.spinner.stop()
        rows = [Text("hi")]

        buttons = button_pile([
            forward_btn(_("Update"), on_press=self.update),
            done_btn(_("Continue without updating"), on_press=self.done),
            cancel_btn(_("Back"), on_press=self.cancel),
            ])
        buttons.base_widget.focus_position = 1
        self._w = screen(rows, buttons, excerpt=_(self.offer_excerpt))

    def check_failed(self):
        if self.spinner is not None:
            self.spinner.stop()
        rows = [Text("hi")]

        buttons = button_pile([
            forward_btn(_("Retry"), on_press=self.still_checking),
            done_btn(_("Continue without updating"), on_press=self.done),
            cancel_btn(_("Back"), on_press=self.cancel),
            ])
        buttons.base_widget.focus_position = 1
        self._w = screen(rows, buttons, excerpt=_(self.offer_excerpt))

    def update(self, sender=None):
        self.controller.ui.set_header("Downloading update...")
        self.doing_bar = SnapdProgressBar()
        rows = [self.doing_bar]

        buttons = [
            forward_btn(_("Cancel update"), on_press=self.offer_update),
            ]

        self._w = screen(rows, buttons, excerpt=_(self.still_checking_excerpt))
        self.controller.start_refresh(self.update_started)

    def update_started(self, change_id):
        self.change_id = change_id
        self.update_progress()

    def update_progress(self):
        self.controller.get_progress(self.change_id, self.updated_progress)

    def updated_progress(self, change):
        if change['Done']:
            # Unlikely to get here because we should be being restarted!
            return
        for task in change['tasks']:
            if task['status'] == "Doing":
                self.doing_label = task['progress']['label']
                done = task['progress']['done']
                total = task['progress']['total']
                self.doing_bar.label = task['progress']['label']
                self.doing_bar.done = done
                self.doing_bar.total = total
                self.doing_bar.set_completion(100*done/total)
        self.controller.loop.set_alarm_in(0.1, self.update_progress)

    def done(self, result=None):
        if self.spinner is not None:
            self.spinner.stop()
        self.controller.done()

    def cancel(self, result=None):
        if self.spinner is not None:
            self.spinner.stop()
        self.controller.cancel()
