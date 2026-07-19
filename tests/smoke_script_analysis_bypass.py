"""Adversarial smoke test for the static script-analysis denylist.

The recent trust-gate work (commits a1196be / 0c110c6) lets external clients
auto-run staged scripts once external script trust is active, gated only by
``script_analysis.analyze_script``. That makes the static denylist the sole
barrier in the trust path, so this test pins two things:

* GUARDS  - adversarial variants the analyzer already catches. Locking these in
            prevents the hardening from regressing.
* BYPASSES - previously reachable sandbox-escape patterns. Each must remain
             blocked and ineligible for trust-window execution.

Run:  python tests/smoke_script_analysis_bypass.py
"""

from __future__ import annotations

import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon", "claude_blender"))

import script_analysis  # noqa: E402


# --- Adversarial variants the analyzer must keep rejecting (regression locks) ---
# Each guard is (source, capabilities). Note: the `filesystem` capability
# intentionally unblocks `open`/`pathlib`, so `open`-based guards run with no
# privilege. The MAX_CAPS guards assert that even a fully trusted client can
# never reach a process-spawning primitive.
MAX_CAPS = ["filesystem", "network", "project_file"]

GUARDS = {
    "direct_eval": ("eval('1+1')", []),
    "direct_exec": ("exec('x=1')", []),
    "import_os": ("import os\nos.remove('x')", []),
    "import_subprocess": ("import subprocess\nsubprocess.run(['echo', 'x'])", []),
    # __builtins__ reflection variants (already hardened, pin them):
    "subscript_eval": ("__builtins__['eval']('1+1')", []),
    "getattr_const_name_open": ("n = 'open'\ngetattr(__builtins__, n)('x', 'w')", []),
    "quit_blender_aliased": ("import bpy\nops = bpy.ops\nops.wm.quit_blender()", []),
    # Even max privilege cannot import or reach a process-spawning module:
    "privileged_import_still_blocked": ("__import__('os').system('echo nope')", MAX_CAPS),
    "privileged_subprocess_still_blocked": ("import subprocess\nsubprocess.run(['x'])", MAX_CAPS),
    "privileged_quit_still_blocked": ("import bpy\nbpy.ops.wm.quit_blender()", MAX_CAPS),
}


# --- Former bypasses that must remain blocked ---
# Keys map to the bypass classes called out in the P0 note: object-graph
# escape, computed attribute names, container indirection, and the
# sys.modules registry (sys is not in BLOCKED_MODULES).
GAPS = {
    # 1. Object-graph escape: walk type() -> __subclasses__ to reach Popen,
    #    never naming a blocked module or builtin.
    "subclasses_popen_escape": (
        "[c for c in ().__class__.__bases__[0].__subclasses__() "
        "if c.__name__ == 'Popen'][0](['echo', 'x'])"
    ),
    # 2. Function __globals__ exposes the real __builtins__ dict -> eval.
    "globals_builtins_eval": "(lambda: 0).__globals__['__builtins__']['eval']('1+1')",
    # 3. Computed attribute name (string concat) defeats constant resolution.
    "getattr_concat_open": "getattr(__builtins__, 'op' + 'en')('x', 'w')",
    # 4. Computed attribute name via str.join.
    "getattr_join_open": "getattr(__builtins__, ''.join(['o', 'p', 'e', 'n']))('x', 'w')",
    # 5. Name bound through a non-constant expression (n = n + 'en').
    "concat_name_open": "n = 'op'\nn = n + 'en'\ngetattr(__builtins__, n)('x', 'w')",
    # 6. Container indirection: callable hidden behind a list/dict literal.
    "list_container_open": "f = [open]\nf[0]('x', 'w')",
    "dict_container_open": "d = {'f': open}\nd['f']('x', 'w')",
    # 7. sys is not blocked, so the module registry hands back os.
    "sys_modules_os_system": "import sys\nsys.modules['os'].system('echo x')",
    # 8. Computed attr name reaches a project-file operator under no privilege.
    "getattr_concat_project_save": (
        "import bpy\n"
        "getattr(bpy.ops.wm, 'save_as_' + 'mainfile')(filepath='x.blend')"
    ),
    # 9. driver_namespace lets a driver expression evaluate arbitrary Python
    #    at scene-eval time, out of band from this static check.
    "driver_namespace_eval": "import bpy\nbpy.app.driver_namespace['pwn'] = eval",
}


def _check_guards():
    for name, (src, caps) in GUARDS.items():
        result = script_analysis.analyze_script(src, privileged_capabilities=caps)
        assert result["blocked"], f"GUARD regressed (now passes): {name}\n{result}"
        assert not result["trust_window_allowed"], f"GUARD would auto-run: {name}\n{result}"


def _check_gaps():
    still_open = []
    for name, src in GAPS.items():
        result = script_analysis.analyze_script(src)
        if not result["blocked"]:
            still_open.append((name, result["trust_window_allowed"]))
    if still_open:
        print(f"smoke_script_analysis_bypass: {len(still_open)} known bypass gap(s) still open:")
        for name, auto_run in still_open:
            flag = " [AUTO-RUNS under trust window]" if auto_run else ""
            print(f"  - {name}{flag}")
        raise AssertionError(f"{len(still_open)} denylist bypass(es) are reachable")
    else:
        print("smoke_script_analysis_bypass: all known bypass gaps are now closed.")


def main():
    _check_guards()
    print("smoke_script_analysis_bypass: guards ok")
    _check_gaps()
    print("smoke_script_analysis_bypass: ok")


if __name__ == "__main__":
    main()
