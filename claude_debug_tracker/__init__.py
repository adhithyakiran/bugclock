"""
bugclock
====================
Track the time your team spends debugging Claude-generated code.

Quickstart:
    pip install bugclock
    bugclock init          # set up in your repo (installs git hooks)
    bugclock start         # begin a debug session
    bugclock stop          # end the session and record time
    bugclock report        # see your analytics
"""

__version__ = "0.1.0"
__all__ = ["tracker", "detector", "reporter", "storage"]
