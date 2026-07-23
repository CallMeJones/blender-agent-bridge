from __future__ import annotations

import ast
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
HANDLERS = ROOT / "addon" / "claude_blender" / "tool_handlers"
REGISTRY = ROOT / "addon" / "claude_blender" / "tool_registry" / "__init__.py"
RUNTIME = ROOT / "addon" / "claude_blender" / "handler_runtime.py"
ANIMATION_RUNTIME = ROOT / "addon" / "claude_blender" / "animation_runtime.py"
EXECUTOR = ROOT / "addon" / "claude_blender" / "tool_executor.py"
ENTRYPOINT = ROOT / "addon" / "claude_blender" / "__init__.py"
ADVANCED_FACADE = ROOT / "addon" / "claude_blender" / "advanced_helpers.py"


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

    def test_registry_composition_lives_above_runtime_and_handlers(self):
        runtime_source = RUNTIME.read_text(encoding="utf-8")
        animation_runtime_source = ANIMATION_RUNTIME.read_text(encoding="utf-8")
        executor_source = EXECUTOR.read_text(encoding="utf-8")

        self.assertNotIn("tool_registry.build_handlers()", runtime_source)
        self.assertNotIn("tool_registry.build_handlers()", animation_runtime_source)
        self.assertNotIn("globals().update", runtime_source)
        self.assertIn("tool_registry.build_handlers()", executor_source)
        self.assertIn("animation_runtime.configure_tool_handler_lookup", executor_source)

    def test_reload_rebuilds_executor_after_runtime_and_handlers(self):
        source = ENTRYPOINT.read_text(encoding="utf-8")
        self.assertIn('sys.modules.get(f"{package}.animation_runtime")', source)
        self.assertIn("importlib.reload(animation_runtime)", source)
        self.assertIn('sys.modules.get(f"{package}.tool_executor")', source)
        self.assertIn("importlib.reload(executor)", source)

    def test_domain_handlers_import_domain_helpers_not_advanced_facade(self):
        for path in sorted(HANDLERS.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imported_modules = {
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
                for alias in node.names
            }
            self.assertNotIn("advanced_helpers", imported_modules, path.name)

    def test_advanced_helpers_is_a_compatibility_facade_only(self):
        source = ADVANCED_FACADE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        implementations = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertEqual({"register", "unregister"}, implementations)
        for retained_entrypoint in (
            "get_2d_animation_details",
            "plan_advanced_scene_workflow",
            "plan_asset_import_workflow",
            "plan_director_workflow",
        ):
            self.assertIn(retained_entrypoint, source)

    def test_animation_orchestration_is_not_owned_by_generic_runtime(self):
        generic_source = RUNTIME.read_text(encoding="utf-8")
        animation_source = ANIMATION_RUNTIME.read_text(encoding="utf-8")
        self.assertNotIn("_ANIMATION_WORKFLOW_MARKERS", generic_source)
        self.assertNotIn("_execute_workflow_tool", generic_source)
        self.assertIn("_ANIMATION_WORKFLOW_MARKERS", animation_source)
        self.assertIn("_execute_workflow_tool", animation_source)

    def test_domain_handlers_use_neutral_support_for_shared_argument_helpers(self):
        moved_helpers = {
            "_bounded_float",
            "_bounded_int",
            "_extract_script_code",
            "_float_list",
            "_name_list",
            "_optional_float",
            "_optional_float_list",
            "_resolve_objects",
            "_simulation_bake_script",
        }
        for path in sorted(HANDLERS.glob("*.py")):
            if path.name == "support.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            runtime_imports = {
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module == "handler_runtime"
                for alias in node.names
            }
            self.assertFalse(runtime_imports & moved_helpers, path.name)


if __name__ == "__main__":
    unittest.main()
