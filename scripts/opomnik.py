#!/usr/bin/env python3
"""UserPromptSubmit hook: a short reminder so estimates get logged before work starts, and open ones get closed.

Prints JSON with hookSpecificOutput.additionalContext (added to the model's context, not shown to the user).
Kept short on purpose: it runs on every message. Never fails the prompt: any error prints nothing and exits 0.

    echo '{}' | python3 opomnik.py          # what the model would get
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RULE = ("calibrated-estimates: before you tell the user a time or cost, log it first "
        "(scripts/estimate.py suggest/calls, then start); after the work, end it and tell the user estimate vs actual.")


def main():
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import estimate
        odprte = estimate.open_entries()
        text = RULE
        if odprte:
            text += " Open estimates (end them if done): " + "; ".join(
                f"{e['id']} '{e['task'][:50]}' since {e['start'][11:16]}" for e in odprte[:3])
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": text}}))
    except Exception:
        pass


if __name__ == "__main__":
    main()
