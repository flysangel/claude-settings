---
name: sdd-rebuild
description: Rebuild a project in a new project from an old project's nutrients (the output of /sdd-export). Run it in the new project, which needs Spec Kit. The maintainer goes through the old principles, features and lessons item by item to keep, modify, merge, split or discard them, adds this generation's new requirements, and confirms a final summary; only then does Spec Kit generate the constitution and the specs, and a lineage is left for the next rebirth. Nothing but its own progress is written before the maintainer confirms.
argument-hint: "<old project path>"
disable-model-invocation: true
---

# sdd-rebuild

The maintainer is rebuilding an old project as a new one. The old project left *nutrients* in its `.sdd-export/`
folder (written by `/sdd-export`): its principles, its features with their requirements and dependencies, the lessons
of that generation, and for every item the generation it first appeared in. This skill runs in the new project. It
lets the maintainer decide, item by item, what the new generation keeps, changes, merges, splits or drops, and which
new requirements it adds; then it has Spec Kit generate the constitution and one spec per feature, in dependency
order, and writes a *lineage* (`.sdd-rebuild/lineage.json`) into the new project. When the new project is exported
one day, `/sdd-export` reads that lineage, so that inherited items keep their identity across generations. The
lineage is read by another tool and a broken chain of `id`s cannot be repaired later; that is why a script composes
it, and why you never write it yourself.

There are two projects. The **new project** is the current folder: everything is written here. The **old project**
is the path the maintainer gives; it is read, never changed, and only through the script (stage 2 is the one
exception, and only with the maintainer's confirmation).

You do the conversation and the judgement: presenting the nutrients, asking the maintainer, comparing the generated
documents with what was confirmed. Everything that can be decided mechanically is done by a script that prints one
JSON object. Always run it from the new project's root (the current folder), exactly like this:

```text
uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_rebuild.py" check [--old <old project path>]
uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_rebuild.py" save [--refresh-source]        (the whole progress on stdin)
uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_rebuild.py" preview
uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_rebuild.py" claim <feature id> [--dir <specs/name>]
uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_rebuild.py" verify
uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_rebuild.py" lineage
uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_rebuild.py" focus
uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_rebuild.py" clear
```

- `check` reports both projects, the saved progress and the next step; it writes nothing.
- `save` validates and saves the progress (only into `.specify/sdd-rebuild/`).
- `preview` composes the lineage from the saved decisions and checks it; it writes nothing.
- `claim` records which spec folder Spec Kit just created for a feature.
- `verify` checks the generated constitution and specs against the confirmed summary; it writes nothing.
- `lineage` writes `.sdd-rebuild/lineage.json`.
- `focus` points `.specify/feature.json` at the first generated spec.
- `clear` removes the saved progress.

Every result has an exit code: 0 success, 1 refused (`reason` says why), 3 a precondition does not hold (`reason`
says why). On failure the JSON has `error`, one English sentence, and `reason`; react to `reason`, not to the
sentence. The work goes through thirteen stages in order, plus "Resuming" when a saved progress exists. Each stage
lists every outcome and what to do next.

## Rules for the whole run

These apply at every stage.

1. **Two projects; the old project is read through the script only.** Never open, list or search the old project's
   files with Read, Grep, Glob or any command: not its plan, tasks, code, specs, README or anything else. What you
   know about the old project comes from the output of `check` (the nutrients and the state of its old lineage).
   The plan, tasks and code of the old project never reach the new project. The one exception is the export in
   stage 2, done under sdd-export's own rules and only after the maintainer agreed. In the new project, read only
   the constitution (`.specify/memory/constitution.md`), `spec.md` files under `specs/` and `.sdd-rebuild/lineage.json`,
   when a stage tells you to.
2. **Never write to the old project.** Outside the confirmed export of stage 2, never create, change or delete
   anything in the old project, and never run any command there (git included): the old project may be the
   maintainer's working copy.
3. **Nothing is generated before the maintainer confirms.** Until the maintainer confirms the final summary in
   stage 8, never invoke any `speckit-` skill, never run `claim`, `lineage` or `focus`, and never change the new
   project's constitution, a spec or `.sdd-rebuild/`. The only write before that confirmation is `save`, which keeps
   the progress in `.specify/sdd-rebuild/` (the confirmed export of stage 2 writes the old project, not this one).
4. **Spec Kit writes the documents.** The constitution is generated only by the `speckit-constitution` skill and
   each spec only by the `speckit-specify` skill. Never write, complete or delete them by hand, and never create a
   spec folder yourself. The only edit you make to a generated document is removing a statement that has no basis
   in the confirmed summary, or marking it as to be confirmed (stages 9 and 10). Never edit `.specify/feature.json`,
   anything in `.sdd-rebuild/` or the progress file yourself; the script does that.
5. **The script composes the lineage.** `origin`, `revised`, `derived_from`, `source`, `spec`, `spec_dir` and the
   discard records are computed by the script from the nutrients and your decisions. In the progress you record only
   the decisions (`basis`, `from`, `discards`) and the content (titles, texts, summaries, kinds); see "The progress".
6. **Questions.** When the maintainer has to decide, use AskUserQuestion. Put the option you recommend first, mark
   it "(Recommended)" and give the reason. Ask one decision per question. Yes-or-no questions of the same kind (such
   as "which lessons no longer apply") may be one question with multiSelect. If AskUserQuestion is not available,
   ask in plain text, still one question at a time and with your recommendation. A path is free text: ask for it
   in plain text.
7. **Language.** Talk with the maintainer in the language their settings ask for. The generated documents are in
   Traditional Chinese, with normative words such as MUST and SHOULD kept in English, unless the new project's
   existing constitution or specs are in another language; then use that language. Record the choice in the
   progress `language` (for example `"zh-TW"`). The progress and the lineage keep the nutrients' Traditional
   Chinese text whatever the documents' language.
8. **Secrets stay out.** No password, key, token or credential value may appear in the conversation, the progress,
   the generated documents or the lineage. If one matters, record only what is needed ("needs an API key for the
   payment service, supplied at run time"). `save` refuses text that looks like a secret.
9. **Save after every decision.** After every decision, give the whole progress to `save` on stdin with a quoted
   heredoc, so that the shell changes nothing in it:

   ```text
   uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_rebuild.py" save <<'SDD_REBUILD_PROGRESS'
   { ...the whole progress... }
   SDD_REBUILD_PROGRESS
   ```

   An interrupted session then continues from the last decision. Never write the progress file any other way.
10. **If the maintainer asks to stop before confirming**, at any stage: make sure the latest decisions are saved,
    tell them that running `/sdd-rebuild` again continues from here (or offers to start over), that nothing is
    generated, and stop.
11. **No commits, no push.** Commit the generated documents and the lineage only when the maintainer asks you to.
    Never run anything that changes the old project's `.git/`. Never push.
12. **Unexpected results.** If the script gives an exit code or a `reason` that no outcome of the current stage
    mentions, or it cannot run at all (for example `uv` is not installed, or the output is not JSON), tell the
    maintainer what happened, show `error`, say what is written so far (from the last `check`: the saved progress
    and its `phase`, which documents were generated, whether the lineage is written), and stop.

## The progress

The progress is a JSON object that you build and give to `save`. Start from the progress `check` shows in `saved`
(when there is one), change what was decided, and send it whole. Fields:

| Field | What you put there |
|---|---|
| `schema`, `tool` | `1`, `"sdd-rebuild"` |
| `old_project` | `old.path` from `check`; never changes |
| `language` | the documents' language (rule 7); may be `null` until stage 8 |
| `phase` | `"deciding"`, then `"confirmed"` once the maintainer confirms (stage 8) |
| `stage` | `"items"` (stages 3 to 5), `"new"` (stage 6), `"lessons"` (stage 7), `"summary"` (stage 8 and later) |
| `old_lineage` | `"used"`, `"not-needed"` or `"skipped"`, as stage 3 decides |
| `constitution` | `{"action": "create" \| "amend" \| "keep", "governance": [text]}` (stage 4); `governance` holds governance rules for the constitution |
| `target` | `{"principles": [...], "features": [...], "lessons": [...]}`: the decided items, see below |
| `discards` | `[{"id": ..., "text": null or a short summary, "reason": null or the maintainer's reason}]`: items of the nutrients that are dropped |
| `pending_decided` | ids of the nutrients' `pending` items the maintainer has decided about |
| `adjustments` | `[{"lesson": lesson id, "change": text, "adopted": true \| false \| null}]` (stage 7) |
| `deferred` | `[{"item": text, "reason": text, "feature": feature id or null}]` |
| `for_plan` | `[{"item": text, "feature": feature id or null}]`: technology choices left to the plan |
| `generation` | `{"constitution": "pending" \| "written" \| "reviewed" \| "not-needed"}`; `"not-needed"` when the action is `keep`, otherwise `"pending"` until stage 9 |

The script adds `source` (a snapshot of the nutrients and the old lineage, taken at the first `save`), `rebuilt_at`,
`saved_at`, `fingerprint`, `baseline` and `lineage_written`; whatever you send for them is ignored.

Items of `target`. Every item has `id`, `basis` and `from`:

- `"basis": "inherit"`, `"from": []`: an item of the nutrients with the same `id` and kind, kept. Its content fields
  may be `null` (keep the old content) or new text (modified; the script marks the change in `revised`).
- `"basis": "derived"`, `"from"`: the ids it comes from, in the order the maintainer gives: a merge (two or more
  sources of the same kind) or a split (one source). It needs a new `id` and its own content.
- `"basis": "new"`, `"from": []`: added in this rebuild, with a new `id` and its own content.

Content fields by kind: principles `title`, `text`; features `title`, `summary`, plus `depends_on` (ids of features
listed before it), `existing_spec` (`null`, or `specs/<name>` of an existing spec it is matched to in stage 4),
`spec_dir` (`null`; only `claim` sets it, and once set, send it back exactly as `check` shows it), `reviewed`
(`false` until stage 10 compares its spec), `requirements` (at least one); requirements `kind` and `text`; lessons
`kind`, `title`, `text`. `kind` is one of `story`, `functional`, `edge-case`, `success-criterion`, `assumption` for
requirements and `decision`, `pitfall`, `reversed` for lessons. A new `id` is lowercase letters and digits joined by
single hyphens, and must not repeat any id the nutrients or their history ever used; `preview` tells you when one
does. The order of `target.features` is the order the specs are generated in: features matched to existing specs
first, then every feature after the features it depends on. No text may hold a code block.

Every item of the nutrients must end up somewhere: kept (`inherit`), named in some item's `from`, or in `discards`.
When a feature is discarded, its requirements are discarded too (each in `discards`) unless the maintainer moves
some of them to another feature.

What `save` may answer at any stage, besides the outcomes each stage lists:

- `invalid` or `secret`: the progress you sent breaks a rule; `path` names the field (`errors` lists the problems
  when you confirmed). Fix it and save again; when the fix changes content, ask the maintainer about that item.
- `frozen`: you changed confirmed content (or used `--refresh-source` after the confirmation). Take the values from
  `saved` in `check`, keep only what may still change (see stage 9), and save again.
- `finished`: the lineage is already written; nothing more is saved. Run `check` and continue from its `next`
  (stage 13).
- `conflict`: handle it like `progress` `"conflict"` in stage 1.
- `os-error`: the progress could not be written; see the `os-error` outcome of stage 3.
- After the confirmation, `invalid` with `errors` whose `check` is `existing-spec`: an existing spec that a feature
  is matched to was removed or moved. That cannot be fixed in the progress; handle it like `existing-spec-missing`
  in stage 11.

When `preview`, `claim`, `verify`, `lineage` or `focus` answers `no-progress`, the progress is missing or not
confirmed where it should be (for example it was cleared in another window): run `check` and continue from stage 1
with its result.

## Stage 1: Start

If the maintainer gave a path after `/sdd-rebuild`, run `check` with it; otherwise run it without `--old`. Run it
before anything else: before reading any file and before asking anything.

```text
uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_rebuild.py" check --old "<old project path>"
```

When there is no path and no saved progress, `check` ends with `old-required`: ask the maintainer for the old
project's path in plain text. Do not search for it, and do not guess it from folder names; then run `check` again
with `--old`.

Outcomes. In every outcome that stops, nothing was written by this run (a saved progress stays as it was); say so.
Do not try to work around a problem by writing, moving or deleting anything yourself.

- Exit code 0 and `progress` is `"conflict"`: `.specify/sdd-rebuild/` holds files this skill did not create. List
  its entries (names only, with Glob on `.specify/sdd-rebuild/*`; do not open them), ask the maintainer to move them
  away and run `/sdd-rebuild` again. Nothing was written. Stop.
- Exit code 0 and `progress` is `"present"`: a rebuild is under way; go to "Resuming".
- Exit code 0, no progress, `export_dir` is `"ours"`: the old project has nutrients; go to stage 3.
- Exit code 0, no progress, `export_dir` is `none` or `empty`: the old project has no nutrients yet; go to stage 2.
- `reason` is `progress-unreadable`: the saved progress cannot be read (it was probably edited by hand). Ask: clear
  it and start over (recommended), or stop so the maintainer can look at `.specify/sdd-rebuild/progress.json`. To
  clear, run `clear` and then run `check` again with the same `--old`; if `clear` answers `conflict`, handle it like
  `progress` `"conflict"` above. Stopping writes nothing.
- `reason` is `old-mismatch`: the saved progress belongs to another old project. Show both paths:
  `saved.old_project` (the progress) and `old.path` (the path given now). Ask: continue with the progress's old
  project (recommended; run `check` again without `--old` and go to "Resuming"), or clear the progress and start
  over with the new path (run `clear`, then `check --old` with the new path). Do not offer the second option when
  `saved.lineage_written` is not `null`: the lineage is written and the rebuild must be finished, not restarted.
  If documents were generated already, say that they stay and count as existing content when starting over.
- `reason` is `dependency`: the skills this one relies on are not installed next to it. List `missing` (sdd-export,
  sdd-grill or both) and ask the maintainer to deploy the skills again (the settings repository's
  `tools/deploy.py` installs them together). Nothing was written. Stop.
- `reason` is `speckit-missing`: the new project has no Spec Kit. Ask the maintainer to run `/sdd-init` in it
  first. Nothing was written. Stop.
- `reason` is `speckit-incomplete`: Spec Kit lacks files needed to generate documents. List `missing`, explain that
  Spec Kit may have changed incompatibly, and recommend `/sdd-update`. Nothing was written. Stop.
- `reason` is `old-required`: ask for the old project's path, as described above.
- `reason` is `old-missing` or `old-not-folder`: the path does not exist or is not a folder. Show `old.path`, ask
  the maintainer to check the path and run `/sdd-rebuild` again. Nothing was written. Stop.
- `reason` is `same-project`, `old-inside-new` or `new-inside-old`: the old project is this project, or one
  contains the other; writing in one would then change the other. Explain which, with both paths. Nothing was
  written. Stop.
- `reason` is `rebuilt`: this project was rebuilt already (read `generation` from `.sdd-rebuild/lineage.json` to say
  which generation it is). A project is rebuilt only once: to add requirements, use `/sdd-grill`; to make the next
  generation, run `/sdd-export` in this project and rebuild into another new project. Nothing was written. Stop.
- `reason` is `rebuild-conflict`: `.sdd-rebuild/` cannot be used by this skill. List `rebuild_conflicts` (files it
  did not write); when the list is empty, `.sdd-rebuild/lineage.json` cannot be read or does not match the lineage
  format. Ask the maintainer to deal with it. Nothing was written. Stop.
- `reason` is `nutrients-conflict`: the old project's `.sdd-export/` holds files sdd-export did not create. List
  `conflicts` (paths in the old project) and ask the maintainer to deal with them in the old project. Nothing was
  written. Stop.
- `reason` is `nutrients-unreadable` or `nutrients-invalid`: the old project's nutrients cannot be read or do not
  match the format. List the field paths in `nutrients_errors`, and ask the maintainer to fix the nutrients or run
  `/sdd-export` again in the old project. Nothing was written. Stop.
- `reason` is `nutrients-newer`: the nutrients come from a newer sdd-export. Ask the maintainer to update the skills
  (deploy the settings repository's `home/` again). Nothing was written. Stop.
- Any other exit code or `reason`: rule 12.

## Stage 2: Exporting the old project

The old project has no nutrients (`export_dir` is `none` or `empty`). They can be exported from here, by following
sdd-export's own instructions; doing so writes `.sdd-export/` into the old project, and nothing else.

First, if `export_skill` from `check` is `false`, the sdd-export skill is not installed next to this one: tell the
maintainer that it must be deployed for the export, that nothing was written, and stop.

Otherwise explain that the old project has no nutrients yet; that you can export them now by following sdd-export's
rules; that this writes the old project's `.sdd-export/` folder and only that folder; and that the maintainer
confirms before and after (sdd-export shows the whole draft before writing). Then ask one question: export now
(recommended), I will run `/sdd-export` in the old project myself and come back, or stop.

To export, use Read on `${CLAUDE_SKILL_DIR}/../sdd-export/SKILL.md` and follow its "Rules for the whole run" and its
Stage 1 to Stage 9 exactly, with only these substitutions. Every other rule of that file applies as written:
secrets (never open `secret_files`, never repeat what `secret_hits` points at), read-only, the git allowlist, one
question per decision, no commits.

- The script is `${CLAUDE_SKILL_DIR}/../sdd-export/scripts/sdd_export.py`, and every command gets
  `--project "<old.path>"`, where `<old.path>` is `old.path` from `check` (for example
  `uv run "${CLAUDE_SKILL_DIR}/../sdd-export/scripts/sdd_export.py" check --project "<old.path>"`).
- The paths that `files` and `check` print are relative to the old project. Give Read and Grep one
  `<old.path>/<path>` at a time, and only for the paths sdd-export's rules let you read (those `files` lists, and
  `.sdd-export/README.md` where its Stage 7 allows it). Glob is allowed only where sdd-export's Stage 2 allows it,
  for folder names under `<old.path>`.
- Git: only the four forms in sdd-export's allowlist, each with `-C "<old.path>"` added right after `git` and
  nothing else added or changed.
- "The project" in that file means the old project. While exporting, write nothing at all in the new project, not
  even `save`.
- Replace sdd-export's Stage 9: report where `.sdd-export/` is and the counts from `write`, say that the maintainer
  may commit it in the old project (their decision), then come back here and run `check --old "<old.path>"` (stage 1
  again). Do not suggest running `/sdd-rebuild`: it is already running.

Outcomes:

- The maintainer chooses to stop (at the question above, or during the export before sdd-export's confirmation):
  nothing was written in either project and nothing is saved; say so and stop.
- The maintainer will export in the old project themselves: tell them to run `/sdd-export` in the old project and,
  when it is done, run `/sdd-rebuild <old project path>` here again. Nothing was written. Stop.
- The export stops on one of sdd-export's own outcomes (a conflict, a project too large without a chosen scope, too
  little to export, and so on): report it as sdd-export's instructions say; nothing was written in the new project.
  Stop.
- sdd-export's `write` succeeds: run `check --old "<old.path>"`. If `export_dir` is `"ours"`, go to stage 3;
  otherwise follow the outcome of stage 1 for what `check` reports.
- The session is interrupted during the export: sdd-export keeps no progress and nothing was saved here (no `save`
  during the export), so running `/sdd-rebuild` again starts at stage 1; if `.sdd-export/` was already written, it
  is read as nutrients.

## Stage 3: Reading the nutrients

Use only the `nutrients` object of the `check` output. Never read the old project's files, not even
`.sdd-export/nutrients.json` itself. If `nutrients_edited` is `true`, tell the maintainer that the nutrients were
edited by hand after the export (they still passed sdd-export's checks).

If `nutrients.scope.coverage` is `"partial"`, the nutrients cover only part of the old project: list
`scope.included` and ask: complete the export in the old project first (recommended), or continue with this part.

Then look at `old_lineage` and `needs_old_lineage` from `check`. The old project's lineage (its
`.sdd-rebuild/lineage.json`) carries the sources of earlier merges and splits; the script uses it to keep the chain
of `derived_from` unbroken. Record the result in the progress `old_lineage`:

- `old_lineage` is `"present"`: the lineage is used; record `"used"`; after the summary below and the first save, go to stage 4.
- `old_lineage` is `none` and `needs_old_lineage` is `false`: the old project is the first generation and has no
  lineage; record `"not-needed"`; after the summary below and the first save, go to stage 4.
- `old_lineage` is `none` and `needs_old_lineage` is `true`: the nutrients are generation 2 or later, but the
  lineage was removed after the export; sources that only it records would be lost, and those ids could later be
  reused. Ask: stop and restore `.sdd-rebuild/lineage.json` in the old project from its git history (recommended),
  or continue with the nutrients only (record `"skipped"`).
- `old_lineage` is `"mismatch"`: the lineage is of another generation than the nutrients. Ask: stop and check that
  both belong to the same project (recommended), or continue with the nutrients only (`"skipped"`).
- `old_lineage` is `unreadable` or `invalid`: list `old_lineage_errors` (field paths). Ask: stop and fix it
  (recommended), or continue with the nutrients only (`"skipped"`).
- `old_lineage` is `"newer"`: it comes from a newer sdd-rebuild. Ask: stop and update the skills (recommended), or
  continue with the nutrients only (`"skipped"`).
- `old_lineage` is `"conflict"`: the file was not written by sdd-rebuild. Ask: stop and check it (recommended), or
  continue with the nutrients only (`"skipped"`).
- The maintainer chooses to stop at any of these questions: nothing was written (there was no `save` yet); tell
  them to run `/sdd-rebuild` again once it is dealt with. Stop.
- The maintainer chooses to continue with the nutrients only: record `old_lineage` as `"skipped"`; the final
  summary (stage 8) and the final report (stage 13) both say so and what it means. After the summary below and the
  first save, go to stage 4.
- For a `"partial"` scope, the maintainer chooses to complete the export first: either they run `/sdd-export` in the
  old project for the other areas and then `/sdd-rebuild` again here (stop now; nothing was written), or the export
  is done from here: go to stage 2 (it starts from the existing nutrients).

Present the nutrients to the maintainer: the principles; the features with their requirements counts and what each
depends on; the lessons; the `pending` items (marked "to be confirmed" in the old project: they are not facts until
the maintainer decides); and the suggested order of the specs (the order of `nutrients.features`, which follows the
dependencies).

Then save the first progress: `phase` `"deciding"`, `stage` `"items"`, `old_lineage` as decided, `language` `null`
(or decided already), `constitution` `{"action": "create", "governance": []}` for now (stage 4 decides), an empty
target, empty lists, and `generation` `{"constitution": "pending"}`, that is `"phase": "deciding"` with
`"stage": "items"`. This first `save` takes the snapshot of the nutrients; from now on everything is decided against
that snapshot.

Outcomes of this `save`:

- The save succeeds (`snapshot` is `"created"`): go to stage 4.
- `reason` is `source`: the nutrients changed or disappeared in the meantime. Run `check` again and start over from
  stage 1 with its result.
- `reason` is `conflict`: handle it like `progress` `"conflict"` in stage 1.
- `reason` is `os-error`: the new project cannot be written, so the progress cannot be kept. Ask: stop
  (recommended), or continue without saving (an interruption then loses every decision). Any later `save` that
  fails the same way gets the same question. Without a saved progress nothing can be generated: the decisions can
  go on up to the final summary, but the confirmation in stage 8 is itself a `save`; if it still fails there, show
  the summary so the maintainer keeps it, and stop.
- `reason` is `invalid` or `secret`: fix the progress you sent (the `path` names the field) and save again.

## Stage 4: What the new project already has

Look at `constitution` and `specs` from `check`.

- `constitution` is `"written"`: the new project already has a constitution. Read `.specify/memory/constitution.md`
  and compare it principle by principle with the nutrients' principles; present the differences. By default it is
  kept as it is (`"action": "keep"`, `generation` `"not-needed"`); if the maintainer agrees to amend it with the
  missing or different principles, use `"amend"` (`generation` `"pending"`). The nutrients' principles are still
  decided in stage 5: those the constitution already covers stay in the lineage (they hold in this generation).
- `constitution` is `"missing"` or `"template"`: there is none yet; the action is `"create"`.
- `specs` is not empty: the new project already has specs. Read each `spec.md` and compare it with the nutrients'
  features. For each feature that matches an existing spec, ask one question: match it to that existing spec
  (it then gets `existing_spec` `"specs/<name>"`, and no new spec is generated for it), generate a new spec, or
  discard it. Never change or overwrite an existing spec. Features matched to an existing spec come first in
  `target.features` (their numbers are lower); add each of them to the target now, as kept, with its requirements;
  stage 5 still goes through their content. Existing specs that match no feature are left alone; they are not part
  of the lineage.
- Neither: skip this stage and go to stage 5.

Outcomes:

- Everything here is decided: save (with the constitution action and any matched features) and go to stage 5.
- The maintainer wants to change an existing spec: explain that this skill never changes existing specs; recommend
  doing it after the rebuild with `/sdd-grill` or by hand; then ask whether the feature is matched to the existing
  spec or gets a new spec.

## Stage 5: Deciding item by item

First ask one question: keep everything as it is, or go through it item by item. When the nutrients have `pending`
items, the first option is "keep everything else as it is", and the pending items are still asked one by one.

Keep everything: put every principle, feature (with its requirements, `depends_on` copied) and lesson that is not in
the target or in `discards` yet (stage 4 may have placed some) into the target with `"basis": "inherit"` and
`null` content, then handle the pending items below.

Item by item: go through the principles, then the features (each with its requirements), then the lessons, in this
order, one item per question, each with your recommendation. The choices for an item are:

- keep it as it is (`"basis": "inherit"`, content `null`);
- modify it (`"basis": "inherit"` with the new title, text, summary or kind);
- merge it with other items of the same kind (one new item, `"basis": "derived"`, `from` listing the merged ids in
  the order the maintainer gives; the merged items are not discarded separately);
- split it (several new items, each `"basis": "derived"` with `from` naming it; when the maintainer also keeps the
  original, the original stays as `"basis": "inherit"`);
- discard it (an entry in `discards`, with the maintainer's reason if they gave one).

For a feature, present its requirements with it. They follow the feature's decision unless the maintainer wants
something else for one of them; a requirement of a merged feature is kept under the new feature, merged, or
discarded. Keep `depends_on` pointing at features that remain: a dependency on a merged feature becomes a
dependency on the merged result, and one on a discarded feature is dropped (say so). You propose new ids; when
`preview` later answers `id-taken` for one, choose a new id and tell the maintainer.

Pending items: every item the nutrients mark `pending` gets its own question, one item each, even when "keep
everything" was chosen: keep it as a fact, modify it, or discard it (then take it out of the target and add it to
`discards`). After the decision add its id to `pending_decided`. Never record a pending item as a fact without that
decision.

After every decision, save (`"stage": "items"`).

Outcomes:

- Every item has a decision: go to stage 6.
- The maintainer changes an earlier decision: change that item in the target (or in `discards`) and save; do not
  go through the other items again.
- Two decisions contradict each other, or a decision conflicts with a principle that is kept: quote both sides and
  ask the maintainer which one wins (one question).
- The maintainer asks to stop: rule 10.
- `save` answers `invalid` or `secret`: fix the progress at the `path` it names (a secret becomes a description of
  what is needed); when the fix changes content, ask the maintainer to confirm that item; then save again.

## Stage 6: New requirements

Ask whether this generation adds new requirements. If it does, use Read on
`${CLAUDE_SKILL_DIR}/../sdd-grill/SKILL.md` and apply its section "Rules for questioning" to each new requirement
until it is settled: one question at a time with a recommendation, no vague answers, contradictions pointed out,
technology choices recorded in `for_plan` rather than discussed, secrets never recorded. Use only that section: not
what the file says about sdd-grill's own progress, commands or document generation.

A settled requirement is added with `"basis": "new"`: a new feature (with its requirements) placed after the
features it depends on, or a new requirement inside an existing feature. Record technology choices in `for_plan` and
whatever is decided later in `deferred`. After every decision, save (`"stage": "new"`).

Outcomes:

- There is no new requirement, or every new requirement is settled: go to stage 7.
- A new requirement overlaps an existing feature: point out the overlap and ask: fold it into the existing feature
  (a modification of that feature) or make it a feature of its own.
- The maintainer asks to stop: rule 10.

## Stage 7: Adjustments from the lessons

Go through the lessons and propose the adjustments they suggest (a new principle, a changed requirement, and so
on). Record each in `adjustments` with the lesson it comes from (`lesson`), `change` and `"adopted": null`, then ask
about each one in its own question, naming the source lesson. If adopted, set `"adopted": true` and make the change
in the target; if not, set `false`. Never change a principle or a requirement because of a lesson unless the
maintainer agreed to that adjustment.

Also decide whether each lesson still applies: lessons that do stay (`"basis": "inherit"`); lessons that no longer
apply go to `discards`. If stage 5 already went through the lessons one by one, that is decided; otherwise ask one
question with multiSelect: which lessons no longer apply.

Outcomes:

- Every adjustment and lesson is decided: save (`"stage": "lessons"`) and go to stage 8.
- An adjustment contradicts a kept principle or another decision: quote both sides and ask the maintainer which one
  wins.
- There is no adjustment to propose: say so plainly, save (`"stage": "lessons"`) and go to stage 8.

## Stage 8: Final summary and confirmation

Set `language` (rule 7) if it is still `null`, save with `"stage": "summary"`, then run `preview`:

```text
uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_rebuild.py" preview
```

`preview` composes the lineage from the saved progress and checks it; it writes nothing. Its errors are exactly the
problems that would make the lineage wrong or make the next `/sdd-export` of the new project fail, so they are fixed
here, before anything is generated.

Present the summary from `preview`'s `summary`, completely:

- `kept`, `modified` (say what changed), `merged` and `split` (with the ids they come `from`), `discarded` (with the
  reason), `added`;
- the decisions about the pending items (`pending_decided`);
- the `adjustments`, adopted and not adopted, each with its lesson;
- the constitution's `action` (create, amend, or keep the existing one);
- the order of the specs (`order`), with what each depends on and which features are matched to existing specs;
- the documents' language;
- when `old_lineage` is `"skipped"`: that the old lineage was not used, so sources only it recorded are lost.

Then ask one question: confirm and generate (recommended), change something, or stop.

Outcomes:

- `ok` is `false`: fix the target according to `errors` (each has `check`, `path` and `detail`):
  `unaccounted` means an item of the nutrients has no decision (ask about it); `id-taken` means a new id was used
  before (choose another id and tell the maintainer); `pending-undecided` means a pending item has no decision (ask
  about it); `inherit-unknown`, `from-unknown` and `discard-conflict` mean an id in the target is wrong or an item
  is both kept and discarded; `existing-spec` means a match to an existing spec is wrong or out of order. Ask one
  question per decision the maintainer has to make, save, and run `preview` again.
- `errors` holds `next-export` or `lineage-format`: the composed lineage disagrees with sdd-export's rules although
  every decision is valid. That is a defect of sdd-rebuild, not something to fix in the decisions. Show the errors,
  ask the maintainer to report the problem, and stop without confirming. The progress stays saved.
- The maintainer confirms: save with `"phase": "confirmed"` (and `"stage": "summary"`). The first confirmed save
  answers `"baseline": true`: the script recorded the constitution and the specs as they are now, so that `verify`
  can later prove they were not touched. Go to stage 9.
- That save answers `invalid` (with `errors`): the progress changed after the preview; run `preview` again and
  present the summary again.
- The maintainer wants to change something: go back to the stage that holds it (stage 5 for items, 6 for new
  requirements, 7 for adjustments), save, and come back to `preview`.
- The maintainer asks to stop: rule 10.

## Stage 9: The constitution

From here on the confirmed content does not change: the target, the discards, the decisions about pending items and
adjustments, and the constitution action are frozen (`save` answers `frozen` if they change). After the
confirmation, `constitution.governance`, `deferred` and `for_plan` can only grow: new entries are added after the
existing ones.

When the action is `create` or `amend`, use the Skill tool to invoke `speckit-constitution`. As its argument, give
only the confirmed principles (title and text, as `preview` showed them) and the governance rules, in the
documents' language, and tell it to use only these and not to infer other principles from the repository. For
`amend`, give only the additions and changes and say that everything else stays as it is. When it returns, save
with `generation` `"written"`.

Then read `.specify/memory/constitution.md` and compare it with the summary in both directions:

- Every confirmed principle and governance rule must be in it. If one is missing, invoke `speckit-constitution`
  once more with only the missing ones, saying that everything else stays as it is, and compare again.
- Every rule in it must come from the summary (for `amend`, the rules that were already there stay as they were).
  Remove a rule that has no such basis. If you think it is worth keeping, ask the maintainer (one question per
  rule); keep it only if they agree, and add it to `constitution.governance` so that later comparisons do not ask
  again. Such a rule was added after the confirmation: it is not part of the lineage, and the final report names it.
  Spec Kit's own bookkeeping (version line, dates, sync report) is not a rule; leave it.

When the comparison is done, save with `generation` `"reviewed"`. When the action is `keep`, skip this stage:
`generation` is already `"not-needed"` and the constitution is not touched.

Outcomes:

- The comparison is done: go to stage 10.
- `speckit-constitution` fails or the session is interrupted: the progress keeps `generation` `"pending"` (nothing
  was written) or `"written"` (the comparison is still to do). Tell the maintainer what happened; running
  `/sdd-rebuild` again continues from there (see "Resuming"). Stop.
- A rule is still missing after the second call: report which parts are missing. Never add them by hand. Stop; the
  progress is kept and the next run continues with the comparison.

## Stage 10: The specs

For each feature of `target.features` whose `existing_spec` is `null`, in that order, one at a time:

1. Use the Skill tool to invoke `speckit-specify` with that feature only, as confirmed: its title and summary, its
   requirements by kind (stories, functional requirements, edge cases, success criteria, assumptions), what it
   depends on (by title, and by spec folder for features already generated or matched to existing specs), and, in
   the spec's Assumptions section, its `deferred` items with their reasons and its `for_plan` items as decisions
   left to the plan (items whose `feature` is `null` go with every spec they affect, or the first spec). Write in
   the documents' language. Never give it a number or a folder name: Spec Kit numbers each spec after the existing
   ones, and calling it one feature at a time in this order makes the numbers follow the order of work.
2. Right after it returns, and before invoking `speckit-specify` for the next feature, run `claim`:

   ```text
   uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_rebuild.py" claim <feature id>
   ```

   It finds the folder Spec Kit just created and records it as the feature's `spec_dir` in the progress.
3. Read `<spec_dir>/spec.md` and compare it with the summary. Spec Kit fills in sections its template requires and
   may infer details: remove statements that have no basis in the summary, or mark them as to be confirmed where a
   section must not be empty. If `speckit-specify` asks clarifying questions, answer from the summary; when the
   summary has no answer, ask the maintainer one question and give the answer to `speckit-specify`, so that it is
   written into the spec. When the answer also needs to be remembered (something deferred, or a choice for the
   plan), add it to `deferred` or `for_plan`. Never change the target: such an answer is added after the
   confirmation, is not part of the lineage, and the final report names it.
4. Save with the feature's `"reviewed": true` and its `spec_dir` exactly as `claim` recorded it.
   Then go to the next feature.

Outcomes:

- `claim` succeeds: compare (step 3), save, and continue with the next feature; once every feature is done, go to
  stage 11.
- `claim` answers `none`: `speckit-specify` did not produce a spec. List `incomplete` if it is not empty (folders
  without a `spec.md`; say that this skill does not delete them). Ask: invoke `speckit-specify` again for this
  feature (recommended), or stop. If it fails again, stop; the progress is kept.
- `claim` answers `ambiguous` or `mismatch`: there is more than one new spec folder, or the new one is not the one
  `.specify/feature.json` points at (`feature_directory`). List `candidates` and `feature_directory`, read each
  candidate's `spec.md` to judge which one is this feature's, and ask the maintainer (recommend the one that
  matches). Then run `claim <feature id> --dir <specs/name>` with their choice. The other candidates are extra
  folders for the maintainer to deal with; `verify` lists them as `unexpected`.
- `claim` answers `not-next`: the feature is not the next one to generate (the order went wrong). Run `check` and
  follow its `next`.
- The session is interrupted around `speckit-specify`: the next run's `check` shows `next.step` `claim` (the spec
  was generated but not recorded) or `specify` (it was not generated); continue from there without generating a
  spec twice.
- The number Spec Kit gave is not the expected one (for example a folder of the maintainer's sits in between):
  `claim` still records it; `verify` in stage 11 decides whether the order is acceptable.

## Stage 11: Verifying

When every feature is done, run `verify`, before the lineage:

```text
uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_rebuild.py" verify
```

It checks the existing documents were not touched, the constitution is written as decided, every feature has its
spec, the numbers follow the order and the dependencies, and everything was compared. Each failure has `check` and
`detail`. When `failures` holds any `check` other than `not-reviewed`, handle those (each of them stops); only when
`not-reviewed` is the only kind, continue as its outcome says.

Outcomes:

- `ok` is `true`: go to stage 12.
- `existing-spec-changed`, `constitution-changed` or `constitution-not-written`: a document that existed before, or
  the constitution, is not as decided (it was changed during the run). Show `detail`. Two ways out: restore it and
  run `/sdd-rebuild` again (recommended), or start over (see "Resuming"; the documents generated so far are kept
  and count as existing). Stop.
- `spec-missing`: a recorded spec folder lost its `spec.md` (for example it was deleted). Show it. Ways out: restore
  the file and run `/sdd-rebuild` again (recommended), or start over. Never generate it again: a new spec would get
  the last number and break the order. Stop.
- `spec-not-new`, `order` or `dependency-order`: the numbers do not follow the order (for example another spec was
  put in between). Show `detail`. Ways out: restore or move away the folders `detail` names and run `/sdd-rebuild`
  again, or start over. Stop.
- `existing-spec-missing`: an existing spec a feature is matched to was removed. Ways out: restore it and run
  `/sdd-rebuild` again, or start over. Stop.
- Only `not-reviewed`: a comparison is missing. Run `check` and continue from its `next` (stage 9 or 10).
- `unexpected` is not empty (with `ok` `true`): folders under `specs/` that belong to no feature. This is not a
  failure; name them in the final report for the maintainer to deal with. This skill will never delete them.

## Stage 12: The lineage

Run `lineage`:

```text
uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_rebuild.py" lineage
```

It checks the documents again, composes the lineage, checks it with sdd-export's own rules, and writes
`.sdd-rebuild/lineage.json` (and `.sdd-rebuild/.gitattributes`, which keeps it LF on every platform).

Outcomes:

- It succeeds (also with `"unchanged": true`, when an earlier run wrote the same lineage before being interrupted):
  go to stage 13.
- `mismatch-documents`: the documents changed since `verify`; handle `failures` as in stage 11.
- `lineage-changed`: `.sdd-rebuild/lineage.json` exists with other content (perhaps it was put there by hand). Show
  it; never overwrite or change it yourself. Ask the maintainer to look at it. Stop.
- `rebuild-conflict`: `.sdd-rebuild/` holds something this skill did not write (`rebuild_conflicts`). Show it. Stop.
- `invalid` (with `errors`): the confirmed progress cannot change, so this means the progress file was edited by
  hand. Show `errors`. Stop.
- `internal` (with `errors`): sdd-export does not accept the composed lineage. This is a defect of sdd-rebuild: the
  lineage was not written, and the generated documents stay. Show `errors` and ask the maintainer to report it.
  Stop.
- `os-error`: the lineage could not be written (or is the same as before). Show `error`; once the cause is fixed,
  running `/sdd-rebuild` again continues with this step. Stop.

## Stage 13: Finishing

Before clearing the progress, keep what the report needs: the output of `verify` (or run `check` and `verify`
again), the `lineage` output, and the saved progress (`baseline.confirmed_counts` tells how many entries
`constitution.governance`, `deferred` and `for_plan` had at the confirmation; the entries after those were added
later). Then run `focus`, and after it `clear`:

```text
uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_rebuild.py" focus
uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_rebuild.py" clear
```

Outcomes:

- `focus` succeeds: `.specify/feature.json` now points at the first generated spec (`feature_directory`; `null` when
  every feature was matched to an existing spec, and then the file is not changed). Run `clear`, then report.
- `focus` answers `mismatch-documents`: the documents were changed after the lineage was written. The ways out are
  those of stage 11, except that you never offer to start over (the lineage is written; this project is rebuilt):
  restore what `failures` names and run `/sdd-rebuild` again. Stop.
- `focus` answers `not-regular`: `.specify/feature.json` is not a regular file. Report it and ask the maintainer to
  fix it; running `/sdd-rebuild` again continues with `focus`. Stop.
- `clear` answers `conflict`: report as usual, and add that `.specify/sdd-rebuild/` holds files this skill did not
  create, for the maintainer to deal with.

The final report, after `clear`:

- every spec with its folder, in order, what it depends on, and which features were matched to existing specs;
- which spec `.specify/feature.json` points at;
- the lineage: `.sdd-rebuild/lineage.json`, its generation; that `.sdd-rebuild/lineage.json` (with
  `.sdd-rebuild/.gitattributes`) MUST be committed to the repository, because the next `/sdd-export` of this
  project needs it; committing is the maintainer's decision, so do not commit unless they ask;
- when `old_lineage` was `"skipped"`: that the old lineage was not used and sources only it recorded are lost;
- the `unexpected` folders, if any (this skill did not delete them);
- what was added after the confirmation (constitution rules the maintainer kept in stage 9, answers written into a
  spec in stage 10, and the entries of `governance`, `deferred` and `for_plan` added then): it is in the documents
  but not in the lineage, so the next `/sdd-export` treats it as new in this generation;
- the next step: the maintainer types `/sdd-drive` in the main session to start the plan and the implementation.

When no spec was generated (every feature was matched to an existing spec), say that `.specify/feature.json` was not
changed and that what comes next depends on those specs; then do not suggest `/sdd-drive`.

After the report, stop. You suggest `/sdd-drive` but never run it yourself, and never start the plan, the tasks or
the implementation; do not commit or push.

## Resuming

`check` found a saved progress. Show where the rebuild stands: the `phase`, the `stage`, how many items of the
nutrients are decided (count what the target and `discards` cover; `preview` lists the rest as `unaccounted`), and
the next step (`next.step`). The nutrients to use are the snapshot in `saved.source.nutrients`, not `nutrients`.

What changed in the old project:

- `source_state` is `"unavailable"`: the old project or its nutrients cannot be read now. That does not matter: the
  snapshot has everything; continue.
- `source_changed` has `true`: the nutrients (or the old lineage) changed since the snapshot. Show `source_diff`
  (items added, removed and changed; for the lineage, say that it changed). While `phase` is `"deciding"`, ask:
  use the new nutrients (recommended; `save --refresh-source` with the current progress, then run `preview`: its
  `unaccounted`, `inherit-unknown` and `from-unknown` errors are the items to decide again, one by one; if the save
  answers `invalid` at `old_lineage`, the old lineage's state changed: decide it again as in stage 3 from `check`'s
  `old_lineage`), keep deciding against the snapshot, or start over (`clear`, then `check --old`). When `phase` is
  `"confirmed"`, say that the confirmed content follows the snapshot and continue without asking.

What changed in the new project (`changed`): while `phase` is `"deciding"` and `constitution` or `specs` changed, do
the comparison of stage 4 again for what changed. When `phase` is `"confirmed"`, leave it to `verify`.

Then continue from `next.step`:

- `decide`: ask: continue (recommended) or start over (`clear`, then `check --old`). To continue, go to the stage of
  `saved.stage`: `items` stage 4 (quick when the new project has no constitution or specs; keep what the progress
  already records) and then stage 5, `new` stage 6, `lessons` stage 7, `summary` stage 8.
- `constitution`: confirmed, but the constitution is not generated yet. Ask: continue generating (recommended), go
  back to the discussion (only possible now, before anything is generated: save with `"phase": "deciding"`, then go
  to stage 8 to change and confirm again), or start over (`clear`). To continue, go to stage 9.
- `review-constitution`: the constitution was generated but not compared. Continue with the comparison of stage 9;
  do not invoke `speckit-constitution` again for what is already there.
- `claim`: the spec of `next.feature` was generated but not recorded (`next.candidates` lists the new folders). Run
  `claim` for `next.feature` and continue as in stage 10; do not generate it again.
- `specify`: continue stage 10 with `next.feature`.
- `review`: continue stage 10 with the comparison (step 3) of `next.feature`.
- `verify`: go to stage 11.
- `focus` or `clear`: the lineage is written; go to stage 13. Do not offer to start over: it is no longer possible.

If documents were generated already (the constitution or a spec) and the maintainer wants to start over: explain
that the generated constitution and specs are kept, that the next rebuild treats them as existing content (stage 4
can match features to them), and that the lineage is not written yet; once they confirm, run `clear`. This is not
offered once the lineage is written.

If documents were generated already and the maintainer wants to change a decision: the confirmed content no longer
changes. Ask: finish as confirmed (recommended; change it afterwards with `/sdd-grill` or by hand), stop here and
keep the progress, or start over (as above).
