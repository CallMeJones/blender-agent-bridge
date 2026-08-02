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
ADVANCED_MODELING = ROOT / "addon" / "claude_blender" / "advanced_modeling.py"
REFERENCE_GUIDES = ROOT / "addon" / "claude_blender" / "reference_guides.py"
REFERENCE_BLOCKOUT = ROOT / "addon" / "claude_blender" / "reference_blockout.py"
REFERENCE_PARTS = ROOT / "addon" / "claude_blender" / "reference_parts.py"
REFERENCE_PART_SCENE = (
    ROOT / "addon" / "claude_blender" / "reference_part_scene.py"
)
REFERENCE_FEATURE_STACKS = (
    ROOT / "addon" / "claude_blender" / "reference_feature_stacks.py"
)
REFERENCE_FUR_FLOW = ROOT / "addon" / "claude_blender" / "reference_fur_flow.py"
SCULPT_FIELDS = ROOT / "addon" / "claude_blender" / "sculpt_fields.py"
SEMANTIC_SCULPT = ROOT / "addon" / "claude_blender" / "semantic_sculpt.py"
ADAPTIVE_REMESH = ROOT / "addon" / "claude_blender" / "adaptive_remesh.py"
VISUAL_HULL = ROOT / "addon" / "claude_blender" / "visual_hull.py"
DEPTH_FIELDS = ROOT / "addon" / "claude_blender" / "depth_fields.py"
REFERENCE_FITTING = ROOT / "addon" / "claude_blender" / "reference_fitting.py"
REFERENCE_VISUAL_HULL = (
    ROOT / "addon" / "claude_blender" / "reference_visual_hull.py"
)
REFERENCE_DEPTH = ROOT / "addon" / "claude_blender" / "reference_depth.py"
REFERENCE_SURFACE_FITTING = (
    ROOT / "addon" / "claude_blender" / "reference_surface_fitting.py"
)
REFERENCE_BENCHMARK_SCENE = (
    ROOT / "addon" / "claude_blender" / "reference_benchmark_scene.py"
)
REFERENCE_MULTIVIEW = ROOT / "addon" / "claude_blender" / "reference_multiview.py"
REFERENCE_MULTIVIEW_SCENE = (
    ROOT / "addon" / "claude_blender" / "reference_multiview_scene.py"
)


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

    def test_reference_annotation_policy_reloads_before_scene_consumer(self):
        tree = ast.parse(ENTRYPOINT.read_text(encoding="utf-8"))
        module_names = ()
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            if any(
                isinstance(target, ast.Name) and target.id == "_MODULE_NAMES"
                for target in node.targets
            ):
                module_names = ast.literal_eval(node.value)
                break

        self.assertIn("reference_annotations", module_names)
        self.assertIn("reference_guides", module_names)
        self.assertIn("inspection_render", module_names)
        self.assertIn("reference_comparison", module_names)
        self.assertIn("reference_forms", module_names)
        self.assertIn("reference_parts", module_names)
        self.assertIn("fur_groom", module_names)
        self.assertIn("reference_multiview", module_names)
        self.assertIn("reference_multiview_scene", module_names)
        self.assertIn("visual_hull", module_names)
        self.assertIn("depth_fields", module_names)
        self.assertIn("reference_fitting", module_names)
        self.assertIn("reference_depth", module_names)
        self.assertIn("reference_visual_hull", module_names)
        self.assertIn("reference_surface_fitting", module_names)
        self.assertIn("reference_scene", module_names)
        self.assertIn("reference_blockout", module_names)
        self.assertIn("reference_part_scene", module_names)
        self.assertIn("reference_feature_stacks", module_names)
        self.assertIn("reference_fur_flow", module_names)
        self.assertIn("sculpt_fields", module_names)
        self.assertIn("semantic_sculpt", module_names)
        self.assertIn("adaptive_remesh", module_names)
        self.assertIn("reference_benchmarks", module_names)
        self.assertIn("reference_benchmark_scene", module_names)
        self.assertLess(
            module_names.index("reference_annotations"),
            module_names.index("reference_guides"),
        )
        self.assertLess(
            module_names.index("reference_guides"),
            module_names.index("reference_comparison"),
        )
        self.assertLess(
            module_names.index("inspection_render"),
            module_names.index("reference_comparison"),
        )
        self.assertLess(
            module_names.index("reference_forms"),
            module_names.index("reference_blockout"),
        )
        self.assertLess(
            module_names.index("reference_parts"),
            module_names.index("reference_part_scene"),
        )
        self.assertLess(
            module_names.index("reference_scene"),
            module_names.index("reference_blockout"),
        )
        self.assertLess(
            module_names.index("reference_blockout"),
            module_names.index("reference_part_scene"),
        )
        self.assertLess(
            module_names.index("reference_part_scene"),
            module_names.index("reference_feature_stacks"),
        )
        self.assertLess(
            module_names.index("advanced_rigging"),
            module_names.index("reference_fur_flow"),
        )
        self.assertLess(
            module_names.index("reference_multiview"),
            module_names.index("reference_multiview_scene"),
        )
        self.assertLess(
            module_names.index("visual_hull"),
            module_names.index("reference_visual_hull"),
        )
        self.assertLess(
            module_names.index("depth_fields"),
            module_names.index("visual_hull"),
        )
        self.assertLess(
            module_names.index("visual_hull"),
            module_names.index("reference_fitting"),
        )
        self.assertLess(
            module_names.index("reference_depth"),
            module_names.index("reference_visual_hull"),
        )
        self.assertLess(
            module_names.index("reference_fitting"),
            module_names.index("reference_surface_fitting"),
        )
        self.assertLess(
            module_names.index("reference_comparison"),
            module_names.index("reference_surface_fitting"),
        )
        self.assertLess(
            module_names.index("reference_multiview_scene"),
            module_names.index("reference_visual_hull"),
        )
        self.assertLess(
            module_names.index("reference_benchmarks"),
            module_names.index("reference_benchmark_scene"),
        )
        self.assertLess(
            module_names.index("reference_comparison"),
            module_names.index("reference_benchmark_scene"),
        )
        self.assertLess(
            module_names.index("sculpt_fields"),
            module_names.index("semantic_sculpt"),
        )
        self.assertLess(
            module_names.index("reference_comparison"),
            module_names.index("semantic_sculpt"),
        )
        self.assertLess(
            module_names.index("semantic_sculpt"),
            module_names.index("adaptive_remesh"),
        )
        self.assertLess(
            module_names.index("reference_guides"),
            module_names.index("reference_multiview_scene"),
        )
        self.assertLess(
            module_names.index("fur_groom"),
            module_names.index("advanced_rigging"),
        )

    def test_reference_guide_scene_ownership_is_separate_from_mesh_modeling(self):
        required = {
            "create_reference_modeling_guides",
            "create_reference_guides_from_annotations",
            "inspect_reference_modeling_guides",
        }
        reference_tree = ast.parse(REFERENCE_GUIDES.read_text(encoding="utf-8"))
        modeling_tree = ast.parse(ADVANCED_MODELING.read_text(encoding="utf-8"))
        reference_functions = {
            node.name for node in reference_tree.body if isinstance(node, ast.FunctionDef)
        }
        modeling_functions = {
            node.name for node in modeling_tree.body if isinstance(node, ast.FunctionDef)
        }

        self.assertTrue(required.issubset(reference_functions))
        self.assertFalse(required & modeling_functions)

        blockout_tree = ast.parse(REFERENCE_BLOCKOUT.read_text(encoding="utf-8"))
        blockout_functions = {
            node.name
            for node in blockout_tree.body
            if isinstance(node, ast.FunctionDef)
        }
        self.assertIn("create_reference_blockout", blockout_functions)
        self.assertNotIn("create_reference_blockout", modeling_functions)

        parts_functions = {
            node.name
            for node in ast.parse(REFERENCE_PARTS.read_text(encoding="utf-8")).body
            if isinstance(node, ast.FunctionDef)
        }
        part_scene_functions = {
            node.name
            for node in ast.parse(
                REFERENCE_PART_SCENE.read_text(encoding="utf-8")
            ).body
            if isinstance(node, ast.FunctionDef)
        }
        self.assertIn("infer_part_graph", parts_functions)
        self.assertIn("create_reference_part_graph", part_scene_functions)
        self.assertIn("build_part_aware_base_mesh", part_scene_functions)
        self.assertNotIn("create_reference_part_graph", modeling_functions)
        self.assertNotIn("build_part_aware_base_mesh", modeling_functions)

        feature_stack_functions = {
            node.name
            for node in ast.parse(
                REFERENCE_FEATURE_STACKS.read_text(encoding="utf-8")
            ).body
            if isinstance(node, ast.FunctionDef)
        }
        self.assertIn("create_eye_stack", feature_stack_functions)
        self.assertIn("create_muzzle_stack", feature_stack_functions)
        self.assertIn("create_ear_stack", feature_stack_functions)
        self.assertNotIn("create_eye_stack", modeling_functions)
        self.assertNotIn("create_muzzle_stack", modeling_functions)
        self.assertNotIn("create_ear_stack", modeling_functions)

        fur_flow_functions = {
            node.name
            for node in ast.parse(REFERENCE_FUR_FLOW.read_text(encoding="utf-8")).body
            if isinstance(node, ast.FunctionDef)
        }
        self.assertIn("create_part_weight_vertex_groups", fur_flow_functions)
        self.assertIn("create_fur_flow_field_from_parts", fur_flow_functions)
        self.assertNotIn("create_part_weight_vertex_groups", modeling_functions)
        self.assertNotIn("create_fur_flow_field_from_parts", modeling_functions)

        multiview_tree = ast.parse(
            REFERENCE_MULTIVIEW_SCENE.read_text(encoding="utf-8")
        )
        multiview_functions = {
            node.name
            for node in multiview_tree.body
            if isinstance(node, ast.FunctionDef)
        }
        self.assertIn("create_multiview_reference_guides", multiview_functions)
        self.assertNotIn(
            "create_multiview_reference_guides",
            modeling_functions,
        )

        benchmark_tree = ast.parse(
            REFERENCE_BENCHMARK_SCENE.read_text(encoding="utf-8")
        )
        benchmark_functions = {
            node.name
            for node in benchmark_tree.body
            if isinstance(node, ast.FunctionDef)
        }
        self.assertIn(
            "evaluate_reference_model_benchmark",
            benchmark_functions,
        )
        self.assertNotIn(
            "evaluate_reference_model_benchmark",
            modeling_functions,
        )

        sculpt_field_tree = ast.parse(SCULPT_FIELDS.read_text(encoding="utf-8"))
        sculpt_field_functions = {
            node.name
            for node in sculpt_field_tree.body
            if isinstance(node, ast.FunctionDef)
        }
        semantic_tree = ast.parse(SEMANTIC_SCULPT.read_text(encoding="utf-8"))
        semantic_functions = {
            node.name
            for node in semantic_tree.body
            if isinstance(node, ast.FunctionDef)
        }
        self.assertIn("sphere_weights", sculpt_field_functions)
        self.assertIn("define_semantic_sculpt_regions", semantic_functions)
        self.assertIn("apply_semantic_sculpt", semantic_functions)
        self.assertIn("apply_form_aware_sculpt", semantic_functions)
        self.assertIn("apply_screen_space_sculpt", semantic_functions)
        public_semantic_functions = {
            name
            for name in semantic_functions
            if not name.startswith("_") and name not in {"register", "unregister"}
        }
        self.assertFalse(public_semantic_functions & modeling_functions)

        visual_hull_functions = {
            node.name
            for node in ast.parse(VISUAL_HULL.read_text(encoding="utf-8")).body
            if isinstance(node, ast.FunctionDef)
        }
        visual_hull_scene_functions = {
            node.name
            for node in ast.parse(
                REFERENCE_VISUAL_HULL.read_text(encoding="utf-8")
            ).body
            if isinstance(node, ast.FunctionDef)
        }
        adaptive_functions = {
            node.name
            for node in ast.parse(ADAPTIVE_REMESH.read_text(encoding="utf-8")).body
            if isinstance(node, ast.FunctionDef)
        }
        self.assertIn("carve_visual_hull", visual_hull_functions)
        self.assertIn("create_multiview_visual_hull", visual_hull_scene_functions)
        self.assertIn("create_multiview_depth_surface", visual_hull_scene_functions)
        self.assertIn("adaptive_remesh", adaptive_functions)

        depth_functions = {
            node.name
            for node in ast.parse(DEPTH_FIELDS.read_text(encoding="utf-8")).body
            if isinstance(node, ast.FunctionDef)
        }
        fitting_functions = {
            node.name
            for node in ast.parse(REFERENCE_FITTING.read_text(encoding="utf-8")).body
            if isinstance(node, ast.FunctionDef)
        }
        depth_scene_functions = {
            node.name
            for node in ast.parse(REFERENCE_DEPTH.read_text(encoding="utf-8")).body
            if isinstance(node, ast.FunctionDef)
        }
        fitting_scene_functions = {
            node.name
            for node in ast.parse(
                REFERENCE_SURFACE_FITTING.read_text(encoding="utf-8")
            ).body
            if isinstance(node, ast.FunctionDef)
        }
        self.assertIn("sample_depth", depth_functions)
        self.assertIn("fit_surface_to_references", fitting_functions)
        self.assertIn("attach_depth_sources", depth_scene_functions)
        self.assertIn(
            "fit_surface_to_multiview_references",
            fitting_scene_functions,
        )

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
