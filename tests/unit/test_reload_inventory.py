from __future__ import annotations

import ast
from pathlib import Path
import unittest
import sys


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
    def test_every_shipped_module_has_one_lifecycle_owner(self):
        sys.path.insert(0, str(ROOT / "addon"))
        import claude_blender
        root = ROOT / "addon" / "claude_blender"
        shipped = set()
        for path in root.rglob("*.py"):
            parts = list(path.relative_to(root).with_suffix("").parts)
            if len(parts) > 1 and parts[-1] == "__init__":
                parts.pop()
            shipped.add(".".join(parts))
        groups = [claude_blender._MODULE_NAMES, claude_blender._TOOL_REGISTRY_RELOAD_ORDER,
                  claude_blender._TOOL_HANDLER_RELOAD_ORDER, claude_blender._EXECUTOR_MODULES,
                  claude_blender._PERSISTENT_MODULES, claude_blender._EXTERNAL_RUNTIME_MODULES,
                  claude_blender._PACKAGE_MODULES]
        declared = [name for group in groups for name in group]
        self.assertEqual(len(declared), len(set(declared)), "Duplicate lifecycle owners")
        self.assertEqual(shipped, set(claude_blender.module_lifecycle_inventory()))

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
