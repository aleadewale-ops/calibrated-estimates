# calibrated-estimates

A Claude Code skill that makes an AI agent's time and cost estimates honest. The agent logs every estimate **before** it starts working. When the work is done, it logs how long the work actually took. Over time the skill learns how wrong the agent usually is and corrects for it.

## Why

AI agents estimate their own work badly, and almost always in the same direction. They have learned from text written by people about people's work, so they say "2–3 days" for something they finish in 20 minutes. They also forget how long model calls take. The errors are predictable, so they can be measured and corrected.

## Results so far (honest)

These numbers come from 27 tasks logged by one user on one machine (an 8 GB Apple M2) between 16 and 19 October 2026:

| | Gut feeling | With the skill |
|---|---|---|
| Median over-estimate | **2.8×** | **1.7×** |
| Estimate within ±50 % of actual | 3 of 26 | 9 of 27 |
| Cost of model runs (actual / estimate) | | 0.98 |

The skill helps, and it is **not accurate yet**. It still over-estimates. Treat this as version 0.1. More users on more machines will make it better.

## Install

Copy the folder into your skills directory:

```bash
git clone https://github.com/aleadewale-ops/calibrated-estimates ~/.claude/skills/calibrated-estimates
```

Optional: add a reminder hook, so logging does not depend on the agent remembering. Put this in `~/.claude/settings.json`:

```json
{"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "timeout": 10,
  "command": "python3 ~/.claude/skills/calibrated-estimates/scripts/opomnik.py 2>/dev/null || true"}]}]}}
```

(`opomnik` is Slovenian for "reminder".) The scripts need Python 3.9+ and nothing else.

## How it works

```bash
estimate.py suggest --kind code --gut 30        # gut feeling -> calibrated estimate with a range
estimate.py calls --n 48 --parallel 6           # model runs: count the calls, don't guess
estimate.py start --task "..." --kind code --gut 30 --estimate 6
estimate.py pause <id> / resume <id>            # waiting for the user or overnight is not counted
estimate.py end <id> [--calls 48] [--usd 1.2]
estimate.py cancel <id>                         # abandoned work is not used for calibration
estimate.py calibrate                           # correction factors per kind of work
```

- **Kinds of work:** `code` (code or text the agent writes), `model-run` (tests, batch calls, simulations), `mixed`, `human` (waiting for a person, never counted as agent time).
- **One log for all projects:** `~/.claude/estimates/log.jsonl`. Each entry records the project, RAM and CPU.
- **Your machine, your factors.** The seed data (17 tasks from the original project) is used only until you have 5 tasks of your own of a kind. After that, only your own log counts.
- **RAM matters for model runs.** A small laptop swaps when several model processes run at once, and a big machine does not. For model runs, the skill prefers entries from machines with similar RAM. Seconds per model call are measured from your own runs.

## Limitations

- All data so far comes from one user, one machine and a few days.
- Agent time depends on the model, the codebase and the task. Expect wider errors in a codebase the agent has not seen before.
- It measures wall-clock time of agent work. It cannot estimate how long a person will take.

## Contributing

If you use it, I'd love to see your `calibrate` output (factors only, no task names). Open an issue.

## License

MIT
