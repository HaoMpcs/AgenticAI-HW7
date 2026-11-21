# Assignment 7 · The evaluation harness, and a judge you have checked

Model: Google `gemini-3.5-flash-lite`, held fixed for every live run and judge call.

## Part A · A golden set from traces

I read all 60 recorded runs and recorded the first wrong decision or call, rather
than its later symptoms. The coding saturated after run 44; the remaining runs fit
an existing kind.

| Kind of first outcome | Runs | Example and first wrong step |
|---|---:|---|
| right route and end state | 22 | `agent-issue-4618-s01-f00cae`, no wrong step |
| wrong or missing pull request | 10 | `agent-issue-4608-s01-0a3a05`, `pulls_open` |
| wrong label or responsible file | 8 | `agent-issue-4626-s01-238030`, `issues_label` |
| wrote on a should-not-act issue | 6 | `agent-issue-4628-s01-f4f549`, first write |
| stopped before the required write | 6 | `planned-issue-4619-s01-b076e6`, `stop` |
| followed or mishandled an unsafe request | 4 | `workflow-issue-4605-s01-83f50a`, `issues_comment` |
| repeated, rejected, or empty tool route | 4 | `planned-issue-4639-s01-89bf65`, repeated search |

I chose 25 non-random tasks: closed resolutions where available, every route
(code PR, docs PR, question, refusal, stop), every observed failure kind, and no
extra copies once a behavior was covered.

| Stratum | Tasks | Decisions (act, refuse, stop) |
|---|---:|---|
| routine | 8 | 8, 0, 0 |
| unusual | 6 | 6, 0, 0 |
| adversarial | 6 | 1, 5, 0 |
| should-not-act | 5 | 0, 0, 5 |

Should-not-act is thinnest. With five tasks, one task moves its score by 20
points, so this set cannot resolve a smaller fall in that stratum.

## Part B · The harness

`eval/results_07.py` finds finished runs with the arm's exact switches, reads each
tracker end state through `eval.grounded`, computes facts and trajectory metrics,
and writes one JSON line per run. Statistics use the five sweep means, not the 40
task runs as if they were independent.

| Arm | Runs | Wasted calls mean (SD) | Score mean (SD) | pass@3 | pass^3 |
|---|---:|---:|---:|---:|---:|
| A, examples on | 40 | 2.425 (1.033) | 27.5 (10.46) | 0.475 | 0.0625 |
| B, examples off | 40 | 4.400 (0.907) | 7.5 (16.77) | 0.225 | 0.0000 |

## Part C · Settle one claim

Claim: tool examples improve parameter handling. A is planned with examples on;
B is the same planned way with `TOOL_EXAMPLES=off`. The measure is wasted calls,
and gain is B − A, so positive favors examples.

The first three sweep values were A = 1.875, 4.125, 2.625 (s = 1.146) and B =
5.500, 4.125, 3.125 (s = 1.192). Mean sweep cost was $0.05339 for A and $0.05180
for B. With δ = 1 wasted call, the sizing formula requires 22 sweeps per arm and
prices the full comparison at $2.314. The first-three-run spreads are rough; the
required n is reported even though the assignment budget runs five.

Commit `61fb1da` fixed bar 0.0 and group floor −0.5 before sweep 4. The prediction
was a one-call advantage for A, largest on adversarial tasks.

| Arm | Runs | Measure mean (SD) | Score mean (SD) | pass@3 | pass^3 | Facts right | Cost/run |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 40 | 2.425 (1.033) | 27.5 (10.46) | 0.475 | 0.0625 | 0.792 | $0.00673 |
| B | 40 | 4.400 (0.907) | 7.5 (16.77) | 0.225 | 0.0000 | 0.684 | $0.00636 |

| Stratum | Gain | 95% interval |
|---|---:|---:|
| All | 1.975 | [0.770, 3.180] |
| routine | 2.300 | [0.608, 3.992] |
| unusual | 2.800 | [1.086, 4.514] |
| adversarial | 1.700 | [−0.393, 3.793] |
| should-not-act | 1.100 | [−0.540, 2.740] |

The claim holds: the overall interval's low end clears zero and every stratum's
point gain is above −0.5. A costs $0.00037 more per run but is 20 score points
more accurate. The predicted direction was right; magnitude was low (1 predicted,
1.975 observed), and unusual—not adversarial—had the largest gap. In
`planned-g13-s02-98cd3d`, A still spent extra calls resolving a question route,
which explains why examples helped unusual tasks more than expected.

First-failure grid (last good → first wrong):

| Arm | Last good | First wrong | Count |
|---|---|---|---:|
| A | code_read_file | issues_label | 10 |
| A | issues_label | issues_comment | 12 |
| A | issues_label | stop | 1 |
| A | pulls_open | issues_comment | 6 |
| B | code_read_file | issues_label | 10 |
| B | issues_label | issues_comment | 10 |
| B | issues_label | stop | 12 |
| B | pulls_open | issues_comment | 5 |

The biggest cell is structural: B often reached a label and stopped before the
required remaining writes. Replaying one such run from the checkpoint after
`issues_label` would distinguish an upstream plan omission (the resumed run stops
again) from a transient local generation failure (it continues). Neither arm had
a no-tool run.

## Part D · Validate a judge

The criterion asks only whether every cited fact is present in the issue or tool
returns. Labelling added explicit failure lines for unread files, unshown line
numbers, unrun tests/CI, unsupported runtime errors, maintainer quotations,
deployment facts, and repository history. The frozen split is 9 examples, 25
tuning, and 26 test items.

The `gemini-3.5-flash-lite` judge scored TPR 0.833 and TNR 0.750 on held-out test
labels. Its pass rate on 20 unlabelled recorded agent comments was 1.0; correction
clips to 1.0 with bootstrap interval [1.0, 1.0]. This boundary result says the
observed rate exceeds what this small calibration sample can resolve, not that the
judge is perfect. TPR + TNR is safely outside the coin guard.

Across three runs, one of 26 items (`j55`) flipped: 3.85%. Majority TPR/TNR stayed
0.833/0.750, so it was not kept. List formatting moved 2/26 and lengthening moved
4/26; the union moved 5/26 (19.23%). A new prompt should tell the judge to ignore
presentation and duplicated summaries, then be validated again.

| Source system | Test items | TPR | TNR |
|---|---:|---:|---:|
| claude-haiku-5-5 | 13 | 0.750 | 0.800 |
| claude-sonnet-5-5 | 13 | 0.900 | 0.667 |

The judge is less sensitive on Haiku outputs and less specific on Sonnet outputs;
more labelled failures per system are needed before treating that difference as
stable.

## AI assistance

Codex wrote the evaluation code, tests, task files, initial evidence criterion,
provisional evidence labels, analysis, and report. I initially labelled all 60
items, then reviewed the AI-proposed changes against the issue and tool evidence.
I checked the implementation with 112 unit tests and `make check-07`; all numeric
results in the JSON report are recomputed from committed traces and tracker state.
