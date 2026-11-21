---
name: sdd-drive
description: After the specs are confirmed, have child sessions take every spec of a Spec Kit project, in number order, through plan, tasks, implement, a test run and a convergence check, without waiting for approval; stop and report only when something fails or is interrupted. Requires Spec Kit. Started only by the maintainer with /sdd-drive.
disable-model-invocation: true
---

# sdd-drive

Drive every unfinished spec of this project to done, one spec and one phase at a time. Each phase (plan, tasks,
implement, check) runs in a fresh child session that the script starts with `claude -p`; you, the main session, only
run the script, wait, and report. The tests are run by the script itself, never trusted from a child session.

Run every command from the project root (the current directory) as:

```text
uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_drive.py" <command>
```

Commands: `status`, `run --spec <dir> --phase <phase> --model <model> --reason "<reason>" [--resume] [--fresh]`,
`watch`, `test --spec <dir>`, `finalize`, `cancel`, `clear`. Each prints one JSON object; decide only from its fields.

## General rules (apply in every stage)

1. **You only coordinate.** You never run plan, tasks, implement or the convergence check yourself: never invoke
   `speckit-plan`, `speckit-tasks`, `speckit-implement` or `speckit-converge`, and never write or edit a plan, tasks,
   code or tests. Your only work is running `sdd_drive.py`, waiting and reporting. When a child session cannot start
   or keeps failing, do not take over the work; report and stop.
2. **Run `status` before every action.** Decide the next step only from the latest `status` output, never from
   memory or an earlier output, including after the conversation was compacted or restarted.
3. **Only through the script.** Do not write anything under `.specify/sdd-drive/` or `.specify/feature.json`, do not
   build a `claude` command yourself, do not create or switch branches, and do not rewrite the work description.
   Do not read or change `.specify/sdd-drive-state.json`; it belongs to another tool.
4. **Background runs and waiting.** Run `run`, `watch` and `test` with the Bash tool's `run_in_background: true` and
   `timeout: 7200000`. Then end your turn and wait for the completion notification: no polling, no sleep, no other
   work meanwhile. When the notification arrives, read that command's output. The child session runs in a detached
   driver, so the end of `run` or `watch` does not mean the child finished; the output's `status` tells you whether
   to `watch` again.
5. **Do not ask, do not wait for approval.** During the run, do not ask the maintainer anything and do not ask them
   to approve a plan or tasks; report only when you stop.
6. **Git.** Never commit, push, stash, reset, check out files, merge or delete branches yourself. Never push: the
   final report reminds the maintainer to push and check CI themselves.
7. **Never discard changes.** Do not discard, revert, stash or commit for the maintainer any uncommitted change to
   let the run continue, and do not revert protected files that a child changed.
8. **Model.** Before every `run`, judge the model from `next.hints` and the phase, and write one English sentence as
   the reason. Defaults: plan `opus`; tasks `sonnet`; implement `sonnet` for mechanical tasks, `opus` for new design
   or after a failure; check (the convergence check) `opus`. Do not default to `fable`; when you use it, the reason
   must say why a cheaper model is not enough. Within one run, do not use the strongest model for every child
   session. When resuming, use `next.model`.
9. **Secrets.** Never put a secret value in a reason or a report. Do not try to recover anything the script replaced
   with `(not shown...)`.
10. **Unexpected results.** When the script returns an exit code or `reason` this document does not mention, or its
    output cannot be parsed, tell the maintainer what happened, run `status` once more and describe the current
    progress from it, then stop.
11. **Language.** Talk to the maintainer in the language their global settings ask for; you may translate the
    script's English messages.
12. **The automatic resume after a usage limit is done only by the driver.** Do not wait for a reset yourself, do
    not schedule a wake-up, and do not `run --resume` on your own because of a usage limit. The automatic resume
    happens at most once, decided by the driver from the records. When you yourself were stopped by a usage limit
    and continue later (Claude Code continued automatically, or the maintainer sent a message), always start again
    from Stage 1 with `status` (rule 2).
13. **Reporting a usage limit.** Every such report includes: the cause (a usage limit, not a failure, not counted
    as a retry); the kind of limit (`limit.types`); the reset time (`limit.resets_at` converted to the maintainer's
    local time, or "no reset time, or it cannot be known"); the current progress (`state_after`); and whether the
    driver will resume automatically (and when) or the maintainer needs to type `/sdd-drive` again.

## Stage 1: Start (`status`)

Order: run `status`, handle it with the table below, announce, then go to Stage 3 or Stage 4.

| `status` result | Next step |
|---|---|
| exit code 3, `reason: dependency` | Say the sdd-grill skill is not installed next to this skill (redeploy with the deploy tool). Stop. |
| `reason: speckit-missing` | Say Spec Kit is not set up: run `/sdd-init` first, then create specs with `/sdd-grill` or `/sdd-rebuild`. Do not start a child session. Stop. |
| `reason: speckit-incomplete` | List the missing `speckit-*` skills from `missing`; say Spec Kit may have changed incompatibly or `/sdd-update` may be needed. Stop. |
| `reason: no-specs` | Say there is no spec yet: create specs with `/sdd-grill` or `/sdd-rebuild` first. Stop. |
| `reason: claude-missing` | Say the `claude` command was not found, so no child session can start. Do not do the work yourself. Stop. |
| `reason: conflict` | Say `.specify/sdd-drive/` holds files this skill did not create and ask the maintainer to check them. Do not delete anything. Stop. |
| `reason: state-unreadable` | Name the field path from `detail` (never a value). Explain that the records hold the failure counts, the test and check records, and which specs are the existing baseline. Offer `clear` once the maintainer agrees, and explain that after clearing no spec is a baseline any more, so every finished spec is tested and checked once again. Until they agree, stop. When they agree, run `clear` (not in the background): on `cleared: true` go back to the start of Stage 1; on any `reason`, report it and stop. Never suggest deleting `.specify/sdd-drive/` by hand. |
| `running: true` with `driver.phase` `running` or `resuming` | Report that a run is already in progress: its spec and phase (`running_attempt`), when it started, and whether it is an automatic resume. Do not start a second child session and do not `finalize`. Run `watch` in the background to take over (Stage 3B). |
| `running: true` with `driver.phase: waiting` | Report per rule 13 that the driver is waiting for the usage limit to reset: which spec and phase, the kind of limit, when it will resume automatically (`driver.waiting_until`), and the current progress. Say the maintainer can simply ask to cancel the automatic resume. Run `watch` in the background (Stage 3B). |
| `running: true` with only a launch in progress (`driver` is null) | Run `watch` in the background (Stage 3B). |
| `last_attempt.auto` is `true` or `last_attempt.auto_resume` is not null | Before the announcement, report this attempt: it was interrupted by a usage limit, whether the automatic resume happened and its result (this happened while the maintainer was away). Then continue with the other rows. |
| `next.action: finalize` | Go to Stage 2. |
| `dirty` is not empty and `leftovers: false` | List the paths. Explain that child sessions commit, so the maintainer must commit or handle these changes first. Do not discard anything, do not start a child session. Stop. |
| `next.action: none` | Report that every spec is done and nothing is pending. Do not start a child session. Stop. |
| `git: false` | Say this is not a git repository: changes cannot be judged from version history and child sessions will not commit. Continue. |
| `next.action` is `run`, `resume` or `test` | Announce: which specs will be handled (the ones whose `state` is not `done`, in number order), the spec and phase to start from, which specs are already done, which are the existing baseline (`baseline: true`: only tested, no convergence check), and each spec's failure counts. Then go to Stage 3 (`run`, `resume`) or Stage 4 (`test`). |

## Stage 2: Record an interrupted attempt (`finalize`)

Run `finalize` (not in the background), then:

| Result | Next step |
|---|---|
| success, and the attempt's `auto_resume` is `lost` | Report per rule 13: the child session was interrupted by a usage limit, the waiting driver is gone (for example after a restart), and the automatic resume did not happen. Say the next `/sdd-drive` resumes the same child session and this is not counted as a failure. Stop. |
| success (other) | Report that the run was interrupted (the child ended without a report): the spec, phase, model and start time, and the current progress from `state_after` and `status`. Say the next `/sdd-drive` resumes the same child session and this is not counted as a failure. Stop. |
| `reason: running` | Report that another run has just started. Stop. |
| `reason: nothing-to-finalize` | Go back to Stage 1. |
| anything else | Rule 10. |

## Stage 3: Start a child session (`run`)

Order: run `status` (rule 2); decide the model and the reason (rule 8); run in the background
`run --spec <next.spec> --phase <next.phase> --model <model> --reason "<reason>"` (when `next.action` is `resume`, add
`--resume` and use `next.model`); wait for the notification; read the output. For every entry of `attempts`, report
in one or two lines: the spec, the phase, the `outcome`, whether it was an automatic resume (`auto`), the requested
model and `model_used`, and the reason. Then follow the table, judging by the last attempt and `status`.
The output of `watch` (Stage 3B) has the same form and is handled with this table too.

| `run` result | Next step |
|---|---|
| `outcome: succeeded` | Go back to the start of Stage 3 or Stage 4 (run `status` first). Do not wait for approval. |
| `outcome: succeeded` with `phase: check` and `convergence: converged` | Report that the convergence check found nothing missing, so this spec is done (all tasks checked, tests passed, check passed). Go back to the start of Stage 3 or Stage 4 and begin the next spec. |
| `outcome: failed` | Stop the whole run; do not start any later spec. Report the spec, the phase, `failure.kind`, `failure.step`, `failure.reason` and the phase's failure count. For `requirements`, say the maintainer needs to fix the spec or the constitution. For `blocked-task`, list the task IDs (`failure.tasks`) and say they need the maintainer or a push. Remind them that any uncommitted changes the child left are theirs to decide on. Say the next `/sdd-drive` retries this phase after the fix. |
| `outcome: verify-failed` | Same as `failed`, explaining `detail.code`: `plan-missing` / `tasks-missing` (the child claimed success but the file is missing or still the template); `tasks-unfinished` (unchecked tasks remain); `tasks-removed` (tasks were deleted); `protected-changed` (list the changed constitution, spec or Spec Kit files from `detail.paths`; not reverted, ask the maintainer to check); `pushed` (remote-tracking refs changed; ask the maintainer to check the remote); `uncommitted` (changes were left uncommitted; nothing was discarded). For the check phase: `check-no-tasks` (the child said it appended tasks but tasks.md did not change; counted neither as done nor as gaps); `check-rewrote-tasks` (tasks.md was rewritten, checked or had tasks deleted instead of only appended to); `check-touched-files` (files other than tasks.md were changed; list `detail.paths`; not reverted). Say the next `/sdd-drive` checks again after the fix. |
| `outcome: gaps-found` | Stop the whole run; do not fix anything and do not start any later spec. List every item of `findings` (ID, text, `source_ref`, `gap_type`; when `findings_total` is over 50, give the total). Say these were appended to tasks.md as unchecked tasks and committed, and give the spec's check failure count. Say the next `/sdd-drive` first implements these tasks, then tests and checks again; if the maintainer thinks an item is not needed, they can handle it in tasks.md themselves. When `detail.code` is `report-mismatch`, also say the child's claim did not match the file and the file was used. |
| `status: waiting` (`auto_resume: waiting`) | Report per rule 13; say the driver will resume once automatically at `waiting_until`, the maintainer does not need to type anything, and they can ask to cancel. Run `watch` in the background (Stage 3B). |
| `status: running` (time limit reached, the child is still working) | Do not report details; run `watch` in the background (Stage 3B). |
| `status: launch-failed` | Report that the driver could not start. Do not do the work yourself. Stop. |
| last `outcome: usage-limit`, `auto_resume: not-waitable` | Report per rule 13: this limit has no reset time (for example a monthly spend limit) or it cannot be judged, so there is no automatic resume; progress and uncommitted files are kept. Say that after handling it (for example raising the limit or waiting for the allowance) the next `/sdd-drive` resumes the same child session. Stop. |
| last `outcome: usage-limit`, `auto_resume: already-auto` | Report per rule 13: after the automatic resume it hit a usage limit again, so it will not retry on its own. Say the next `/sdd-drive` resumes. Stop. |
| last `outcome: usage-limit`, `auto_resume: cancelled` | Report that the automatic resume was cancelled as asked and the progress is kept; the next `/sdd-drive` resumes. Stop. |
| last `outcome: usage-limit`, `auto_resume: skipped-changed` | Report that the working tree changed while waiting, so the driver did not resume, to keep those changes out of the child's commits. List the paths from `status`'s `dirty`. Ask the maintainer to handle them, then type `/sdd-drive` again. Stop. |
| an attempt has `auto: true` and the last `outcome` is `succeeded` | Report that the driver resumed automatically after the reset and finished the phase (time, model). Go back to the start of Stage 3 or Stage 4 (run `status` first). |
| an attempt has `auto: true` and the last `outcome` is something else | Handle it with the row of that outcome, and say in the report that it is the result of the automatic resume. |
| `outcome: api-error` (and `resume_failed` is not `true`) | Report the API error and `detail.text` (for example not logged in, or the model is unavailable). It is not counted as a failure and progress is kept. Do not do the work yourself and do not retry automatically. Stop; say the next `/sdd-drive` resumes after it is handled. |
| `outcome: interrupted` (and `resume_failed` is not `true`) | Report that the child ended without a report (`detail.code`) and the progress from `state_after`; it is not counted as a failure. Stop; the next `/sdd-drive` resumes. |
| `outcome: launch-failed` | Report that the child session could not start and why (`detail.text`). Do not do the work yourself. Stop. |
| `resume_failed: true` (whatever the `outcome`) | Report that the original child session could not be resumed (for example its history is not on this machine). Run the same phase once with a fresh session: `run ... --resume --fresh`. The new session still continues from the unfinished part of the files. If that fails too, handle its `outcome`. |
| `permission_denials` is not empty | List the denied tools in the phase report; it does not change the other rows. |
| `reason: secret` | Rewrite the reason without the secret and run once more. |
| `reason: running` | Report that another run is in progress (another main session may have taken over). Stop, and do not `watch`, so two main sessions never drive at once. |
| `reason: pending-finalize` or `reason: not-next` | Go back to Stage 1 (the state changed after `status`). |
| `reason: dirty` | Same as the `dirty` row of Stage 1. |
| `reason: branch-diverged` | Say the spec's branch already exists and has diverged from the current branch; ask the maintainer to decide how to merge or rename it. Do not merge or reset. Stop. |
| `reason` `speckit-missing`, `speckit-incomplete`, `claude-missing`, `conflict` or `state-unreadable` | Same as Stage 1. |
| `reason: os-error` | Report why writing or the git command failed. Stop. |
| the background command printed no JSON (killed, timed out, or you were interrupted and continued) | Go back to Stage 1; `status` shows `running` or `finalize`, handle that. |
| you yourself were stopped by a usage limit and continue later (the reset may already have passed) | Go back to Stage 1; whether the driver already resumed or finished, handle what `status` and `watch` show (rule 12). |

## Stage 3B: Wait for the driver (`watch`)

Order: run `watch` in the background, wait for the notification, and handle its output with the Stage 3 table.
`watch` reports a wait only when the driver starts waiting during that `watch`; when it runs out of time it prints
the current state. Also:

| Result | Next step |
|---|---|
| `reason: no-driver` | Go back to Stage 1. |
| while waiting, the maintainer asks to cancel the automatic resume | Go to Stage 6. |
| while waiting, the maintainer sends another message | Answer it; then, if `status` still shows the driver running, run `watch` in the background again. |

## Stage 4: Confirm the tests pass (`test`)

Order: run `status`; when `next.action` is `test`, run `test --spec <next.spec>` in the background; wait for the
notification; follow the table. You run the tests yourself through the script: do not trust a child session's claim
that the tests pass.

| Result | Next step |
|---|---|
| `passed: true` and the spec is an existing baseline (`baseline: true` in `status`) | Report that these existing-baseline specs (`covers`) passed and are done, with no convergence check (the maintainer can run Spec Kit's convergence check themselves to verify). Go back to the start of Stage 3 or Stage 4. |
| `passed: true` for other specs | Report that these specs (`covers`) passed; they are not done yet, the next step is the convergence check (`next.phase: check`). Go back to the start of Stage 3 or Stage 4. |
| `passed: false` | Stop; do not start any later spec. Report the spec, the test command, the exit code, the key lines of `output_tail` and the failure count. Say the next `/sdd-drive` tests again after the fix. |
| `reason: no-test-command` | Report that completion cannot be confirmed by tests because plan.md has no runnable test command; the spec is not treated as done. Stop. |
| `reason` `running`, `pending-finalize`, `not-next` or `dirty` | Same as the matching row of Stage 3. |
| the background command printed no JSON | Go back to Stage 1. |

## Stage 5: Final report

Whenever the run ends or stops (every stop above), the final report includes:

1. The state of every spec, from the last `status`: done, the current spec and phase, not started.
2. Why it stopped: for a failure, the spec, step, reason and failure count; for an interruption, its kind, stating
   clearly that it is not a failure; for a usage limit, rule 13, and whether the automatic resume already happened.
3. Every child session of this run: spec, phase, `outcome`, requested model and actual model (`model_used`), and the
   reason; when the convergence check found gaps, every item of `findings`.
4. The next step: what the next `/sdd-drive` will do; when everything is done, remind the maintainer to push and
   check CI on both platforms themselves, and the items in tasks.md's Notes that need them in person.

Reading only this report, the maintainer must know which spec, which step and why, without opening any child
session's history.

## Stage 6: Cancel the automatic resume (`cancel`)

Only when the maintainer explicitly asks, run `cancel` (not in the background).

| Result | Next step |
|---|---|
| `cancel_requested: true` | Say the driver stops within 30 seconds. Run `watch` in the background (Stage 3B); when it shows `auto_resume: cancelled`, report with the matching Stage 3 row and stop. |
| `reason: not-waiting` | From `status`, say there is no automatic resume waiting now (it may have started or finished already); continue with Stage 1. |
| anything else | Rule 10. |
