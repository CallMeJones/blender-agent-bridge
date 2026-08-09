"""Canonical trace, benchmark, and quality-review tool specifications."""

from __future__ import annotations

from ..registry import ToolSpec
from .workflows_refinement import REFERENCE_BRIEF_SCHEMA


TOKEN_USAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "input_tokens": {"type": "integer", "minimum": 0},
        "output_tokens": {"type": "integer", "minimum": 0},
        "total_tokens": {"type": "integer", "minimum": 0},
        "cached_input_tokens": {"type": "integer", "minimum": 0},
        "cache_creation_input_tokens": {"type": "integer", "minimum": 0},
        "cache_read_input_tokens": {"type": "integer", "minimum": 0},
    },
    "additionalProperties": False,
}

QUALITY_SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "criterion": {"type": "string", "maxLength": 120},
        "score": {"type": "integer", "minimum": 1, "maximum": 5},
        "evidence": {
            "type": "array",
            "items": {"type": "string", "maxLength": 1000},
            "minItems": 1,
            "maxItems": 20,
        },
        "finding": {"type": "string", "maxLength": 2000},
        "repair_action": {"type": "string", "maxLength": 2000},
    },
    "required": ["criterion", "score", "evidence", "finding", "repair_action"],
    "additionalProperties": False,
}

QUALITY_REPAIR_SCHEMA = {
    "type": "object",
    "properties": {
        "criterion": {"type": "string", "maxLength": 120},
        "action": {"type": "string", "maxLength": 2000},
        "result": {"type": "string", "maxLength": 2000},
    },
    "required": ["criterion", "action"],
    "additionalProperties": False,
}

REFERENCE_BENCHMARK_THRESHOLD_SCHEMA = {
    "type": "object",
    "properties": {
        "min_silhouette_iou": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
        },
        "max_mean_edge_distance_ratio": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
        },
        "max_p95_edge_distance_ratio": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
        },
        "max_centroid_offset_ratio": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
        },
        "max_landmark_error_ratio": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
        },
        "max_error_region_magnitude": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
        },
        "require_landmarks": {"type": "boolean"},
    },
    "additionalProperties": False,
}


def _read_contract(description):
    return {
        "description": description,
        "mutates_scene": False,
        "has_side_effects": False,
        "supports_headless": True,
        "permissions": ["scene:read"],
    }


def _local_write_contract(description):
    return {
        "description": description,
        "mutates_scene": False,
        "has_side_effects": True,
        "supports_headless": True,
        "permissions": ["scene:read", "filesystem:write"],
    }


SPECS = (
    ToolSpec(
        name="start_execution_trace",
        description=(
            "Start a local replay-oriented execution trace. Subsequent MCP and Blender helper calls record ordered "
            "arguments, bounded results, timing where available, evidence URIs, and generated scripts as local "
            "artifacts. Credential-like arguments are redacted."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "maxLength": 160},
                "prompt": {"type": "string", "maxLength": 16000},
                "metadata": {"type": "object", "additionalProperties": True},
                "trace_id": {"type": "string", "maxLength": 100},
                "replace_active": {"type": "boolean"},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        contract=_local_write_contract("Start a durable local execution trace"),
        handler_key="start_execution_trace",
        order=1210,
        groups=("model_quality", "advanced_workflow", "observability"),
        exposure="catalog",
        owner="quality_observability",
    ),
    ToolSpec(
        name="get_execution_trace",
        description="Return one execution-trace manifest and optionally its ordered bounded events.",
        input_schema={
            "type": "object",
            "properties": {
                "trace_id": {"type": "string"},
                "include_events": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        contract=_read_contract("Read one local execution trace"),
        handler_key="get_execution_trace",
        order=1220,
        groups=("model_quality", "advanced_workflow", "observability"),
        exposure="catalog",
        owner="quality_observability",
    ),
    ToolSpec(
        name="list_execution_traces",
        description="List recent local execution traces without loading their events or script artifacts.",
        input_schema={
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}},
            "additionalProperties": False,
        },
        contract=_read_contract("List local execution traces"),
        handler_key="list_execution_traces",
        order=1230,
        groups=("model_quality", "advanced_workflow", "observability"),
        exposure="catalog",
        owner="quality_observability",
    ),
    ToolSpec(
        name="finalize_execution_trace",
        description=(
            "Finalize the active or named execution trace with an outcome, notes, and optional provider-reported "
            "token usage. Estimated trace payload tokens remain separate from reported model tokens."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "trace_id": {"type": "string"},
                "outcome": {"type": "string", "maxLength": 80},
                "notes": {"type": "string", "maxLength": 8000},
                "token_usage": TOKEN_USAGE_SCHEMA,
            },
            "additionalProperties": False,
        },
        contract=_local_write_contract("Finalize a durable local execution trace"),
        handler_key="finalize_execution_trace",
        order=1240,
        groups=("model_quality", "advanced_workflow", "observability"),
        exposure="catalog",
        owner="quality_observability",
    ),
    ToolSpec(
        name="prepare_execution_trace_replay",
        description=(
            "Prepare an ordered gateway-ready dry-run replay plan from a trace. Mutations are never executed "
            "automatically; credential blockers must be resolved and stored script code is withheld by default."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "trace_id": {"type": "string"},
                "include_script_code": {
                    "type": "boolean",
                    "description": "Resolve locally stored script artifacts into the replay packet. Defaults to false.",
                },
                "include_read_only": {"type": "boolean"},
            },
            "required": ["trace_id"],
            "additionalProperties": False,
        },
        contract=_read_contract("Prepare a non-executing replay plan from a local trace"),
        handler_key="prepare_execution_trace_replay",
        order=1250,
        groups=("model_quality", "advanced_workflow", "observability"),
        exposure="catalog",
        owner="quality_observability",
    ),
    ToolSpec(
        name="list_quality_benchmark_tasks",
        description=(
            "List versioned quality benchmark tasks for animal, human, hard-surface, negative animation routing, "
            "fresh five-tool gateway behavior, and required calibrated reference-metric profiles."
        ),
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        contract=_read_contract("List built-in versioned quality benchmark tasks"),
        handler_key="list_quality_benchmark_tasks",
        order=1260,
        groups=("model_quality", "advanced_workflow", "observability"),
        exposure="catalog",
        owner="quality_observability",
    ),
    ToolSpec(
        name="start_quality_benchmark_run",
        description=(
            "Start a versioned benchmark run and its execution trace. Reference-model tasks require an explicit "
            "reference URI or local path."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "enum": [
                        "reference_cartoon_animal",
                        "reference_human_character",
                        "reference_hard_surface_product",
                        "animation_wave_negative_routing",
                        "fresh_gateway_execution",
                    ],
                },
                "client_name": {"type": "string", "maxLength": 160},
                "model_name": {"type": "string", "maxLength": 160},
                "reference_uri": {"type": "string", "maxLength": 2000},
                "reference_sha256": {
                    "type": "string",
                    "pattern": "^[0-9a-fA-F]{64}$",
                    "description": "Optional SHA-256 for a non-local reference. Local files are fingerprinted automatically.",
                },
                "notes": {"type": "string", "maxLength": 4000},
                "replace_active_trace": {"type": "boolean"},
            },
            "required": ["task_id"],
            "additionalProperties": False,
        },
        contract=_local_write_contract("Start a versioned quality benchmark run and execution trace"),
        handler_key="start_quality_benchmark_run",
        order=1270,
        groups=("model_quality", "advanced_workflow", "observability"),
        exposure="catalog",
        owner="quality_observability",
    ),
    ToolSpec(
        name="get_quality_benchmark_run",
        description="Return a named benchmark run, or the latest run when run_id is omitted.",
        input_schema={
            "type": "object",
            "properties": {"run_id": {"type": "string"}},
            "additionalProperties": False,
        },
        contract=_read_contract("Read one local quality benchmark run"),
        handler_key="get_quality_benchmark_run",
        order=1280,
        groups=("model_quality", "advanced_workflow", "observability"),
        exposure="catalog",
        owner="quality_observability",
    ),
    ToolSpec(
        name="evaluate_reference_model_benchmark",
        description=(
            "Render a model through a calibrated reference camera, publish the mask/redline evidence, evaluate "
            "silhouette, edge, centroid, regional, and optional landmark metrics against versioned blockout, refined, "
            "or review thresholds, and optionally record the result on a running reference benchmark."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "profile": {
                    "type": "string",
                    "enum": ["blockout", "refined", "review"],
                },
                "threshold_overrides": {
                    **REFERENCE_BENCHMARK_THRESHOLD_SCHEMA,
                    "description": (
                        "Optional diagnostic thresholds. Evaluations using "
                        "overrides cannot satisfy an official benchmark run."
                    ),
                },
                "run_id": {
                    "type": "string",
                    "description": "Optional running reference-model benchmark to receive this evaluation.",
                },
                "collection_name": {"type": "string"},
                "camera_name": {"type": "string"},
                "object_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 64,
                },
                "selected_only": {"type": "boolean"},
                "outline_name": {"type": "string"},
                "reference_mask_source": {
                    "type": "string",
                    "enum": ["auto", "outline", "alpha"],
                },
                "landmark_targets": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "object_name": {"type": "string"},
                            "location": {
                                "type": "array",
                                "items": {"type": "number"},
                                "minItems": 3,
                                "maxItems": 3,
                            },
                        },
                        "required": ["name"],
                        "additionalProperties": False,
                    },
                    "maxItems": 128,
                },
                "max_axis": {
                    "type": "integer",
                    "minimum": 64,
                    "maximum": 1024,
                },
                "mask_threshold": {
                    "type": "number",
                    "minimum": 0.01,
                    "maximum": 0.99,
                },
                "include_structure": {
                    "type": "boolean",
                    "description": "Add basic topology-integrity gates from inspect_modeling_quality to the silhouette verdict.",
                },
                "structural_max_faces": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100000000,
                    "description": "Optional face budget. Zero records face count without gating it.",
                },
                "structural_require_materials": {"type": "boolean"},
                "structural_weight": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "description": "Weight of the structural score in the combined score; pass/fail always requires both terms.",
                },
            },
            "additionalProperties": False,
        },
        contract={
            **_local_write_contract(
                "Render and gate calibrated reference metrics, publish evidence, and optionally update a benchmark run"
            ),
            "permissions": ["scene:read", "files:read", "files:write"],
            "long_running": True,
            "duration_hint": "One bounded still render plus deterministic metric evaluation.",
            "timeout_recovery": {
                "recoverable": True,
                "poll_after_seconds": 5,
                "status_tool": "blender_bridge_status",
                "evidence_resource": "blender://inspection-renders/latest/metadata",
            },
        },
        handler_key="evaluate_reference_model_benchmark",
        order=1285,
        groups=(
            "model_quality",
            "reference_modeling",
            "observability",
        ),
        exposure="catalog",
        owner="quality_observability",
    ),
    ToolSpec(
        name="finish_quality_benchmark_run",
        description=(
            "Finish a benchmark run, evaluate observed routing/tool expectations, link its quality review, record "
            "reported token usage, and finalize the execution trace."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "outcome": {"type": "string", "maxLength": 80},
                "quality_review_id": {"type": "string"},
                "notes": {"type": "string", "maxLength": 8000},
                "token_usage": TOKEN_USAGE_SCHEMA,
            },
            "required": ["run_id", "outcome"],
            "additionalProperties": False,
        },
        contract=_local_write_contract("Finish a quality benchmark run and its execution trace"),
        handler_key="finish_quality_benchmark_run",
        order=1290,
        groups=("model_quality", "advanced_workflow", "observability"),
        exposure="catalog",
        owner="quality_observability",
    ),
    ToolSpec(
        name="start_model_quality_review",
        description=(
            "Create durable model-quality state from an actual reference brief, applicable rubric, matched evidence "
            "URIs, quality floor, and bounded repair limit."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "reference_description": {"type": "string", "maxLength": 4000},
                "reference_brief": REFERENCE_BRIEF_SCHEMA,
                "target_objects": {"type": "array", "items": {"type": "string"}, "maxItems": 100},
                "evidence_uris": {"type": "array", "items": {"type": "string"}, "maxItems": 100},
                "quality_floor": {"type": "integer", "minimum": 1, "maximum": 5},
                "max_repair_passes": {"type": "integer", "minimum": 0, "maximum": 10},
                "trace_id": {"type": "string"},
                "benchmark_run_id": {"type": "string"},
            },
            "required": ["reference_brief", "evidence_uris"],
            "additionalProperties": False,
        },
        contract=_local_write_contract("Start durable model-quality evaluation and repair state"),
        handler_key="start_model_quality_review",
        order=1300,
        groups=("model_quality", "advanced_workflow", "observability"),
        exposure="catalog",
        owner="quality_observability",
    ),
    ToolSpec(
        name="get_model_quality_review_packet",
        description=(
            "Return a scoring packet for one model-quality review. Prior scores and repairs are excluded by default "
            "so a separate evaluator can score the current evidence blindly."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "review_id": {"type": "string"},
                "include_prior_scores": {"type": "boolean"},
            },
            "required": ["review_id"],
            "additionalProperties": False,
        },
        contract=_read_contract("Read a blind or history-inclusive model-quality scoring packet"),
        handler_key="get_model_quality_review_packet",
        order=1310,
        groups=("model_quality", "advanced_workflow", "observability"),
        exposure="catalog",
        owner="quality_observability",
    ),
    ToolSpec(
        name="submit_model_quality_evaluation",
        description=(
            "Submit one complete evidence-backed 1-5 scorecard. The tool validates every applicable criterion and "
            "returns ready_for_user_review, repair_required, or blocked_quality_floor."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "review_id": {"type": "string"},
                "scores": {
                    "type": "array",
                    "items": QUALITY_SCORE_SCHEMA,
                    "minItems": 1,
                    "maxItems": 20,
                },
                "evaluator": {"type": "string", "maxLength": 240},
                "evidence_uris": {"type": "array", "items": {"type": "string"}, "maxItems": 100},
                "notes": {"type": "string", "maxLength": 4000},
                "blind": {"type": "boolean"},
            },
            "required": ["review_id", "scores"],
            "additionalProperties": False,
        },
        contract=_local_write_contract("Validate and store one model-quality scorecard"),
        handler_key="submit_model_quality_evaluation",
        order=1320,
        groups=("model_quality", "advanced_workflow", "observability"),
        exposure="catalog",
        owner="quality_observability",
    ),
    ToolSpec(
        name="record_model_quality_repair",
        description=(
            "Record one completed bounded repair pass, update evidence URIs, and return a fresh blind scoring packet. "
            "The repair limit is enforced."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "review_id": {"type": "string"},
                "repairs": {
                    "type": "array",
                    "items": QUALITY_REPAIR_SCHEMA,
                    "minItems": 1,
                    "maxItems": 20,
                },
                "evidence_uris": {"type": "array", "items": {"type": "string"}, "maxItems": 100},
                "notes": {"type": "string", "maxLength": 4000},
                "trace_id": {"type": "string"},
            },
            "required": ["review_id", "repairs", "evidence_uris"],
            "additionalProperties": False,
        },
        contract=_local_write_contract("Record a bounded model-quality repair pass"),
        handler_key="record_model_quality_repair",
        order=1330,
        groups=("model_quality", "advanced_workflow", "observability"),
        exposure="catalog",
        owner="quality_observability",
    ),
    ToolSpec(
        name="get_model_quality_review",
        description="Return a named model-quality review with score and repair history, or the latest review.",
        input_schema={
            "type": "object",
            "properties": {"review_id": {"type": "string"}},
            "additionalProperties": False,
        },
        contract=_read_contract("Read durable model-quality score and repair state"),
        handler_key="get_model_quality_review",
        order=1340,
        groups=("model_quality", "advanced_workflow", "observability"),
        exposure="catalog",
        owner="quality_observability",
    ),
)


def register(registry):
    registry.register_many(SPECS)


def register_handlers(handler_registry):
    from ...tool_handlers import quality_observability

    quality_observability.register(handler_registry, SPECS)
