"""Durable score, repair, and completion state for reference-model reviews."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import time
import uuid

from . import user_paths


REVIEW_SCHEMA_VERSION = 1
LATEST_REVIEW_RESOURCE_URI = "blender://model-quality-reviews/latest"
VALID_STATUSES = {
    "awaiting_evaluation",
    "repair_required",
    "ready_for_user_review",
    "blocked_quality_floor",
}


def _now_iso():
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="milliseconds")


def _root(create=False):
    path = user_paths.user_data_path("model-quality-reviews")
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def _safe_id(value, fallback="review"):
    safe = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in str(value or ""))
    return safe.strip("._")[:100] or fallback


def _review_id():
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:10]}"


def _path(review_id):
    return os.path.join(_root(), f"{_safe_id(review_id, '')}.json")


def _write(review):
    path = _path(review["review_id"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(review, handle, indent=2, sort_keys=True, ensure_ascii=True)
    os.replace(temp_path, path)
    return review


def _read(review_id):
    try:
        with open(_path(review_id), "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _bounded_strings(values, *, max_items=64, max_chars=1000):
    result = []
    seen = set()
    for raw in values if isinstance(values, (list, tuple)) else []:
        value = str(raw or "").strip()[:max_chars]
        if value and value not in seen:
            result.append(value)
            seen.add(value)
        if len(result) >= max_items:
            break
    return result


def _digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _public_summary(review):
    evaluations = list(review.get("evaluations") or [])
    latest = evaluations[-1] if evaluations else {}
    return {
        "ok": True,
        "available": True,
        "review_id": review.get("review_id", ""),
        "status": review.get("status", ""),
        "subject": (review.get("reference_brief") or {}).get("subject", "model"),
        "quality_floor": review.get("quality_floor", 4),
        "max_repair_passes": review.get("max_repair_passes", 3),
        "repair_pass_count": len(review.get("repairs") or []),
        "evaluation_count": len(evaluations),
        "failed_criteria": list(latest.get("failed_criteria") or []),
        "minimum_score": latest.get("minimum_score"),
        "average_score": latest.get("average_score"),
        "ready_for_user_review": review.get("status") == "ready_for_user_review",
        "blocked": review.get("status") == "blocked_quality_floor",
        "updated_at": review.get("updated_at", ""),
        "created_at": review.get("created_at", ""),
        "benchmark_run_id": review.get("benchmark_run_id", ""),
        "trace_id": review.get("trace_id", ""),
        "review_uri": f"blender://model-quality-reviews/{review.get('review_id', '')}",
        "latest_review_uri": LATEST_REVIEW_RESOURCE_URI,
    }


def create_review(
    *,
    reference_brief,
    rubric,
    target_objects=None,
    evidence_uris=None,
    quality_floor=4,
    max_repair_passes=3,
    trace_id="",
    benchmark_run_id="",
    review_id="",
):
    brief = dict(reference_brief or {}) if isinstance(reference_brief, dict) else {}
    criteria = []
    seen = set()
    for item in rubric if isinstance(rubric, (list, tuple)) else []:
        if not isinstance(item, dict) or not item.get("applies", True):
            continue
        criterion = str(item.get("criterion") or "").strip()
        if not criterion or criterion in seen:
            continue
        seen.add(criterion)
        criteria.append(
            {
                "criterion": criterion[:120],
                "target": str(item.get("target") or "")[:2000],
                "repair_action": str(item.get("repair_action") or "")[:2000],
                "evidence_from_brief": _bounded_strings(item.get("evidence_from_brief"), max_chars=500),
                "applies": True,
            }
        )
    if not criteria:
        return {
            "ok": False,
            "code": "quality_rubric_required",
            "message": "At least one applicable quality criterion is required",
        }
    review_id = _safe_id(review_id or _review_id())
    if os.path.exists(_path(review_id)):
        return {
            "ok": False,
            "code": "quality_review_exists",
            "message": f"Model quality review already exists: {review_id}",
        }
    floor = max(1, min(5, int(quality_floor or 4)))
    max_repairs = max(
        0,
        min(10, int(3 if max_repair_passes is None else max_repair_passes)),
    )
    now = _now_iso()
    review = {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "review_id": review_id,
        "status": "awaiting_evaluation",
        "created_at": now,
        "updated_at": now,
        "reference_brief": brief,
        "reference_brief_digest": _digest(brief),
        "rubric": criteria,
        "rubric_digest": _digest(criteria),
        "target_objects": _bounded_strings(target_objects, max_items=100, max_chars=240),
        "evidence_uris": _bounded_strings(evidence_uris, max_items=100, max_chars=1000),
        "quality_floor": floor,
        "max_repair_passes": max_repairs,
        "trace_id": str(trace_id or "")[:120],
        "benchmark_run_id": str(benchmark_run_id or "")[:120],
        "evaluations": [],
        "repairs": [],
    }
    _write(review)
    return {
        "ok": True,
        "message": "Model quality review started",
        "review": _public_summary(review),
        "packet": review_packet(review_id, include_prior_scores=False),
    }


def get_review(review_id):
    review = _read(review_id)
    if not review:
        return {
            "ok": False,
            "available": False,
            "review_id": str(review_id or ""),
            "message": "Model quality review was not found",
        }
    return {"ok": True, "available": True, "review": review, "summary": _public_summary(review)}


def review_packet(review_id, *, include_prior_scores=False):
    review = _read(review_id)
    if not review:
        return {
            "ok": False,
            "available": False,
            "review_id": str(review_id or ""),
            "message": "Model quality review was not found",
        }
    packet = {
        "review_id": review["review_id"],
        "status": review["status"],
        "reference_brief": review["reference_brief"],
        "rubric": review["rubric"],
        "target_objects": review["target_objects"],
        "evidence_uris": review["evidence_uris"],
        "quality_floor": review["quality_floor"],
        "repair_pass_count": len(review.get("repairs") or []),
        "max_repair_passes": review["max_repair_passes"],
        "required_score_fields": ["criterion", "score", "evidence", "finding", "repair_action"],
        "score_scale": {"minimum": 1, "maximum": 5},
        "blind_packet": not bool(include_prior_scores),
        "scoring_instruction": (
            "Score only the supplied evidence against the reference brief. Do not infer hidden form, use category "
            "templates, or raise a score because of effort. Cite evidence for every score."
        ),
    }
    if include_prior_scores:
        packet["prior_evaluations"] = list(review.get("evaluations") or [])
        packet["repairs"] = list(review.get("repairs") or [])
    packet["packet_digest"] = _digest(packet)
    return {"ok": True, "available": True, "message": "Model quality review packet ready", "packet": packet}


def _normalize_scores(review, scores):
    rubric_names = [item["criterion"] for item in review.get("rubric") or []]
    by_name = {}
    errors = []
    for index, raw in enumerate(scores if isinstance(scores, (list, tuple)) else []):
        if not isinstance(raw, dict):
            errors.append(f"scores[{index}] must be an object")
            continue
        criterion = str(raw.get("criterion") or "").strip()
        if criterion not in rubric_names:
            errors.append(f"scores[{index}].criterion is not applicable: {criterion or '(empty)'}")
            continue
        if criterion in by_name:
            errors.append(f"Duplicate criterion: {criterion}")
            continue
        try:
            score = int(raw.get("score"))
        except (TypeError, ValueError):
            score = 0
        if score < 1 or score > 5:
            errors.append(f"{criterion}.score must be between 1 and 5")
        evidence = _bounded_strings(raw.get("evidence"), max_items=20, max_chars=1000)
        finding = str(raw.get("finding") or "").strip()[:2000]
        repair_action = str(raw.get("repair_action") or "").strip()[:2000]
        if not evidence:
            errors.append(f"{criterion}.evidence is required")
        if not finding:
            errors.append(f"{criterion}.finding is required")
        if not repair_action:
            errors.append(f"{criterion}.repair_action is required")
        by_name[criterion] = {
            "criterion": criterion,
            "score": score,
            "evidence": evidence,
            "finding": finding,
            "repair_action": repair_action,
        }
    missing = [criterion for criterion in rubric_names if criterion not in by_name]
    if missing:
        errors.append(f"Missing applicable criteria: {', '.join(missing)}")
    return [by_name[name] for name in rubric_names if name in by_name], errors


def submit_evaluation(
    review_id,
    *,
    scores,
    evaluator="",
    evidence_uris=None,
    notes="",
    blind=True,
):
    review = _read(review_id)
    if not review:
        return {
            "ok": False,
            "available": False,
            "review_id": str(review_id or ""),
            "message": "Model quality review was not found",
        }
    if review.get("status") not in {"awaiting_evaluation", "repair_required"}:
        return {
            "ok": False,
            "code": "quality_review_not_awaiting_evaluation",
            "message": f"Review cannot accept scores while status is {review.get('status')}",
            "review": _public_summary(review),
        }
    if review.get("status") == "repair_required":
        return {
            "ok": False,
            "code": "quality_repair_must_be_recorded",
            "message": "Record the completed repair pass before submitting another evaluation",
            "review": _public_summary(review),
        }
    normalized, errors = _normalize_scores(review, scores)
    if errors:
        return {
            "ok": False,
            "code": "invalid_quality_scorecard",
            "message": "Quality scorecard is incomplete or invalid",
            "errors": errors,
        }
    supplied_evidence = _bounded_strings(evidence_uris, max_items=100, max_chars=1000)
    if supplied_evidence:
        review["evidence_uris"] = supplied_evidence
    floor = int(review.get("quality_floor") or 4)
    failed = [item["criterion"] for item in normalized if item["score"] < floor]
    scores_only = [item["score"] for item in normalized]
    repairs_used = len(review.get("repairs") or [])
    if failed and repairs_used >= int(review.get("max_repair_passes") or 0):
        status = "blocked_quality_floor"
    elif failed:
        status = "repair_required"
    else:
        status = "ready_for_user_review"
    evaluation = {
        "evaluation_index": len(review.get("evaluations") or []) + 1,
        "submitted_at": _now_iso(),
        "evaluator": str(evaluator or "")[:240],
        "blind": bool(blind),
        "notes": str(notes or "")[:4000],
        "scores": normalized,
        "failed_criteria": failed,
        "minimum_score": min(scores_only),
        "average_score": round(sum(scores_only) / len(scores_only), 3),
        "repair_pass_count": repairs_used,
        "evidence_uris": list(review.get("evidence_uris") or []),
    }
    review.setdefault("evaluations", []).append(evaluation)
    review["status"] = status
    review["updated_at"] = _now_iso()
    _write(review)
    repair_queue = [
        item
        for item in normalized
        if item["criterion"] in failed
    ]
    return {
        "ok": True,
        "message": (
            "Quality floor met; preview is ready for explicit user review"
            if status == "ready_for_user_review"
            else (
                "Quality floor was not met within the repair-pass limit"
                if status == "blocked_quality_floor"
                else "Repair is required before another evaluation"
            )
        ),
        "review": _public_summary(review),
        "evaluation": evaluation,
        "repair_queue": repair_queue,
        "commit_allowed": status == "ready_for_user_review",
        "must_leave_preview_pending": True,
    }


def record_repair(
    review_id,
    *,
    repairs,
    evidence_uris=None,
    notes="",
    trace_id="",
):
    review = _read(review_id)
    if not review:
        return {
            "ok": False,
            "available": False,
            "review_id": str(review_id or ""),
            "message": "Model quality review was not found",
        }
    if review.get("status") != "repair_required":
        return {
            "ok": False,
            "code": "quality_repair_not_expected",
            "message": f"Review does not accept a repair while status is {review.get('status')}",
            "review": _public_summary(review),
        }
    used = len(review.get("repairs") or [])
    maximum = int(review.get("max_repair_passes") or 0)
    if used >= maximum:
        review["status"] = "blocked_quality_floor"
        review["updated_at"] = _now_iso()
        _write(review)
        return {
            "ok": False,
            "code": "quality_repair_limit_reached",
            "message": "The bounded repair-pass limit has been reached",
            "review": _public_summary(review),
        }
    normalized_repairs = []
    latest_evaluation = (review.get("evaluations") or [])[-1]
    failed_criteria = set(latest_evaluation.get("failed_criteria") or [])
    for raw in repairs if isinstance(repairs, (list, tuple)) else []:
        if not isinstance(raw, dict):
            continue
        criterion = str(raw.get("criterion") or "").strip()
        action = str(raw.get("action") or "").strip()[:2000]
        if criterion in failed_criteria and action:
            normalized_repairs.append(
                {
                    "criterion": criterion,
                    "action": action,
                    "result": str(raw.get("result") or "")[:2000],
                }
            )
    if not normalized_repairs:
        return {
            "ok": False,
            "code": "quality_repairs_required",
            "message": "At least one repair action for a currently failed criterion is required",
        }
    supplied_evidence = _bounded_strings(evidence_uris, max_items=100, max_chars=1000)
    if not supplied_evidence:
        return {
            "ok": False,
            "code": "quality_repair_evidence_required",
            "message": "Recaptured evidence URIs are required for every recorded repair pass",
        }
    review["evidence_uris"] = supplied_evidence
    repair = {
        "repair_pass": used + 1,
        "recorded_at": _now_iso(),
        "repairs": normalized_repairs,
        "notes": str(notes or "")[:4000],
        "trace_id": str(trace_id or "")[:120],
        "evidence_uris": list(review.get("evidence_uris") or []),
    }
    review.setdefault("repairs", []).append(repair)
    review["status"] = "awaiting_evaluation"
    review["updated_at"] = _now_iso()
    _write(review)
    return {
        "ok": True,
        "message": "Repair pass recorded; recapture matched evidence and submit a blind evaluation",
        "review": _public_summary(review),
        "repair": repair,
        "next_packet": review_packet(review_id, include_prior_scores=False)["packet"],
    }


def list_reviews(limit=20):
    root = _root()
    if not os.path.isdir(root):
        return []
    rows = []
    for name in os.listdir(root):
        if not name.endswith(".json"):
            continue
        review = _read(name[:-5])
        if review:
            rows.append(_public_summary(review))
    rows.sort(key=lambda row: row.get("updated_at", ""), reverse=True)
    return rows[: max(1, min(100, int(limit or 20)))]


def latest_review():
    rows = list_reviews(1)
    return get_review(rows[0]["review_id"]) if rows else {
        "ok": False,
        "available": False,
        "message": "No model quality reviews are available",
    }


def parse_review_resource_uri(uri):
    parts = str(uri or "").split("/")
    if len(parts) == 4 and parts[:3] == ["blender:", "", "model-quality-reviews"]:
        return parts[3]
    return ""


def register():
    pass


def unregister():
    pass
