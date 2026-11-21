"""Interactive, human-only labeller for Assignment 7 judge outputs.

This program displays the supplied issue, evidence and comment without scoring or
suggesting a verdict. It appends only the verdict and reason typed by the person.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from harness import ROOT

OUTPUTS = ROOT / "fixtures" / "judge" / "outputs"
LABELS = ROOT / "eval" / "labels" / "labels.csv"


def existing() -> dict[str, tuple[str, str]]:
    if not LABELS.exists():
        return {}
    with LABELS.open(newline="") as stream:
        return {row["id"]: (row["label"], row["reason"]) for row in csv.DictReader(stream)}


def save(labels: dict[str, tuple[str, str]]) -> None:
    LABELS.parent.mkdir(parents=True, exist_ok=True)
    with LABELS.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["id", "label", "reason"])
        for item in sorted(labels):
            writer.writerow([item, *labels[item]])


def main() -> int:
    labels = existing()
    paths = sorted(OUTPUTS.glob("*.json"))
    for path in paths:
        data = json.loads(path.read_text())
        item = data["id"]
        if item in labels:
            continue
        print("\n" + "=" * 80)
        print(f"{item} · system {data['system']}")
        print("\nISSUE\n", json.dumps(data["issue"], indent=2, ensure_ascii=False))
        print("\nEVIDENCE\n", json.dumps(data["evidence"], indent=2, ensure_ascii=False))
        print("\nCOMMENT\n", data["comment"])
        while True:
            answer = input("\n[p]ass, [f]ail, [q]uit: ").strip().lower()
            if answer == "q":
                save(labels)
                print(f"saved {len(labels)} labels to {LABELS.relative_to(ROOT)}")
                return 0
            if answer not in {"p", "f"}:
                continue
            reason = input("one-line reason: ").strip()
            if reason:
                labels[item] = ("pass" if answer == "p" else "fail", reason)
                save(labels)
                break
    print(f"complete: saved {len(labels)} labels to {LABELS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
