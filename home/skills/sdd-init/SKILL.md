---
name: sdd-init
description: Bring the latest stable Spec Kit into the current project, or remove it again with the argument "remove".
disable-model-invocation: true
argument-hint: "[remove]"
---

# sdd-init

Bring Spec Kit into the current project, or remove it. All decisions are made by the
script; your job is to run it once and report what it printed.

Arguments: `$ARGUMENTS`

## 1. Pick the command

- No argument: run `uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_init.py" init`
- The argument is `remove`: run `uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_init.py" remove`
- Anything else: run nothing. Tell the maintainer the usage is `/sdd-init` or
  `/sdd-init remove`, then stop.

## 2. Run it

Run the command in the current project directory, exactly once. Do not add options
and do not change directory first.

## 3. Report

Report everything the script printed, without leaving out any path:

- the Spec Kit version
- every `created`, `skipped`, `staged` and `warning` line (for remove: every
  `deleted`, `kept` and `unstaged` line)
- the `Git:` line
- both next steps, not just one of them: `/sdd-grill`, or `/speckit-constitution`
  followed by `/speckit-specify`

## 4. When it fails

If the exit code is not 0, report the reason and what the maintainer should do, as
printed by the script, then stop. The same applies when the `uv` command does not
exist: say that `uv` is missing and has to be installed, then stop.

- Do NOT run the script again.
- Do NOT install Spec Kit in any other way.
- Do NOT create or edit files under `.specify/` or any `speckit-*` skill by hand.

## 5. Leave the rest alone

Do NOT commit, do NOT push, and do NOT modify any file the script did not create.
