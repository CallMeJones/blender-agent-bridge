from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
ADDON_INIT = ROOT / "addon" / "claude_blender" / "__init__.py"


def _tuple_assignment(name):
    tree = ast.parse(ADDON_INIT.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return set(ast.literal_eval(node.value))
    raise AssertionError(f"Missing {name} in {ADDON_INIT}")


class ReloadInventoryTests(unittest.TestCase):
    def test_every_registry_domain_is_reloaded(self):
        domains = {
            f"tool_registry.domains.{path.stem}"
            for path in (ROOT / "addon" / "claude_blender" / "tool_registry" / "domains").glob("*.py")
            if path.stem != "__init__"
        }
        configured = {
            name for name in _tuple_assignment("_TOOL_REGISTRY_RELOAD_ORDER") if name.startswith("tool_registry.domains.")
        }
        self.assertEqual(domains, configured)

    def test_every_modular_handler_is_reloaded(self):
        handlers = {
            f"tool_handlers.{path.stem}"
            for path in (ROOT / "addon" / "claude_blender" / "tool_handlers").glob("*.py")
            if path.stem != "__init__"
        }
        configured = _tuple_assignment("_TOOL_HANDLER_RELOAD_ORDER")
        self.assertEqual(handlers, configured)

    def test_generation_provider_policy_is_reloaded_before_dispatch(self):
        configured = list(_tuple_assignment("_MODULE_NAMES"))
        self.assertIn("generation_providers", configured)

        source = ADDON_INIT.read_text(encoding="utf-8")
        generation_index = source.index('    "generation_providers",')
        dispatcher_index = source.index('    "tool_dispatcher",')
        self.assertLess(generation_index, dispatcher_index)


if __name__ == "__main__":
    unittest.main()
