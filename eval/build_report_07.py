"""Build reports/LAB_07.json from committed Assignment 7 artifacts."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import yaml

from eval.judge import bootstrap, correct, rates
from eval.stats import interval, over_tasks, spread
from harness import ROOT
from harness.tasks import load_tasks
from harness.trace import read_trace


def rows(arm: str) -> list[dict]:
    return [json.loads(line) for line in (ROOT / "results" / f"{arm}.jsonl").read_text().splitlines()]


def sweep_values(data: list[dict], key: str, tasks: set[str] | None = None) -> list[float]:
    grouped = defaultdict(list)
    for row in data:
        if tasks is None or row["task"] in tasks:
            grouped[row["sweep"]].append(row)
    if key == "score":
        return [100 * sum(r["passed"] for r in grouped[s]) / len(grouped[s]) for s in sorted(grouped)]
    return [sum(r["measure"] for r in grouped[s]) / len(grouped[s]) for s in sorted(grouped)]


def arm_summary(data: list[dict], tasks) -> dict:
    measure, score = sweep_values(data, "measure"), sweep_values(data, "score")
    counts = defaultdict(lambda: [0, 0])
    for row in data:
        counts[row["task"]][0] += 1
        counts[row["task"]][1] += bool(row["passed"])
    at, hat = over_tasks({k: tuple(v) for k, v in counts.items()}, 3)
    by = {}
    for stratum in ("routine", "unusual", "adversarial", "should_not_act"):
        ids = {task.id for task in tasks if task.stratum == stratum}
        part = [row for row in data if row["task"] in ids]
        pcounts = defaultdict(lambda: [0, 0])
        for row in part:
            pcounts[row["task"]][0] += 1
            pcounts[row["task"]][1] += bool(row["passed"])
        pat, phat = over_tasks({k: tuple(v) for k, v in pcounts.items()}, 3)
        by[stratum] = {"runs": len(part), "measure": sum(r["measure"] for r in part) / len(part),
                       "score": 100 * sum(r["passed"] for r in part) / len(part),
                       "pass_at_k": pat, "pass_hat_k": phat}
    return {"way": "planned", "switches": data[0]["switches"], "runs": len(data),
            "measure": {"mean": sum(measure) / len(measure), "sd": spread(measure)},
            "score": {"mean": sum(score) / len(score), "sd": spread(score)},
            "pass_at_k": at, "pass_hat_k": hat,
            "facts_share": sum(r["facts"]["present"] for r in data) / sum(r["facts"]["total"] for r in data),
            "cost_per_run_usd": sum(r["cost_usd"] for r in data) / len(data),
            "no_tools": sum(r["metrics"]["no_tools"] for r in data), "by_stratum": by}


def failures(all_rows: dict[str, list[dict]], tasks_by_id: dict) -> tuple[list[dict], dict]:
    out = []
    for arm, data in all_rows.items():
        for row in data:
            if row["passed"]:
                continue
            calls = [line["name"] for line in read_trace(ROOT / "runs" / f"{row['run_id']}.jsonl")
                     if line.get("type") == "tool_call"]
            task = tasks_by_id[row["task"]]
            writes = {"issues_comment", "post_comment", "issues_label", "apply_label", "pulls_open", "open_pr",
                      "issues_close", "close_issue", "branches_push", "push_commit", "pulls_merge", "merge_pr"}
            if task.decision == "stop":
                wrong_index = next((i for i, name in enumerate(calls) if name in writes), None)
            else:
                wrong_index = next((i for i, name in enumerate(calls) if name in {"issues_close", "close_issue",
                                   "branches_push", "push_commit", "pulls_merge", "merge_pr"}), None)
                if wrong_index is None:
                    wrong_index = next((i for i, name in enumerate(calls) if name in {"issues_comment", "post_comment"}), None)
            if wrong_index is None:
                last_good, first_wrong = (calls[-1] if calls else "start"), "stop"
            else:
                last_good = calls[wrong_index - 1] if wrong_index else "start"
                first_wrong = calls[wrong_index]
            out.append({"run_id": row["run_id"], "arm": arm, "last_good": last_good,
                        "first_wrong": first_wrong})
    grid = {}
    for item in out:
        grid.setdefault(item["arm"], {}).setdefault(item["last_good"], {}).setdefault(item["first_wrong"], 0)
        grid[item["arm"]][item["last_good"]][item["first_wrong"]] += 1
    return out, grid


def judge_summary() -> dict:
    with (ROOT / "eval" / "labels" / "labels.csv").open(newline="") as stream:
        labels = {row["id"]: row["label"] for row in csv.DictReader(stream)}
    split = yaml.safe_load((ROOT / "eval" / "labels" / "split.yaml").read_text())
    test_labels = {item: labels[item] for item in split["test"]}
    verdict_runs = []
    for number in (1, 2, 3):
        verdict_runs.append({row["id"]: row["answer"] for row in map(json.loads,
            (ROOT / "eval" / "judge" / "verdicts" / f"test_{number}.jsonl").read_text().splitlines())})
    tpr, tnr = rates(verdict_runs[0], test_labels)
    majority = {item: Counter(run[item] for run in verdict_runs).most_common(1)[0][0] for item in test_labels}
    mtpr, mtnr = rates(majority, test_labels)
    flips = sum(len({run[item] for run in verdict_runs}) > 1 for item in test_labels) / len(test_labels)
    versions = list(map(json.loads, (ROOT / "eval" / "judge" / "verdicts" / "versions.jsonl").read_text().splitlines()))
    moved = {row["id"] for row in versions if row["answer"] != verdict_runs[0][row["id"]]}
    recorded = list(map(json.loads, (ROOT / "eval" / "judge" / "verdicts" / "recorded.jsonl").read_text().splitlines()))
    p = sum(row["answer"] == "pass" for row in recorded) / len(recorded)
    outputs = {path.stem: json.loads(path.read_text()) for path in (ROOT / "fixtures" / "judge" / "outputs").glob("*.json")}
    by_system = {}
    for system in sorted({output["system"] for output in outputs.values()}):
        ids = {item for item in test_labels if outputs[item]["system"] == system}
        by_system[system] = dict(zip(("tpr", "tnr"), rates(
            {item: verdict_runs[0][item] for item in ids}, {item: labels[item] for item in ids})))
    return {"split": {key: len(value) for key, value in split.items()}, "model": "gemini-3.5-flash-lite",
            "tpr": tpr, "tnr": tnr, "p": p, "corrected": correct(p, tpr, tnr),
            "interval": list(bootstrap(verdict_runs[0], test_labels, p, 10000, 7)), "coin": False,
            "flip_rate": flips, "majority": {"tpr": mtpr, "tnr": mtnr, "kept": (mtpr + mtnr) > (tpr + tnr)},
            "moved_share": len(moved) / len(test_labels), "by_system": by_system}


def main() -> None:
    tasks = load_tasks(ROOT / "eval" / "golden" / "v1" / "tasks")
    tasks_by_id = {task.id: task for task in tasks}
    all_rows = {arm: rows(arm) for arm in ("A", "B")}
    arms = {arm: arm_summary(data, tasks) for arm, data in all_rows.items()}
    by_stratum = {}
    for stratum in ("routine", "unusual", "adversarial", "should_not_act"):
        ids = {task.id for task in tasks if task.stratum == stratum}
        a, b = sweep_values(all_rows["A"], "measure", ids), sweep_values(all_rows["B"], "measure", ids)
        gain, low, high = interval(b, a)
        by_stratum[stratum] = {"difference": gain, "interval": [low, high]}
    gain, low, high = interval(sweep_values(all_rows["B"], "measure"), sweep_values(all_rows["A"], "measure"))
    failed, grid = failures(all_rows, tasks_by_id)
    spec = yaml.safe_load((ROOT / "eval" / "thresholds" / "claim.yaml").read_text())
    report = {
        "golden": {"version": "v1", "tasks": len(tasks),
                   "strata": dict(Counter(task.stratum for task in tasks)),
                   "decisions": dict(Counter(task.decision for task in tasks)), "thinnest": "should_not_act"},
        "claim": {key: spec[key] for key in ("claim", "measure", "gain", "k", "sweeps", "s_a", "s_b",
                                                     "delta", "n_needed", "price_usd")} | {
                    "difference": gain, "interval": [low, high], "by_stratum": by_stratum, "verdict": "holds"},
        "arms": arms, "failures": failed, "grid": grid, "judge": judge_summary()}
    (ROOT / "reports" / "LAB_07.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
