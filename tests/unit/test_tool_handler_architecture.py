from __future__ import annotations

import ast
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
HANDLERS = ROOT / "addon" / "claude_blender" / "tool_handlers"
REGISTRY = ROOT / "addon" / "claude_blender" / "tool_registry" / "__init__.py"


class ToolHandlerArchitectureTests(unittest.TestCase):
    def test_domain_handlers_declare_runtime_dependencies_explicitly(self):
        for path in sorted(HANDLERS.glob("*.py")):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("vars(_runtime).items()", source, path.name)
            self.assertNotIn("globals()[_runtime_name]", source, path.name)

            tree = ast.parse(source, filename=str(path))
            broad_runtime_imports = [
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
                and node.module == "handler_runtime"
                and any(alias.name == "*" for alias in node.names)
            ]
            self.assertEqual([], broad_runtime_imports, path.name)

    def test_registry_does_not_mutate_handler_global_namespaces(self):
        source = REGISTRY.read_text(encoding="utf-8")
        self.assertNotIn("handler.__globals__.update", source)


if __name__ == "__main__":
    unittest.main()
