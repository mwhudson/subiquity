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

""" Base Frame Widget """

import logging

from subiquitycore.ui.buttons import _stylized_button
from subiquitycore.ui.frame import SubiquityCoreUI


log = logging.getLogger('subiquitycore.ui.frame')


class SubiquityUI(SubiquityCoreUI):

    def __init__(self, app):
        self.right_icon = _stylized_button("[", "]", 'xx')(
            _("Help"), on_press=lambda sender: app.show_help())
        self.right_icon.attr_map = {}
        self.right_icon.focus_map = {None: 'progress_incomplete'}
        super().__init__()
