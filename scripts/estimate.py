#!/usr/bin/env python3
"""Calibrated estimates: log every time/cost estimate before starting, log the actual result, and learn correction factors.

Log file: $ESTIMATES_LOG, else ~/.claude/estimates/log.jsonl (one log across all projects, so calibration learns from all
work; each entry records the project, RAM, CPU and parallelism). A project-local ./.estimates/log.jsonl from v1 is merged in
automatically. Seed data from the original project (one 8 GB Mac) lives in ../data/seed.jsonl and is used for a kind only
until you have MIN_N entries of your own of that kind (use --no-seed to exclude it). Model runs depend on the machine, so
for model-run entries from machines with similar RAM count first, and `calls` measures seconds per call from your own log.

    estimate.py suggest --kind code --gut 30                 # calibrated estimate from a gut feeling (minutes)
    estimate.py calls --n 48 --sec 11.5 --parallel 6 --first 25 --usd 0.05 --cache-writes 4 --cache-usd 0.8
    estimate.py start --task "add export command" --kind code --gut 30 --estimate 10 [--usd 0] [--parallel 4] [--new-codebase]
    estimate.py open                                         # estimates started but not ended (the reminder hook shows these)
    estimate.py pause <id> / resume <id>                     # stop the clock while waiting for the user or overnight
    estimate.py cancel <id> [--note "..."]                   # abandoned task: kept in the log, excluded from calibration
    estimate.py end <id> [--wait 5] [--usd 1.2] [--calls 12] [--note "..."]
    estimate.py calibrate [--no-seed]                        # factors per kind
    estimate.py list [--last 10]

Kinds: code (writing/changing code or text the agent produces itself), model-run (tests, batch LLM calls, simulations:
time is dominated by model latency), mixed, human (waiting for a person; never estimate this as agent time).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import statistics as st
import sys
import uuid
from pathlib import Path

SEED = Path(__file__).resolve().parent.parent / "data" / "seed.jsonl"
KINDS = ("code", "model-run", "mixed", "human")
# Starting factors (estimate / actual) until calibration has >= MIN_N entries of a kind (from seed.jsonl, 16. 10. 2026).
DEFAULT_FACTOR = {"code": 5.0, "model-run": 0.9, "mixed": 3.5, "human": 1.0}
MIN_N = 5
DEFAULT_SEC = 11.5   # seconds per model call in the original project; replaced by your own measurement once logged


def project() -> str:
    """Project name: the folder that holds .claude/ or .git, so running a script from a subfolder does not log 'scripts'."""
    if os.environ.get("ESTIMATES_PROJECT"):
        return os.environ["ESTIMATES_PROJECT"]
    here = Path.cwd().resolve()
    for d in (here, *here.parents):
        if d.name == ".claude":
            return d.parent.name
        if (d / ".git").exists() or (d / ".claude").is_dir() and d != Path.home():
            return d.name
    return here.name


def similar_ram(e: dict, ram) -> bool:
    """Same machine class: RAM within a factor of 2 (8 vs 16 GB similar, 8 vs 64 GB not). Unknown RAM counts as similar."""
    r = e.get("ram_gb")
    return not ram or not r or 0.5 <= r / ram <= 2


def log_path() -> Path:
    p = Path(os.environ.get("ESTIMATES_LOG") or Path.home() / ".claude" / "estimates" / "log.jsonl")
    p.parent.mkdir(parents=True, exist_ok=True)
    legacy = Path.cwd() / ".estimates" / "log.jsonl"   # v1 kept a log per project: merge it once into the shared log
    if legacy.exists() and legacy.resolve() != p.resolve():
        have = {e.get("id") for e in read(p)}
        new = [e for e in read(legacy) if e.get("id") not in have]
        if new:
            with p.open("a", encoding="utf-8") as f:
                f.writelines(json.dumps(dict(e, project=e.get("project") or Path.cwd().name), ensure_ascii=False) + "\n" for e in new)
        legacy.rename(legacy.with_suffix(".merged"))
    return p


def machine() -> dict:
    """Circumstances that change how long model runs take: RAM (parallel CLI processes swap on small machines) and CPU."""
    info = {"os": sys.platform}
    try:
        import subprocess
        if sys.platform == "darwin":
            info["ram_gb"] = round(int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout) / 2**30)
            info["cpu"] = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout.strip()
        elif Path("/proc/meminfo").exists():
            kb = int(Path("/proc/meminfo").read_text().split("MemTotal:")[1].split()[0])
            info["ram_gb"] = round(kb / 2**20)
            info["cpu_count"] = os.cpu_count()
        else:
            info["cpu_count"] = os.cpu_count()
    except Exception:
        pass
    return info


def read(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.exists() else []


def entries(seed: bool = True) -> list[dict]:
    own = [e for e in read(log_path()) if e.get("actual_min") and not e.get("cancelled")]
    return own + ([{"ram_gb": 8, **e, "seed": True} for e in read(SEED)] if seed else [])   # seed: one 8 GB Apple M2


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def quantile(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    i = (len(xs) - 1) * q
    lo, hi = int(i), min(int(i) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)


def factors(seed: bool = True) -> dict[str, dict]:
    """Per kind: ratio = what was estimated (gut if logged, else estimate) / actual. >1 means over-estimate.

    Seed entries count only while you have fewer than MIN_N of your own of that kind. For model-run, entries from
    machines with similar RAM are used when there are MIN_N of them (a small laptop swaps, a big machine does not)."""
    out, ram = {}, machine().get("ram_gb")
    every = entries(seed)
    for k in KINDS:
        rows = [e for e in every if e.get("kind") == k and (e.get("gut_min") or e.get("estimate_min")) and e.get("actual_min")]
        own = [e for e in rows if not e.get("seed")]
        rows, source = (own, "your data") if len(own) >= MIN_N else (rows, f"your {len(own)} + seed")
        if k == "model-run" and ram:
            alike = [e for e in rows if similar_ram(e, ram)]
            if len(alike) >= MIN_N and len(alike) < len(rows):
                rows, source = alike, source + f", machines with ~{ram} GB RAM"
            elif len(alike) < MIN_N:
                source += f"; only {len(alike)} from machines like yours ({ram} GB RAM), so expect a different speed"
        r = [(e.get("gut_min") or e["estimate_min"]) / e["actual_min"] for e in rows]
        if len(r) >= MIN_N:
            out[k] = {"n": len(r), "median": st.median(r), "p20": quantile(r, 0.2), "p80": quantile(r, 0.8), "source": source}
        else:
            out[k] = {"n": len(r), "median": DEFAULT_FACTOR[k], "p20": DEFAULT_FACTOR[k] * 0.5, "p80": DEFAULT_FACTOR[k] * 2,
                      "source": f"default (only {len(r)} entries, need {MIN_N})"}
    return out


def cmd_suggest(a):
    f = factors(not a.no_seed)[a.kind]
    mid = a.gut / f["median"]
    # never narrower than x0.6 .. x2 around the middle: small samples look more certain than they are
    fast, slow = min(a.gut / f["p80"], mid * 0.6), max(a.gut / f["p20"], mid * 2)
    print(f"{a.kind}: gut {a.gut:g} min -> estimate {mid:.0f} min (likely range {fast:.0f}-{slow:.0f} min); "
          f"factor {f['median']:.1f} from {f['n']} entries, {f['source']}")
    if a.kind == "model-run":
        print("For model runs prefer `calls`: count the calls instead of guessing.")


def measured_sec() -> tuple[float, str]:
    """Median seconds per call from your own ended model runs (logged with --calls) on machines with similar RAM."""
    ram = machine().get("ram_gb")
    own = [e for e in entries(False) if e.get("calls") and e.get("kind") == "model-run" and similar_ram(e, ram)]
    if len(own) >= 3:
        return st.median(e["actual_min"] * 60 * (e.get("parallel") or 1) / e["calls"] for e in own), f"measured from {len(own)} of your runs"
    return DEFAULT_SEC, f"default {DEFAULT_SEC:g} s from the original project; log runs with `end --calls N` to measure yours"


def cmd_calls(a):
    """Time = first call + remaining calls x median seconds / parallelism (+ sequential rounds); cost = calls x per-call + cache writes."""
    if a.sec is None:
        a.sec, src = measured_sec()
        print(f"seconds per call: {a.sec:.1f} ({src})")
    seq = a.rounds or 0
    t = (a.first + max(0, a.n - 1) * a.sec / max(1, a.parallel) + seq * a.sec) / 60
    cost = a.n * a.usd + a.cache_writes * a.cache_usd
    print(f"{a.n} calls, {a.parallel} in parallel{f', {seq} sequential rounds' if seq else ''}: ~{t:.0f} min (range {t * 0.8:.0f}-{t * 1.5:.0f}); "
          f"cost ~{cost:.2f} USD (range {cost * 0.6:.2f}-{cost * 1.4:.2f}; lower if the prompt cache hits)")


def cmd_start(a):
    e = {"id": uuid.uuid4().hex[:8], "task": a.task, "kind": a.kind, "gut_min": a.gut, "estimate_min": a.estimate,
         "estimate_usd": a.usd, "start": now(), "project": a.project or project(), "parallel": a.parallel,
         "new_codebase": a.new_codebase, **machine()}
    with log_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(e["id"])


def find(a) -> tuple[list[dict], dict]:
    rows = read(log_path())
    e = next((r for r in rows if r["id"] == a.id), None)
    if not e:
        sys.exit(f"no entry {a.id}")
    return rows, e


def write(rows: list[dict]):
    log_path().write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def paused_min(e: dict, until: dt.datetime) -> float:
    """Minutes the clock was stopped, including a pause that is still running."""
    p = e.get("paused_min", 0)
    if e.get("paused_at"):
        p += (until - dt.datetime.fromisoformat(e["paused_at"])).total_seconds() / 60
    return p


def cmd_pause(a):
    rows, e = find(a)
    if not e.get("paused_at"):
        e["paused_at"] = now()
        write(rows)
    print(f"{e['id']} paused")


def cmd_resume(a):
    rows, e = find(a)
    if e.get("paused_at"):
        e["paused_min"] = round(paused_min(e, dt.datetime.now()), 1)
        del e["paused_at"]
        write(rows)
    print(f"{e['id']} running again (paused {e.get('paused_min', 0)} min in total)")


def cmd_cancel(a):
    rows, e = find(a)
    e.update(cancelled=now(), note=a.note)
    write(rows)
    print(f"{e['id']} cancelled, not used for calibration")


def cmd_end(a):
    rows, e = find(a)
    end = dt.datetime.now()
    paused = paused_min(e, end)
    mins = (end - dt.datetime.fromisoformat(e["start"])).total_seconds() / 60 - (a.wait or 0) - paused
    e.pop("paused_at", None)
    e.update(end=end.isoformat(timespec="seconds"), wait_min=a.wait or 0, paused_min=round(paused, 1),
             actual_min=round(max(mins, 0.1), 1), actual_usd=a.usd, note=a.note, **({"calls": a.calls} if a.calls else {}))
    write(rows)
    est = e.get("estimate_min")
    ratio = f", estimate/actual {est / e['actual_min']:.1f}" if est else ""
    print(f"{e['task']}: estimated {est} min, actual {e['actual_min']} min{ratio}")


def cmd_calibrate(a):
    for k, f in factors(not a.no_seed).items():
        print(f"{k:10} n={f['n']:3}  factor median {f['median']:.1f}  (p20 {f['p20']:.1f}, p80 {f['p80']:.1f})  {f['source']}")
    usd = [(e["estimate_usd"], e["actual_usd"]) for e in entries(not a.no_seed) if e.get("estimate_usd") and e.get("actual_usd")]
    if usd:
        print(f"cost      n={len(usd):3}  actual/estimate median {st.median(b / a_ for a_, b in usd):.2f}")


def open_entries(max_hours: float = 12) -> list[dict]:
    """Started, not ended, and not older than max_hours (older ones are forgotten, not open)."""
    lim = dt.datetime.now() - dt.timedelta(hours=max_hours)
    return [e for e in read(log_path()) if not e.get("actual_min") and not e.get("cancelled")
            and dt.datetime.fromisoformat(e["start"]) > lim]


def cmd_open(a):
    for e in open_entries():
        state = " (paused)" if e.get("paused_at") else ""
        print(f"{e['id']} started {e['start'][11:16]}{state}, estimate {e.get('estimate_min')} min: {e['task'][:70]}")


def cmd_list(a):
    for e in read(log_path())[-a.last:]:
        print(f"{e['id']} {e['start'][:16]} {e['kind']:9} est {e.get('estimate_min')} act {e.get('actual_min')}  {e['task'][:60]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("suggest")
    s.add_argument("--kind", choices=KINDS, required=True)
    s.add_argument("--gut", type=float, required=True, help="your first feeling, in minutes of agent work")
    s.add_argument("--no-seed", action="store_true")
    c = sp.add_parser("calls")
    c.add_argument("--n", type=int, required=True, help="number of model calls")
    c.add_argument("--sec", type=float, help="median seconds per call (default: measured from your log, else 11.5)")
    c.add_argument("--parallel", type=int, default=1)
    c.add_argument("--rounds", type=int, help="extra calls that must run one after another (e.g. turns of a simulation)")
    c.add_argument("--first", type=float, default=20, help="seconds for the first call (cache write, startup)")
    c.add_argument("--usd", type=float, default=0.05, help="median cost per call")
    c.add_argument("--cache-writes", type=int, default=0, help="distinct long system prompts that must be cached once")
    c.add_argument("--cache-usd", type=float, default=0.8)
    st_ = sp.add_parser("start")
    st_.add_argument("--task", required=True)
    st_.add_argument("--kind", choices=KINDS, required=True)
    st_.add_argument("--gut", type=float)
    st_.add_argument("--estimate", type=float, required=True)
    st_.add_argument("--usd", type=float)
    st_.add_argument("--parallel", type=int, help="model calls or subagents running at the same time")
    st_.add_argument("--new-codebase", action="store_true", help="code you have not worked in before (slower than the seed data)")
    st_.add_argument("--project", help="project name (default: folder holding .claude/ or .git; or $ESTIMATES_PROJECT)")
    for name in ("pause", "resume"):
        sp.add_parser(name).add_argument("id")
    ca = sp.add_parser("cancel")
    ca.add_argument("id")
    ca.add_argument("--note")
    e = sp.add_parser("end")
    e.add_argument("id")
    e.add_argument("--wait", type=float, help="minutes spent waiting for a human, excluded")
    e.add_argument("--usd", type=float)
    e.add_argument("--calls", type=int, help="model calls made (model-run), so seconds per call can be measured")
    e.add_argument("--note")
    k = sp.add_parser("calibrate")
    k.add_argument("--no-seed", action="store_true")
    sp.add_parser("open")
    li = sp.add_parser("list")
    li.add_argument("--last", type=int, default=10)
    a = ap.parse_args()
    {"suggest": cmd_suggest, "calls": cmd_calls, "start": cmd_start, "end": cmd_end, "calibrate": cmd_calibrate, "list": cmd_list,
     "open": cmd_open, "pause": cmd_pause, "resume": cmd_resume, "cancel": cmd_cancel}[a.cmd](a)


if __name__ == "__main__":
    main()
