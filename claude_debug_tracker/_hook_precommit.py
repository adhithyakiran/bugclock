"""
Pre-commit hook: warn if Claude-generated files are being modified
while there is no active debug session recorded.
"""

import subprocess
import sys

from .detector import is_claude_generated
from .tracker import get_active_session


def main():
    try:
        staged = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=M"],
            text=True, stderr=subprocess.DEVNULL,
        ).splitlines()
    except Exception:
        return

    claude_staged = [f for f in staged if is_claude_generated(f)]
    if not claude_staged:
        return

    active = get_active_session()
    if active:
        return  # session already open — all good

    # Print to stderr so it doesn't pollute git output
    print(
        "\n[bugclock] Modifying Claude-generated files:\n"
        + "\n".join(f"  {f}" for f in claude_staged)
        + "\nNo active debug session found. "
        "Run 'bugclock start' before debugging, or the post-commit "
        "hook will try to auto-infer the session.\n",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
