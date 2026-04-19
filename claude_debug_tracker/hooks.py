"""
Generate and install git hooks that enable auto-inference of debug sessions.

post-commit hook logic:
  1. Get files changed in the latest commit
  2. Check if any are Claude-generated
  3. If commit message contains fix/debug keywords → auto-record a session
     using file modification timestamps to estimate duration
"""

import os
import stat
import subprocess
from pathlib import Path

_HOOKS_DIR = Path(".git/hooks")

# ── Hook scripts ──────────────────────────────────────────────────────────────

_PRE_COMMIT = """\
#!/bin/sh
# bugclock: warn if fixing Claude-generated files with no active session
python -m claude_debug_tracker._hook_precommit 2>/dev/null || true
"""

_POST_COMMIT = """\
#!/bin/sh
# bugclock: auto-infer debug session from fix commits
python -m claude_debug_tracker._hook_postcommit 2>/dev/null || true
"""


# ── Install / uninstall ───────────────────────────────────────────────────────

def install(verbose: bool = True) -> bool:
    if not _HOOKS_DIR.exists():
        if verbose:
            print("  [warn] .git/hooks not found — is this a git repo?")
        return False

    _write_hook("pre-commit", _PRE_COMMIT)
    _write_hook("post-commit", _POST_COMMIT)

    if verbose:
        print("  ✓ Git hooks installed (pre-commit, post-commit)")
    return True


def uninstall(verbose: bool = True):
    for name in ("pre-commit", "post-commit"):
        hook_path = _HOOKS_DIR / name
        if hook_path.exists():
            content = hook_path.read_text()
            if "bugclock" in content:
                hook_path.unlink()
                if verbose:
                    print(f"  ✓ Removed {name} hook")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_hook(name: str, content: str):
    hook_path = _HOOKS_DIR / name

    if hook_path.exists():
        existing = hook_path.read_text()
        # Append only if our marker isn't already present
        if "bugclock" not in existing:
            hook_path.write_text(existing.rstrip() + "\n\n" + content)
    else:
        hook_path.write_text(content)

    # Ensure executable
    current = hook_path.stat().st_mode
    hook_path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
