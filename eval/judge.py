"""Assignment 7, Part D: the judge, its rates and its correction (checks/FORMATS.md,
section 15.10).

    python -m eval.judge test 1        # run 1 on the test set: eval/judge/verdicts/test_1.jsonl
    python -m eval.judge versions      # the test items' list and long versions: versions.jsonl
    python -m eval.judge recorded      # the agent way's recorded comments: recorded.jsonl

Your judge reads one output, its issue and what RepoMind's tools returned, and
answers with slide 36's fixed reply: JSON with a one-line "reasoning", then an
"answer", "Pass" or "Fail". Every call goes through a metered judge session, so its
tokens and cost are recorded and priced, and count against lab_token_ceiling:

    from harness.meter import judge_session
    with judge_session("test-1") as session:
        response = session.client.create(system=prompt, messages=[{"role": "user", "content": text}])
        session.trace.model_call(0, response, purpose="judge")

Write session.id on every verdict line. To test the plumbing for nothing, pass
backend="harness.scripted:PassEverything", a judge that passes everything: a coin.

The checker calls `correct`, `rates` and `bootstrap` on cases of its own, and
`correct` on a coin, so keep their names, arguments and returns.
"""

from __future__ import annotations

import json  # noqa: F401
import random
import argparse
import re
import yaml
from pathlib import Path

from harness import ROOT
from harness.meter import judge_session  # noqa: F401

OUTPUTS = ROOT / "fixtures" / "judge" / "outputs"
VERDICTS = ROOT / "eval" / "judge" / "verdicts"
PROMPT = ROOT / "prompts" / "judge.md"


class CoinJudge(ValueError):
    """TPR + TNR is within 0.1 of 1: the judge is no better than a coin. Fix it, do not
    correct it (slide 44)."""


def correct(p: float, tpr: float, tnr: float) -> float:
    """The share you would pass, labelling by hand, from the judge's pass rate p on
    outputs nobody labelled: (p + TNR - 1) / (TPR + TNR - 1) (slide 44), clipped to
    0 to 1. Raises CoinJudge when TPR + TNR is within 0.1 of 1."""
    denominator = tpr + tnr - 1
    if abs(denominator) <= 0.1:
        raise CoinJudge("TPR + TNR is too close to 1")
    return min(1.0, max(0.0, (p + tnr - 1) / denominator))


def rates(verdicts: dict[str, str], labels: dict[str, str]) -> tuple[float, float]:
    """(TPR, TNR) of the judge's verdicts against your labels, each "pass" or "fail",
    on the items both cover (slide 43): TPR is the share of the labelled passes the
    judge passed, TNR the share of the labelled fails it failed."""
    positives = [item for item, label in labels.items() if label == "pass" and item in verdicts]
    negatives = [item for item, label in labels.items() if label == "fail" and item in verdicts]
    tpr = sum(verdicts[item] == "pass" for item in positives) / len(positives) if positives else 0.0
    tnr = sum(verdicts[item] == "fail" for item in negatives) / len(negatives) if negatives else 0.0
    return tpr, tnr


def bootstrap(verdicts: dict[str, str], labels: dict[str, str], p: float,
              resamples: int = 2000, seed: int = 0) -> tuple[float, float]:
    """The middle 95% of the corrected rate over resamples of the test items, drawn
    with replacement, as many as there are, each time recomputing TPR and TNR
    (slide 44). A resample on which the judge is a coin is left out."""
    items = [item for item in labels if item in verdicts]
    rng = random.Random(seed)
    corrected = []
    for _ in range(resamples):
        draw = [rng.choice(items) for _ in items]
        positives = [item for item in draw if labels[item] == "pass"]
        negatives = [item for item in draw if labels[item] == "fail"]
        if not positives or not negatives:
            continue
        tpr = sum(verdicts[item] == "pass" for item in positives) / len(positives)
        tnr = sum(verdicts[item] == "fail" for item in negatives) / len(negatives)
        try:
            corrected.append(correct(p, tpr, tnr))
        except CoinJudge:
            continue
    if not corrected:
        return None, None
    corrected.sort()
    last = len(corrected) - 1
    return corrected[int(0.025 * last)], corrected[int(0.975 * last)]


def load_outputs(root: Path = ROOT) -> dict[str, dict]:
    """The 60 outputs to label, by ID (section 15.9)."""
    return {p.stem: json.loads(p.read_text()) for p in sorted((root / "fixtures" / "judge" / "outputs").glob("*.json"))}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["test", "versions", "recorded"])
    parser.add_argument("run", nargs="?", type=int, choices=[1, 2, 3])
    parser.add_argument("--backend")
    args = parser.parse_args(argv)
    if args.command == "test" and args.run is None:
        parser.error("test requires run 1, 2 or 3")

    prompt = PROMPT.read_text()
    VERDICTS.mkdir(parents=True, exist_ok=True)
    if args.command in {"test", "versions"}:
        split = yaml.safe_load((ROOT / "eval" / "labels" / "split.yaml").read_text())
        outputs = load_outputs()
        items = []
        for item in split["test"]:
            if args.command == "test":
                items.append((item, None, outputs[item], outputs[item]["comment"]))
            else:
                for version in ("list", "long"):
                    items.append((item, version, outputs[item], outputs[item]["versions"][version]))
        name = f"test-{args.run}" if args.command == "test" else "versions"
        destination = VERDICTS / (f"test_{args.run}.jsonl" if args.command == "test" else "versions.jsonl")
    else:
        items = _recorded_items()
        name, destination = "recorded", VERDICTS / "recorded.jsonl"

    rows = []
    with judge_session(name, backend=args.backend) as session:
        for item, version, evidence, comment in items:
            payload = {"issue": evidence["issue"], "evidence": evidence["evidence"], "comment": comment}
            response = session.client.create(system=prompt, messages=[{
                "role": "user", "content": json.dumps(payload, ensure_ascii=False)
            }])
            session.trace.model_call(0, response, purpose="judge")
            answer, reasoning = _parse(response.text)
            row = {"id": item, "answer": answer, "reasoning": reasoning,
                   "session": session.id, "model": response.model}
            if version:
                row["version"] = version
            rows.append(row)
    destination.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    print(f"wrote {len(rows)} verdicts to {destination.relative_to(ROOT)}")
    return 0


def _parse(text: str) -> tuple[str, str]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"judge did not return JSON: {text[:200]!r}")
    data = json.loads(match.group(0))
    answer = str(data.get("answer", "")).strip().lower()
    reasoning = " ".join(str(data.get("reasoning", "")).split())
    if answer not in {"pass", "fail"} or not reasoning:
        raise ValueError(f"bad judge verdict: {data!r}")
    return answer, reasoning


def _recorded_items() -> list[tuple[str, None, dict, str]]:
    items = []
    for path in sorted((ROOT / "fixtures" / "traces7").glob("agent-*.jsonl")):
        lines = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        calls = [line for line in lines if line.get("type") == "tool_call"]
        comments = [call for call in calls if call.get("name") in {"post_comment", "issues_comment"}]
        if not comments:
            continue
        final = comments[-1]
        before = calls[:calls.index(final)]
        issue_result = next((call.get("result") for call in before
                             if call.get("name") in {"read_issue", "issues_read"}), "")
        evidence = [{"tool": call.get("name"), "input": call.get("input"), "result": call.get("result", "")}
                    for call in before]
        comment = str((final.get("input") or {}).get("body") or "")
        items.append((str(lines[0]["run_id"]), None,
                      {"issue": issue_result, "evidence": evidence}, comment))
    return items


if __name__ == "__main__":
    raise SystemExit(main())
