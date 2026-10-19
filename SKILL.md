---
name: calibrated-estimates
description: Use whenever you are about to tell the user how long something will take or how much it will cost (your own coding, writing, test runs, batch model calls, agent runs), whenever the user asks "how long", "how much", "when will it be done", and before starting any multi-step task you announced with an estimate. Turns gut estimates into calibrated ones from logged estimate-vs-actual data, computes model-run time and cost from call counts, and logs every estimate before work starts so the factors keep improving.
---

# Calibrated estimates

AI agents estimate their own work badly, in a predictable direction. In the project this skill comes from (17 logged tasks, October 2026):

| What was estimated | Typical error |
|---|---|
| Agent work estimated in human working days ("2–3 days") | 50–360x too high |
| Agent code work estimated in minutes, from gut feeling | 2.5–10x too high (median about 5–10x) |
| Model runs (tests, batch calls, simulations) | 10–50 % too low |
| Cost of model runs | ±50 %, both directions (prompt cache) |

The reasons are stable, so they can be corrected:
1. **Human-time habit.** Estimates are learned from human-written text about human work. The agent writes code far faster than a person.
2. **Model time is forgotten.** Long runs are dominated by model latency and by things that must happen one after another (turns of a simulation), not by writing code.
3. **Cache is ignored.** Repeated runs with the same long system prompt cost a fraction of the first one.
4. **Measurement noise.** Waiting for the user, parallel subagents and crashes blur the actual time unless they are logged separately.

## Rules

1. **Never estimate agent work in human days or weeks.** Say minutes of agent work. Say separately what needs the human (decisions, review, clicking) and that you cannot estimate their time.
2. **Classify the task:** `code` (code or text you write), `model-run` (tests, batch calls, simulations), `mixed`, `human` (waiting for a person).
3. **Code and text:** write down your gut feeling first, then calibrate:
   `python3 scripts/estimate.py suggest --kind code --gut 30`
   Give the middle number and the range, not a single number.
4. **Model runs:** do not guess. Count the calls and compute:
   `python3 scripts/estimate.py calls --n 48 --sec 11.5 --parallel 6 --cache-writes 4`
   - `--sec`: median seconds per call. Leave it out once you have logged a few runs with `end --calls N`: the script then measures it from your own runs on machines with similar RAM. Long prompts, multi-step agent calls and small machines running several processes at once are slower.
   - `--rounds`: calls that must run one after another (turns of a simulated day, a conversation). These dominate time and are the most common thing forgotten.
   - `--cache-writes`: number of distinct long system prompts. The first call with each costs much more; later ones hit the cache.
5. **Log before you start, with the time:**
   `python3 scripts/estimate.py start --task "..." --kind code --gut 30 --estimate 6 [--parallel 4] [--new-codebase]` → prints an id.
   The entry records the project (the folder that holds `.claude/` or `.git`, or `--project`), RAM and CPU automatically. Model-run factors prefer entries from machines with similar RAM, because a small laptop swaps when several model processes run at once and a big machine does not.
   An estimate written after the work has started does not count. If you forgot, say so and log it as missing.
6. **Log the actual result when done:**
   `python3 scripts/estimate.py end <id> --wait 4 --usd 1.2 [--calls 48] --note "..."`
   `--wait` excludes minutes spent waiting for the user; `--calls` records how many model calls a run made, so seconds per call can be measured. Note anything that broke the estimate (a crash, a scope change, parallel work).
   - When the work stops for a while (waiting for the user, overnight), `pause <id>` and later `resume <id>`: paused time is not counted.
   - When a task is abandoned or replaced, `cancel <id> --note "..."`: it stays in the log but does not affect calibration.
7. **Tell the user** both numbers at the end: estimated vs actual, and why they differed if they did.
8. **Recalibrate every 10 new entries:** `python3 scripts/estimate.py calibrate`. Until a kind has 5 of your own entries, your entries are combined with the seed data from the original project; from then on only your own entries count for that kind. `--no-seed` drops the seed entirely.

## What the seed data does not cover

The seed (`data/seed.jsonl`) is one project, one day, one machine (an 8 GB Apple M2), mostly small changes to a codebase the agent already knew well. Model runs on a bigger machine will be faster than the seed suggests. Expect slower work for: a new codebase, unfamiliar libraries, debugging something you cannot reproduce, and anything that needs the user's decisions in the middle. Widen the range in those cases and say why.

## Files

- `scripts/estimate.py`: suggest, calls, start, pause, resume, cancel, end, open, calibrate, list. Log: `$ESTIMATES_LOG` or `~/.claude/estimates/log.jsonl`, one log across all projects so every project teaches the factors.
- `scripts/opomnik.py`: reminder hook. Add it as a `UserPromptSubmit` hook so logging does not depend on remembering:
  ```json
  {"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "timeout": 10,
    "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/skills/calibrated-estimates/scripts/opomnik.py\" 2>/dev/null || true"}]}]}}
  ```
  It adds one line to the context on every message, plus any estimates that were started and not ended.
- `data/seed.jsonl`: 17 tasks with estimate and actual from the original project.
- `references/method.md`: how the factors are computed and what to collect for better calibration.
