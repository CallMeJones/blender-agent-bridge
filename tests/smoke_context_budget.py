"""Pure-Python smoke tests for prompt-budget hard caps (run with plain python)."""

from __future__ import annotations

import json
import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon", "claude_blender"))

import context_budget  # noqa: E402


def test_truncate_text_never_exceeds_budget():
    sample = "x" * 500
    for budget in [0, 1, 5, 14, 15, 16, 40, 499, 500, 501, 10_000]:
        result = context_budget.truncate_text(sample, budget)
        assert len(result) <= max(0, budget), (budget, len(result))
    # Non-string inputs are coerced and still capped.
    assert len(context_budget.truncate_text(123456789, 3)) <= 3
    # Text already within budget is returned unchanged.
    assert context_budget.truncate_text("hi", 100) == "hi"


def test_dumps_json_for_prompt_respects_hard_cap():
    big = {"items": [{"name": f"object_{i}", "blob": "y" * 2_000} for i in range(400)]}
    for budget in [5, 50, 200, 2_000, 20_000]:
        text = context_budget.dumps_json_for_prompt(big, max_chars=budget)
        assert len(text) <= budget, (budget, len(text))
    # A comfortably large budget must still yield parseable JSON.
    text = context_budget.dumps_json_for_prompt(big, max_chars=120_000)
    json.loads(text)


def main():
    test_truncate_text_never_exceeds_budget()
    test_dumps_json_for_prompt_respects_hard_cap()
    print("smoke_context_budget: ok")


if __name__ == "__main__":
    main()
