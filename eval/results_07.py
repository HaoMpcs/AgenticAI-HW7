"""Assignment 7, Part B, task 1: one line per run, in results/<arm>.jsonl
(checks/FORMATS.md, section 15.4).

    python -m eval.results_07 --arm A --way planned --claim plan
    python -m eval.results_07 --arm B --way planned --switch TOOL_EXAMPLES=off --claim examples

Reads the arm's finished runs on your subset's golden tasks in runs/, checks each with your
grounded check, computes Part C's measure and the five metrics, and writes one line
per run. The helpers below find the runs and read them; the rest is yours.

A line (section 15.4):

    {"arm": "A", "way": "planned", "switches": {...}, "run_id": "...", "task": "g07",
     "stratum": "routine", "sweep": 1, "passed": true, "facts": {"present": 6, "total": 6},
     "measure": 0, "tokens": 31234, "cost_usd": 0.0412, "wall_clock_s": 18.2,
     "metrics": {"step_count": 2, "precision": 1.0, "recall": 1.0, "repeats": 0,
                 "orphans": 1, "no_tools": false, "cost_usd": 0.0412, "latency_s": 18.2}}

Part C's measure, per run, by claim (section 15.4): tokens, the run_end line's
totals.total_tokens; plan, the run's repeats; examples, its wasted calls: the lines of
its call record (runs/<run_id>.calls.jsonl) whose outcome is "rejected", "error" or
"protocol", plus the search calls whose result has "count": 0; checkpoint, its duplicate
writes: the comments beyond one, plus the open pull requests beyond one, on its issue
in its end state; split, 100 when the run passed and 0 when it did not.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from harness import LAB, ROOT
from harness import switches as switch_board
from harness.formats import UNFINISHED
from harness.roles import tool_for
from harness.tasks import end_state, load_tasks, read_subset
from harness.trace import read_trace
from harness.tracker import Tracker
from eval.grounded import check
from eval.metrics import metrics


def finished_runs(way: str, switches: dict | None = None, root: Path = ROOT,
                  scripted: bool = False) -> list[list[dict]]:
    """Every finished Assignment 7 run of `way` with these switches (unset ones at their
    defaults), on a real model, as its trace's lines: one list per run. A run is finished
    when its last line is run_end and it did not end quota or rate_limited. With
    scripted=True, the runs on a scripted model instead, to test your code for free."""
    want = {**switch_board.DEFAULTS, **(switches or {})}
    out = []
    for path in sorted((root / "runs").glob("*.jsonl")):
        if path.name.startswith("_") or path.name.count(".") > 1:
            continue
        lines = read_trace(path)
        start = lines[0] if lines else {}
        if start.get("type") != "run_start" or start.get("lab") != LAB or start.get("way") != way:
            continue
        if {**switch_board.DEFAULTS, **(start.get("switches") or {})} != want:
            continue
        free = str(start.get("backend", "")).startswith("harness.scripted:") or start.get("backend") == "never-stops"
        if free != scripted:
            continue
        ends = [r.get("terminal_reason") for r in lines if r.get("type") == "end"]
        if lines[-1].get("type") != "run_end" or set(ends) & set(UNFINISHED):
            continue
        out.append(lines)
    return out


def call_record(run_id: str, root: Path = ROOT) -> list[dict]:
    """A run's call record, runs/<run_id>.calls.jsonl, one dict per line."""
    path = root / "runs" / f"{run_id}.calls.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--arm", required=True, choices=["A", "B"])
    p.add_argument("--way", required=True)
    p.add_argument("--switch", action="append", default=[], metavar="NAME=VALUE")
    p.add_argument("--claim", required=True, choices=["tokens", "plan", "examples", "checkpoint", "split"])
    p.add_argument("--tasks", default="eval/golden/v1/tasks")
    p.add_argument("--subset", default="eval/subsets/claim.txt", help="only these task IDs (Part C)")
    p.add_argument("--scripted", action="store_true",
                   help="the runs on a scripted model, to test this script for free: writes "
                        "results/scripted_<arm>.jsonl, which the checker never reads")
    args = p.parse_args(argv)
    switches = _switches(args.switch)
    tasks = {task.id: task for task in load_tasks(args.tasks)}
    subset = set(read_subset(args.subset))
    unknown = subset - set(tasks)
    if unknown:
        raise SystemExit(f"subset names unknown tasks: {', '.join(sorted(unknown))}")

    tracker = Tracker(flaky=False, readback_fail=False)
    rows = []
    for lines in finished_runs(args.way, switches, scripted=args.scripted):
        start, end = lines[0], lines[-1]
        task_id = str(start.get("task"))
        if task_id not in subset:
            continue
        task = tasks[task_id]
        run_id = str(start["run_id"])
        state = end_state(tracker, run_id, task)
        grounded = check(task, state)
        run_metrics = metrics(lines, task)
        totals = end.get("totals") or {}
        rows.append({
            "arm": args.arm,
            "way": args.way,
            "switches": start.get("switches") or {},
            "run_id": run_id,
            "task": task.id,
            "stratum": task.stratum,
            "sweep": int(start.get("sweep") or 0),
            "passed": grounded["passed"],
            "facts": {"present": sum(v == "present" for v in grounded["facts"].values()),
                      "total": len(grounded["facts"])},
            "measure": _measure(args.claim, lines, run_metrics, state, task, run_id),
            "tokens": int(totals.get("total_tokens") or 0),
            "cost_usd": float(totals.get("cost_usd") or 0.0),
            "wall_clock_s": float(end.get("elapsed_s") or 0.0),
            "metrics": run_metrics,
        })

    rows.sort(key=lambda row: (row["sweep"], row["task"], row["run_id"]))
    destination = ROOT / "results" / (f"scripted_{args.arm}.jsonl" if args.scripted else f"{args.arm}.jsonl")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    print(f"wrote {len(rows)} runs to {destination.relative_to(ROOT)}")
    return 0


def _switches(items: list[str]) -> dict:
    names = {"FLAKY_WRITES": "flaky_writes", "READBACK_FAIL": "readback_fail",
             "KEY_MODE": "key_mode", "VERIFY": "verify", "TOOL_EXAMPLES": "tool_examples"}
    out = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"--switch needs NAME=VALUE, not {item!r}")
        name, value = item.split("=", 1)
        key = names.get(name.upper(), name.lower())
        lowered = value.strip().lower()
        out[key] = lowered in {"1", "true", "yes", "on"} if key in {"flaky_writes", "readback_fail"} else lowered
    return out


def _measure(claim: str, lines: list[dict], run_metrics: dict, state: dict, task, run_id: str):
    end = lines[-1]
    if claim == "tokens":
        return int((end.get("totals") or {}).get("total_tokens") or 0)
    if claim == "plan":
        return run_metrics["repeats"]
    if claim == "split":
        return 100 if check(task, state)["passed"] else 0
    if claim == "checkpoint":
        issue_state = state[int(task.issues[0])]
        return max(0, len(issue_state.get("comments") or []) - 1) + max(0, len(issue_state.get("prs") or []) - 1)
    if claim == "examples":
        wasted = 0
        search_name = tool_for("search")
        for record in call_record(run_id):
            if record.get("outcome") in {"rejected", "error", "protocol"}:
                wasted += 1
                continue
            result = record.get("result")
            if record.get("tool") == search_name or record.get("name") == search_name:
                if isinstance(result, str):
                    try:
                        result = json.loads(result)
                    except json.JSONDecodeError:
                        result = {}
                if isinstance(result, dict) and result.get("count") == 0:
                    wasted += 1
        return wasted
    raise ValueError(f"unknown claim {claim}")


if __name__ == "__main__":
    raise SystemExit(main())
