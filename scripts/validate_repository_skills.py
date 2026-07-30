#!/usr/bin/env python3
"""Validate the repository's MCP-client-neutral skill metadata."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = ROOT / "skills"
MAX_SKILL_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
NAME_PATTERN = re.compile(r"^[a-z0-9-]+$")
FRONTMATTER_PATTERN = re.compile(
    r"\A---\r?\n(?P<frontmatter>.*?)\r?\n---(?:\r?\n|\Z)",
    flags=re.DOTALL,
)


def _parse_scalar(value: str, line_number: int) -> str:
    value = value.strip()
    if not value:
        return ""
    if value.startswith('"'):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"frontmatter line {line_number} has an invalid quoted value"
            ) from exc
        if not isinstance(parsed, str):
            raise ValueError(
                f"frontmatter line {line_number} must contain a string value"
            )
        return parsed
    if value.startswith("'"):
        if len(value) < 2 or not value.endswith("'"):
            raise ValueError(
                f"frontmatter line {line_number} has an invalid quoted value"
            )
        return value[1:-1].replace("''", "'")
    return value


def _parse_frontmatter(content: str) -> dict[str, str]:
    match = FRONTMATTER_PATTERN.match(content)
    if not match:
        raise ValueError("SKILL.md must start with a YAML frontmatter block")

    frontmatter: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        match.group("frontmatter").splitlines(), start=2
    ):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if raw_line[:1].isspace() or ":" not in raw_line:
            raise ValueError(
                f"frontmatter line {line_number} must be a top-level key/value pair"
            )
        key, raw_value = raw_line.split(":", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"frontmatter line {line_number} has an empty key")
        if key in frontmatter:
            raise ValueError(f"frontmatter key '{key}' is duplicated")
        frontmatter[key] = _parse_scalar(raw_value, line_number)
    return frontmatter


def validate_skill(skill_path: Path) -> list[str]:
    skill_path = skill_path.resolve()
    skill_file = skill_path if skill_path.is_file() else skill_path / "SKILL.md"
    skill_dir = skill_file.parent
    if not skill_file.is_file():
        return ["SKILL.md not found"]

    try:
        content = skill_file.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"could not read SKILL.md as UTF-8: {exc}"]

    try:
        frontmatter = _parse_frontmatter(content)
    except ValueError as exc:
        return [str(exc)]

    errors: list[str] = []
    expected_keys = {"name", "description"}
    missing_keys = expected_keys - frontmatter.keys()
    unexpected_keys = frontmatter.keys() - expected_keys
    if missing_keys:
        errors.append(f"missing frontmatter key(s): {', '.join(sorted(missing_keys))}")
    if unexpected_keys:
        errors.append(
            f"unexpected frontmatter key(s): {', '.join(sorted(unexpected_keys))}"
        )

    name = frontmatter.get("name", "").strip()
    if not name:
        errors.append("name must not be empty")
    else:
        if not NAME_PATTERN.fullmatch(name):
            errors.append(
                "name must use lowercase letters, digits, and single hyphens only"
            )
        if name.startswith("-") or name.endswith("-") or "--" in name:
            errors.append(
                "name cannot start or end with a hyphen or contain consecutive hyphens"
            )
        if len(name) > MAX_SKILL_NAME_LENGTH:
            errors.append(
                f"name exceeds the {MAX_SKILL_NAME_LENGTH}-character limit"
            )
        if name != skill_dir.name:
            errors.append(
                f"name '{name}' does not match skill directory '{skill_dir.name}'"
            )

    description = frontmatter.get("description", "").strip()
    if not description:
        errors.append("description must not be empty")
    else:
        if "<" in description or ">" in description:
            errors.append("description cannot contain angle brackets")
        if len(description) > MAX_DESCRIPTION_LENGTH:
            errors.append(
                f"description exceeds the {MAX_DESCRIPTION_LENGTH}-character limit"
            )
    return errors


def _default_skill_paths() -> list[Path]:
    return sorted(
        path
        for path in SKILLS_ROOT.iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate repository skill frontmatter without client-specific tooling."
    )
    parser.add_argument(
        "skill_paths",
        nargs="*",
        type=Path,
        help="Skill directories or SKILL.md files. Defaults to every repository skill.",
    )
    args = parser.parse_args(argv)
    skill_paths = args.skill_paths or _default_skill_paths()
    if not skill_paths:
        print("No repository skills found.", file=sys.stderr)
        return 1

    failed = False
    for skill_path in skill_paths:
        errors = validate_skill(skill_path)
        display_path = str(skill_path)
        if errors:
            failed = True
            for error in errors:
                print(f"[FAIL] {display_path}: {error}", file=sys.stderr)
        else:
            print(f"[OK] {display_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
