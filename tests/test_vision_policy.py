import unittest

from ancharview.desktop import _is_text_value_role
from ancharview.server import _select_context, _visual_decision


class VisionPolicyTests(unittest.TestCase):
    def test_visual_goal_includes_image(self) -> None:
        include, _ = _visual_decision([], "compare the chart colors", "auto")
        self.assertTrue(include)

    def test_screen_description_includes_image_with_good_accessibility(self) -> None:
        nodes = [
            {"name": "Save", "automation_id": "save", "role": "Button"},
            {"name": "File name", "automation_id": "name", "role": "Edit"},
            {"name": "Save as type", "automation_id": "type", "role": "ComboBox"},
            {"name": "Cancel", "automation_id": "cancel", "role": "Button"},
        ]
        include, _ = _visual_decision(nodes, "describe what is currently on screen", "auto")
        self.assertTrue(include)

    def test_sparse_accessibility_includes_image(self) -> None:
        include, _ = _visual_decision([{"name": "Window", "automation_id": "", "role": "Window"}], "save the file", "auto")
        self.assertTrue(include)

    def test_semantic_tree_avoids_image_for_control_task(self) -> None:
        nodes = [
            {"name": "Save", "automation_id": "save", "role": "Button"},
            {"name": "File name", "automation_id": "name", "role": "Edit"},
            {"name": "Save as type", "automation_id": "type", "role": "ComboBox"},
            {"name": "Cancel", "automation_id": "cancel", "role": "Button"},
        ]
        include, _ = _visual_decision(nodes, "click the Save button", "auto")
        self.assertFalse(include)

    def test_mode_overrides_auto_policy(self) -> None:
        nodes = [{"name": "Save", "automation_id": "save", "role": "Button"}]
        self.assertTrue(_visual_decision(nodes, "save", "always")[0])
        self.assertFalse(_visual_decision([], "inspect this chart", "never")[0])


class ContextSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.nodes = [
            {"element_id": "root", "parent_id": None, "depth": 0, "name": "App", "visible": True},
            {"element_id": "toolbar", "parent_id": "root", "depth": 1, "name": "Toolbar", "visible": True},
            {"element_id": "save", "parent_id": "toolbar", "depth": 2, "name": "Save", "visible": True, "patterns": ["invoke"], "relevance": 1.0},
            {"element_id": "cancel", "parent_id": "toolbar", "depth": 2, "name": "Cancel", "visible": True, "patterns": ["invoke"], "relevance": 0.0},
        ]

    def test_interactive_context_keeps_match_and_ancestors_only(self) -> None:
        selected = _select_context(self.nodes, "save", "interactive", 20)

        self.assertEqual([node["element_id"] for node in selected], ["root", "toolbar", "save"])

    def test_full_context_keeps_unmatched_nodes(self) -> None:
        selected = _select_context(self.nodes, "save", "full", 20)

        self.assertEqual(len(selected), 4)

    def test_minimal_context_prefers_focus(self) -> None:
        self.nodes[3]["focused"] = True

        selected = _select_context(self.nodes, "save", "minimal", 20)

        self.assertIn("cancel", [node["element_id"] for node in selected])
        self.assertIn("save", [node["element_id"] for node in selected])


class SensitiveFieldTests(unittest.TestCase):
    def test_sensitive_edit_roles_do_not_expose_accessible_name(self) -> None:
        self.assertTrue(_is_text_value_role("windows", "Edit"))
        self.assertTrue(_is_text_value_role("windows", "ComboBox"))
        self.assertTrue(_is_text_value_role("linux", "text"))
        self.assertTrue(_is_text_value_role("linux", "Password Text"))

    def test_static_text_and_buttons_are_not_treated_as_input(self) -> None:
        self.assertFalse(_is_text_value_role("windows", "Text"))
        self.assertFalse(_is_text_value_role("linux", "label"))
        self.assertFalse(_is_text_value_role("windows", "Button"))


if __name__ == "__main__":
    unittest.main()