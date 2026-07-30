"""Run deterministic reference-modeling metric fixtures without Blender."""

from __future__ import annotations

import argparse
import json
import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import reference_benchmarks, reference_metrics  # noqa: E402


DEFAULT_MANIFEST = os.path.join(
    ROOT,
    "benchmarks",
    "reference-modeling-suite-v1.json",
)


def run_manifest(path):
    with open(path, "r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    _validate_manifest(manifest)

    results = []
    failures = []
    seen_ids = set()
    for case in manifest["cases"]:
        case_id = str(case.get("case_id") or "").strip()
        if not case_id or case_id in seen_ids:
            raise ValueError(
                "Every benchmark case needs a unique non-empty case_id"
            )
        seen_ids.add(case_id)
        width = _dimension(case.get("width"), f"{case_id}.width")
        height = _dimension(case.get("height"), f"{case_id}.height")
        reference_mask = reference_metrics.rasterize_polygon(
            case.get("reference_polygon"),
            width,
            height,
        )
        model_mask = reference_metrics.rasterize_polygon(
            case.get("model_polygon"),
            width,
            height,
        )
        metrics = reference_metrics.compare_masks(
            reference_mask,
            model_mask,
            width,
            height,
        )
        landmark_errors = reference_metrics.compare_landmarks(
            case.get("reference_landmarks"),
            case.get("model_landmarks"),
            width,
            height,
        )
        evaluation = reference_benchmarks.evaluate_comparison(
            metrics,
            landmark_errors,
            profile=case.get("profile"),
            threshold_overrides=case.get("threshold_overrides"),
        )
        expected = case.get("expected_pass")
        if not isinstance(expected, bool):
            raise ValueError(f"{case_id}.expected_pass must be boolean")
        matched = evaluation["passed"] == expected
        result = {
            "case_id": case_id,
            "expected_pass": expected,
            "passed": evaluation["passed"],
            "matched_expectation": matched,
            "quality_score": evaluation["quality_score"],
            "failed_gates": evaluation["failed_gates"],
        }
        results.append(result)
        if not matched:
            failures.append(case_id)

    return {
        "ok": not failures,
        "schema_version": manifest["schema_version"],
        "suite_version": manifest["suite_version"],
        "case_count": len(results),
        "failed_case_ids": failures,
        "results": results,
    }


def _validate_manifest(manifest):
    if not isinstance(manifest, dict):
        raise ValueError("Benchmark manifest must be a JSON object")
    if (
        manifest.get("schema_version")
        != reference_benchmarks.REFERENCE_BENCHMARK_SCHEMA_VERSION
    ):
        raise ValueError("Benchmark manifest schema_version is unsupported")
    if (
        manifest.get("suite_version")
        != reference_benchmarks.REFERENCE_BENCHMARK_SUITE_VERSION
    ):
        raise ValueError(
            "Benchmark manifest suite_version does not match the evaluator"
        )
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Benchmark manifest cases must be a non-empty list")
    if len(cases) > 100:
        raise ValueError("Benchmark manifest is limited to 100 cases")
    if not all(isinstance(case, dict) for case in cases):
        raise ValueError("Every benchmark case must be a JSON object")


def _dimension(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if not 16 <= number <= 2048:
        raise ValueError(f"{field} must be between 16 and 2048")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run offline reference-modeling benchmark fixtures.",
    )
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    args = parser.parse_args(argv)
    try:
        report = run_manifest(os.path.abspath(args.manifest))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
