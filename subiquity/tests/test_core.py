from unittest import TestCase

from urwid import Text

from subiquitycore.testing import view_helpers
from subiquitycore.ui.stretchy import StretchyOverlay
from subiquitycore.view import BaseView

from subiquity.core import Subiquity
from subiquity.ui.views.global_extra import GlobalExtraStretchy


class FakeOpts:
    bootloader = None
    machine_config = None
    dry_run = True
    answers = None
    screens = None
    snaps_from_examples = True


class NoLocalHelpView(BaseView):
    def __init__(self):
        super().__init__(Text(""))


class LocalHelpView(NoLocalHelpView):
    def local_help(self):
        return "title", "local help content"


class SubiquityTests(TestCase):

    def make_app(self, view=None):
        app = Subiquity(FakeOpts(), '')

        if view is None:
            view = NoLocalHelpView()
        app.ui.set_body(view)

        return app

    def test_global_extra(self):
        app = self.make_app()

        app.ui._w.base_widget.focus_position = 2

        self.assertTrue(app.ui.right_icon.selectable())

        app.show_global_extra()

        for w in view_helpers.get_focus_path(app.ui._w):
            if isinstance(w, StretchyOverlay):
                if isinstance(w.stretchy, GlobalExtraStretchy):
                    break
        else:
            self.fail("global extra dialog not focused")

        self.assertIsNotNone(
            view_helpers.find_button_matching(
                overlay,
                '^Read about global hot keys$'))

        self.assertFalse(app.ui.right_icon.selectable())

        app.ui.body.remove_overlay()
        self.assertEqual(app.ui._w.base_widget.focus_position, 2)
        self.assertTrue(app.ui.right_icon.selectable())

    def test_global_extra_keys(self):
        app = self.make_app()
        app.unhandled_input('f1')
        self.assertTrue(app.showing_global_extra)
        app = self.make_app()
        app.unhandled_input('ctrl h')
        self.assertTrue(app.showing_global_extra)

    def test_general_help(self):
        app = self.make_app()
        overlay = app.show_global_extra()

        general_help_btn = view_helpers.find_button_matching(
            overlay, '^Read about this installer$')
        self.assertIsNotNone(general_help_btn)

        for w in view_helpers.get_focus_path(overlay):
            if w is general_help_btn:
                break
        else:
            self.fail("about button not focused")

        view_helpers.click(general_help_btn)

        def pred(w):
            return isinstance(w, Text) and \
              'Welcome to the Ubuntu Server Installer' in w.text

        self.assertIsNotNone(view_helpers.find_with_pred(app.ui, pred))

    def test_global_keys_help(self):
        app = self.make_app()
        overlay = app.show_global_extra()

        global_hot_keys_btn = view_helpers.find_button_matching(
            overlay, '^Read about global hot keys$')
        self.assertIsNotNone(global_hot_keys_btn)

        view_helpers.click(global_hot_keys_btn)

        def pred(w):
            return isinstance(w, Text) and \
              'The following keys can be used at any time' in w.text

        self.assertIsNotNone(view_helpers.find_with_pred(app.ui, pred))

    def test_no_local_help(self):
        app = self.make_app(NoLocalHelpView())
        overlay = app.show_global_extra()

        self.assertIsNone(view_helpers.find_button_matching(
            overlay, '^View help on this screen$'))

    def test_local_help(self):
        app = self.make_app(LocalHelpView())
        overlay = app.show_global_extra()

        local_help_btn = view_helpers.find_button_matching(
            overlay, '^View help on this screen$')
        self.assertIsNotNone(local_help_btn)

        view_helpers.click(local_help_btn)

        def pred(w):
            return isinstance(w, Text) and \
              'local help content' in w.text

        self.assertIsNotNone(view_helpers.find_with_pred(app.ui, pred))
