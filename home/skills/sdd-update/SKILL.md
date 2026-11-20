---
name: sdd-update
description: Update the Spec Kit in the current project, brought in by /sdd-init, to the latest stable release while keeping every file the maintainer changed.
disable-model-invocation: true
---

# sdd-update

Update the Spec Kit that `/sdd-init` brought into the current project to the latest
stable release. All decisions are made by the script; your job is to run it once and
report what it printed.

Arguments: `$ARGUMENTS`

## 1. Check the arguments

This skill takes no arguments. If any argument was given, run nothing: tell the
maintainer that `/sdd-update` takes no arguments, that it always updates to the latest
stable release, and that it cannot pick a version or downgrade. Then stop.

## 2. Run it

Run `uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_update.py"` in the current project
directory, exactly once. Do not add options and do not change directory first.

## 3. Report

Report everything the script printed, without leaving out any path:

- the version change (from which version to which version)
- every `updated`, `created`, `removed`, `kept`, `staged` and `warning` line; for each
  `kept` file, also give the path of its comparison copy under `.specify/sdd-update/`
- the `Git:` line and, when printed, the `Next:` line

## 4. When it fails

If the exit code is not 0, report the reason and what the maintainer should do, as
printed by the script, then stop. The same applies when the `uv` command does not
exist: say that `uv` is missing and has to be installed, then stop.

- Do NOT run the script again.
- Do NOT update Spec Kit in any other way, and do NOT run `specify` yourself.
- Do NOT create or edit files under `.specify/` or any `speckit-*` skill by hand.
- When the script asks for `/sdd-init` to be run first, ask the maintainer to run it.
  Do NOT run it yourself.

## 5. Kept files and comparison copies

Do NOT merge kept files on your own, and do NOT modify or delete the comparison copies
under `.specify/sdd-update/`. Help compare or merge them only when the maintainer later
asks for it explicitly.

## 6. Leave the rest alone

Do NOT commit, do NOT push, and do NOT modify any file the script did not change.
