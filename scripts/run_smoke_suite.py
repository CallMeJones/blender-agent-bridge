"""Run the checked smoke manifest locally or in CI with the same selection rules."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests" / "smoke_manifest.json"
sys.path.insert(0, str(ROOT / "addon"))
from claude_blender import process_utils


def load_manifest():
    rows = json.loads(MANIFEST.read_text(encoding="utf-8"))["tests"]
    paths = [row["file"] for row in rows]
    actual = {path.relative_to(ROOT).as_posix() for path in (ROOT / "tests").glob("smoke_*.py")}
    if len(paths) != len(set(paths)) or set(paths) != actual:
        raise ValueError(f"Smoke inventory mismatch: missing={actual - set(paths)}, stale={set(paths) - actual}")
    for row in rows:
        if row["environment"] not in {"python", "blender"} or not row["lanes"]:
            raise ValueError(f"Missing environment/lane: {row['name']}")
        if not {"core", "release"}.intersection(row["lanes"]) and not row.get("reason"):
            raise ValueError(f"Missing deterministic-suite exclusion reason: {row['name']}")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane", default="release", choices=["core", "release", "artifacts", "live", "fixture", "publication"])
    parser.add_argument("--environment", choices=["python", "blender"])
    parser.add_argument("--blender", default=os.environ.get("BLENDER_EXECUTABLE") or shutil.which("blender"))
    parser.add_argument("--test", action="append", default=[])
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--log-dir", default=".dev-session/smoke-results")
    parser.add_argument("test_args", nargs=argparse.REMAINDER, help="Arguments after -- for an explicitly selected fixture/publication test")
    args = parser.parse_args()
    rows = [row for row in load_manifest() if args.lane in row["lanes"]
            and (not args.environment or row["environment"] == args.environment)
            and (not args.test or row["name"] in args.test)]
    if not rows:
        parser.error("No smoke tests match this selection")
    if args.test_args and len(rows) != 1:
        parser.error("Test arguments require exactly one selected test")
    if args.list:
        for row in rows:
            print(f"{row['name']} ({row['environment']}, {row['timeout_seconds']}s)")
        return 0
    if any(row["environment"] == "blender" for row in rows) and not args.blender:
        parser.error("Blender tests require --blender or BLENDER_EXECUTABLE")
    log_dir = ROOT / args.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    failures = []
    for row in rows:
        command = ([args.blender, "--background", "--factory-startup", "--python-exit-code", "1", "--python"]
                   if row["environment"] == "blender" else [sys.executable]) + [str(ROOT / row["file"])]
        extra = args.test_args[1:] if args.test_args[:1] == ["--"] else args.test_args
        if extra:
            command += (["--"] if row["environment"] == "blender" else []) + extra
        print(f"RUN {row['name']}", flush=True)
        with subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, encoding="utf-8", errors="replace",
                              **process_utils.process_group_kwargs()) as process:
            try:
                output, _ = process.communicate(timeout=row["timeout_seconds"])
                passed = process.returncode == 0 and row["success"] in output
            except subprocess.TimeoutExpired:
                process_utils.terminate_process_tree(process)
                output, _ = process.communicate(timeout=10)
                output = f"Timed out after {row['timeout_seconds']}s\n" + output
                passed = False
        (log_dir / (row["name"] + ".log")).write_text(output, encoding="utf-8")
        print(f"{'PASS' if passed else 'FAIL'} {row['name']}", flush=True)
        if not passed:
            failures.append(row["name"])
            print(output[-6000:], flush=True)
    print(f"{len(rows) - len(failures)}/{len(rows)} smoke tests passed", flush=True)
    return bool(failures)


if __name__ == "__main__":
    sys.exit(main())
