import unittest
from unittest import mock

import urwid

from subiquitycore.testing import view_helpers

from subiquity.client.controllers.filesystem import FilesystemController
from subiquity.models.filesystem import (
    Bootloader,
    FilesystemModel,
    )
from subiquity.models.tests.test_filesystem import (
    make_disk,
    )
from subiquity.ui.views.filesystem.filesystem import FilesystemView


class FilesystemViewTests(unittest.TestCase):

    def make_view(self, model, devices=[]):
        controller = mock.create_autospec(spec=FilesystemController)
        controller.ui = mock.Mock()
        model.bootloader = Bootloader.NONE
        model.all_devices.return_value = devices
        return FilesystemView(model, controller)

    def test_simple(self):
        self.make_view(mock.create_autospec(spec=FilesystemModel))

    def test_one_disk(self):
        model = mock.create_autospec(spec=FilesystemModel)
        model._probe_data = {}
        model._actions = []
        model._all_ids = set()
        disk = make_disk(model, serial="DISK-SERIAL")
        view = self.make_view(model, [disk])
        w = view_helpers.find_with_pred(
            view,
            lambda w: isinstance(w, urwid.Text) and "DISK-SERIAL" in w.text)
        self.assertIsNotNone(w, "could not find DISK-SERIAL in view")
