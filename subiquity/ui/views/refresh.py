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
from subiquitycore.ui.anchors import StepsProgressBar
from subiquitycore.ui.buttons import forward_btn, done_btn, cancel_btn
from subiquitycore.ui.utils import button_pile, screen

from subiquity.controllers.refresh import CHECK_STATE
from subiquity.ui.spinner import Spinner

log = logging.getLogger('subiquity.refresh')

spin_texts = ['-', '\\', '|', '/']

class SnapdProgressBar(ProgressBar):
    def __init__(self):
        self.label = ""
        self.done_text = ""
        self.total_text = ""
        self.spinning = True
        self.spin_text = ''
        self.spin_i = 0
        self.maxcol = 76

        super().__init__(
            normal='progress_incomplete',
            complete='progress_complete')

    def start_spinning(self):
        self.spinning = True

    def stop_spinning(self):
        self.spinning = False

    def spin(self):
        self.spin_text = spin_texts[self.spin_i % len(spin_texts)]
        self.spin_i += 1
        self._invalidate()

    def render(self, size, focus=False):
        self.maxcol = size[0]
        return super().render(size, focus)

    def get_text(self):
        if self.spinning:
            suffix = self.spin_text
        else:
            suffix =  "{} / {}".format(self.done_text, self.total_text)
        left = self.maxcol - len(suffix) - 3
        if len(self.label) > left:
            label = self.label[:left-3] + '...'
        else:
            label = self.label + ' ' * (left - len(self.label))
        return label + ' ' + suffix


def fmt(q):
    q /= 1024*1024
    return "{:.2f}".format(q)


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

        self.last_task_id = None

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

        self._w = screen(rows, buttons, excerpt=_(self.still_checking_excerpt))

    def offer_update(self, sender=None):
        if self.spinner is not None:
            self.spinner.stop()
        rows = [Text("hi")]

        buttons = button_pile([
            done_btn(_("Update"), on_press=self.update),
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
        self.task_bar = SnapdProgressBar()
        rows = [self.task_bar]

        buttons = [
            cancel_btn(_("Cancel update"), on_press=self.offer_update),
            ]

        self._w = screen(rows, buttons, excerpt=_(self.progress_excerpt))
        self.controller.start_update(self.update_started)

    def update_started(self, change_id):
        self.change_id = change_id
        self.update_progress()

    def update_progress(self, loop=None, ud=None):
        self.controller.get_progress(self.change_id, self.updated_progress)

    def updated_progress(self, change):
        if change['status'] == 'Done':
            # Won't get here when not in dry run mode as we'll have been
            # restarted.
            self.done()
            return
        for task in change['tasks']:
            if task['status'] == "Doing":
                total = task['progress']['total']
                done = task['progress']['done']
                total = task['progress']['total']
                self.task_bar.label = task['summary']
                if total == 1:
                    self.task_bar.start_spinning()
                    self.task_bar.spin()
                    self.task_bar.set_completion(0)
                else:
                    self.task_bar.stop_spinning()
                    self.task_bar.done_text = fmt(done)
                    self.task_bar.total_text = fmt(total) + " MiB"
                    self.task_bar.set_completion(100*done/total)
                self.last_task_id == task['id']
        self.controller.loop.set_alarm_in(0.1, self.update_progress)

    def done(self, result=None):
        if self.spinner is not None:
            self.spinner.stop()
        self.controller.done()

    def cancel(self, result=None):
        if self.spinner is not None:
            self.spinner.stop()
        self.controller.cancel()
