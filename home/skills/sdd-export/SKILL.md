---
name: sdd-export
description: Export an old project's principles, per-feature requirements and dependencies, lessons learned and generation information as nutrients in .sdd-export/, so that a new project can be reborn from them with /sdd-rebuild. Run it in the old project. It does not need Spec Kit, only reads the project, and writes nothing until the maintainer confirms the draft.
disable-model-invocation: true
argument-hint: "[scope path ...]"
---

# sdd-export

The maintainer wants to rebuild an old project as a new one. This skill collects what the new project should
inherit, the *nutrients*, and leaves them in the old project's `.sdd-export/` folder:

- the principles the project follows;
- each feature, its requirements (described as user needs and testable behaviour, never as implementation), and
  which features depend on which;
- the lessons of this generation: important decisions and their reasons, pitfalls, and approaches that were reversed;
- the generation: which generation this project is, and for every item the generation it first appeared in.

Later the maintainer runs `/sdd-rebuild` in a new project, which reads `.sdd-export/nutrients.json` and generates a
constitution and specs from it. The new project then records a lineage in `.sdd-rebuild/lineage.json`; when that
project is exported in turn, this skill reads the lineage so that inherited items keep their identity across
generations. That is why the format is strict: another tool parses it, and a broken chain of `id`s and `origin`s
cannot be repaired later.

The old project may be anything: with or without Spec Kit, with or without git, in any language. You work in two
modes. Reading the project, understanding it, describing its features and talking with the maintainer are your job.
Everything that can be decided mechanically is done by a script that prints one JSON object: the state of the
project and of `.sdd-export/`, the list of files you may read, the validation of your draft, and the one write at
the end. Always run it from the old project's root (the current folder), exactly like this:

```text
uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_export.py" check
uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_export.py" files [--scope <path>]...
uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_export.py" validate          (draft on stdin)
uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_export.py" write --expect <state>   (confirmed draft on stdin)
```

Every result has an exit code. 0 means success. 1 means the request was refused (`reason` says why: `usage`,
`invalid`, `secret`, `changed` or `os-error`). 3 means the project cannot be exported in its current state (`reason`
says why). On failure the JSON has `error`, one English sentence, and `reason`; react to `reason`, not to the
sentence.

The work goes through nine stages in order. Each stage below lists every outcome and what to do next. No outcome
leaves you without a next step; if something happens that no outcome describes, tell the maintainer what happened,
say that nothing was written, and stop.

## Rules for the whole run

These apply at every stage.

1. **Stay read-only.** Read the project only with read tools (Read, Grep, Glob), and only the files that `files`
   lists plus what `check` prints. Two narrow exceptions: Glob may list folder names when you help the maintainer
   pick a scope in stage 2, and you may read `.sdd-export/README.md` when stage 7 asks you to merge the
   maintainer's edits to it. Neither makes other files readable. The only commands you may run are this skill's script and read-only git
   commands: `git --no-pager log`, `git --no-pager show`, `git --no-pager ls-files` and `git --no-pager blame`. Never
   run a build, a test, a package install, a formatter, a code generator or any of the project's own scripts, even
   when it would answer a question quickly: they create files, and the maintainer was promised an untouched project.
   Never create or change a file in the project with Write, Edit or any other way, not even a temporary file. You
   give the draft to the script on stdin only, with a quoted heredoc so that the shell changes nothing in it:

   ```text
   uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_export.py" validate <<'SDD_EXPORT_DRAFT'
   { ...the draft... }
   SDD_EXPORT_DRAFT
   ```

2. **There is exactly one write.** The only thing that writes is `write`, after the maintainer confirmed the draft
   in stage 7. Never create or change anything in `.sdd-export/` any other way, and never change any file outside
   `.sdd-export/`.
3. **Spec Kit is not needed.** Never call any `speckit-` skill, and do not ask or suggest the maintainer to run
   `/sdd-init` first. When the project has `.specify/memory/constitution.md` and specs under `specs/`, you only read
   them.
4. **Secrets stay out.** Never open the files in `secret_files` (from `check` or `files`). The lines that
   `secret_hits` points at may hold credentials: never quote or repeat their values in the conversation, the draft
   or the nutrients. If a secret matters, record only its location (for example a doubt saying that a given file
   and line hold a hard-coded credential). No secret value may ever appear in the conversation.
5. **Questions.** When the maintainer has to decide, use AskUserQuestion. Put the option you recommend first and say
   why. Ask one decision per question. Yes-or-no questions of the same kind (such as "which earlier lessons no
   longer apply") may be one question with multiSelect, so the maintainer can select several answers; each doubt
   gets its own question, always. If AskUserQuestion is not available, ask in plain text, still one question at a
   time and with your recommendation.
6. **Language.** Talk with the maintainer in the language their settings ask for. Every text in the draft and the
   nutrients (titles, requirements, lessons, reasons) is in Traditional Chinese; keep normative words such as MUST
   and SHOULD in English, and keep file names, identifiers and proper names as they are. When a source document is
   in another language, translate it in the draft; the maintainer confirms the translation together with the draft.
7. **If the maintainer asks to stop before confirming**, at any stage: write nothing, tell them that nothing is
   saved and that running `/sdd-export` again starts over from the beginning, and stop.
8. **If the maintainer changes an earlier decision before confirming**: change that item in the draft and show the
   change again at the final confirmation. Do not reopen or go through the other decisions again.
9. **No commits.** Never run `git add`, `git commit`, `git push` or anything else that changes `.git/`. Whether the
   nutrients are committed is the maintainer's decision; you only tell them they can commit.
10. **Never invent.** Anything without evidence is marked `pending`; never make up a fact, a reason or a lesson to
    fill a gap.

## The draft

The draft is a JSON object that lives only in the conversation until stage 8. It has the format of
`nutrients.json` without the three fields the script fills in: leave out `tool`, `schema` and `exported_at` (the
script refuses a draft that has them). Key order does not matter; the script writes the file in a fixed order.
Array order does matter: it is kept as given.

Top level, every key required:

- `generation`: the number `check` reports in `generation`.
- `project`: the project's name, usually `project` from `check` (a name, not a path).
- `language`: always `"zh-Hant"`.
- `scope`: an object with `coverage` and `included`: `{"coverage": "full", "included": []}` for the whole project,
  or `{"coverage": "partial", "included": [<paths>]}` when only some areas are covered (see stage 2).
- `principles`, `features`, `lessons`, `discarded`: arrays. `features` needs at least one entry; the others may be
  empty.

Every principle, feature, requirement and lesson has:

- `id`: lowercase letters and digits joined by single hyphens, at most 64 characters, unique in the whole draft and
  never changed once it exists, across generations too;
- `origin`: the generation it first appeared in, from 1 to `generation`; lower than `generation` means inherited;
- `revised`: the later generations in which its content changed, strictly increasing, each greater than `origin`
  and at most `generation` (an item with `origin` equal to `generation` therefore always has `[]`);
- `derived_from`: the `id`s of earlier items it was merged or split from, usually `[]`.

Principles, requirements and lessons also have `status` (`"confirmed"` or `"pending"`) and `evidence` (an array).
A `confirmed` item needs at least one piece of evidence; a `pending` one may have none. Each piece of evidence is
one of:

- a path relative to the project root, with `/` (a file or a folder that exists, is in the `files` list or contains
  listed files, and is not a secret file); `.specify/memory/constitution.md` and `.sdd-rebuild/lineage.json` are
  allowed;
- `commit:<hash>`, with 7 to 40 lowercase hexadecimal characters, a commit that exists (only in a git repository);
- `maintainer`, when the maintainer told you in this conversation.

The kinds of item, with their own fields:

- principle: `id`, `origin`, `title`, `text`, `revised`, `derived_from`, `source` (`constitution`, `doc`, `code` or
  `maintainer`), `status`, `evidence`.
- feature: `id`, `origin`, `title`, `summary` (one paragraph on what the user can do), `revised`, `derived_from`,
  `source` (`spec`, `code`, `mixed` or `maintainer`), `spec` (the spec file such as `specs/001-x/spec.md`; required
  when `source` is `spec` or `mixed`, otherwise `null`), `depends_on` (`id`s of features listed before this one),
  `requirements` (at least one). List features so that every feature comes after the ones it depends on.
- requirement (inside its feature): `id`, `origin`, `kind` (`story`, `functional`, `edge-case`,
  `success-criterion` or `assumption`), `text`, `revised`, `derived_from`, `source` (`spec`, `code`, `doc` or
  `maintainer`), `status`, `evidence`.
- lesson: `id`, `origin`, `kind` (`decision`, `pitfall` or `reversed`), `title`, `text` (a decision includes its
  reason; a reversed approach includes why it was reversed), `revised`, `derived_from`, `status`, `evidence`.
- discarded item: `id` (the discarded item's `id`; a discarded doubt gets a new `id`), `kind` (`principle`,
  `feature`, `requirement`, `lesson` or `doubt`), `origin` (the item's `origin`; for a doubt, this generation),
  `discarded_in` (the generation it was discarded in), `text` (a short summary of what was discarded), `reason`
  (the maintainer's reason, in Traditional Chinese; when they gave none, write the Traditional Chinese for "the
  maintainer decided to discard it").

No string may be empty, no string may contain a code block (a line starting with three or more backticks or
tildes), and no object may have keys other than the ones above: there is no place for plans, tasks or code.

## Stage 1: Start

Run `check` as the very first thing, before anything else and before you read any project file:

```text
uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_export.py" check
```

It reports, without changing anything, whether `.sdd-export/` can be used, which generation this project is,
whether nutrients were exported before, which constitution and specs exist, and how much there is to read. Reading
files first would waste effort if the project cannot be exported, and could even mean reading a folder the
maintainer keeps their own files in.

Outcomes when the command fails or exits with 3. In all of them you have read nothing and written nothing; say so,
and do not try to work around the problem by writing or deleting anything yourself:

- `uv` is not installed, or the script cannot run (the command is not found, or the output is not JSON): tell the
  maintainer the skill needs `uv` installed and on the PATH, show the error, say that nothing was written, and stop.
- `reason` is `conflict`: `.sdd-export/` exists but holds things this skill did not create. List the paths in
  `conflicts`, explain that you will not overwrite or touch them, and ask the maintainer to move or rename them
  and run `/sdd-export` again. Nothing was written. Stop.
- `reason` is `nutrients-unreadable` or `nutrients-invalid`: the existing `.sdd-export/nutrients.json` cannot be
  read or no longer matches the format, usually after a hand edit. List the field paths in `errors` (for
  `nutrients-unreadable`, say the file is not valid UTF-8 JSON). Ask the maintainer to fix the file, or delete
  `.sdd-export/` themselves if they do not need it, and run `/sdd-export` again. Never overwrite it. Nothing was
  written. Stop.
- `reason` is `nutrients-newer` or `lineage-newer`: the nutrients or the lineage were written by a newer version of
  the tools. Ask the maintainer to update this skill and run it again; never guess at a newer format or overwrite
  it. Nothing was written. Stop.
- `reason` is `lineage-unreadable`, `lineage-invalid` or `lineage-conflict`: `.sdd-rebuild/lineage.json` cannot be
  used (it is not valid JSON, it breaks the lineage rules, whose field paths are in `errors`, or another tool wrote
  it). Explain which. Never treat the project as a first generation instead: that would cut the chain of
  generations. Ask the maintainer to fix the lineage and run `/sdd-export` again. Never overwrite or change the
  lineage yourself. Nothing was written. Stop.
- Exit code 1, or exit code 3 with any other reason: show `error`, say that nothing was written, and stop.

When `check` exits with 0, go through these in order; more than one may apply:

- `inventory.files` is 0: there is nothing you may read (everything is excluded: dependencies, build output, binary
  or secret files). Tell the maintainer, show the numbers in `inventory.skipped`, say that nothing was written, and
  stop.
- `writable` is `false`: the project looks read-only, so the write at the end may fail. You can still build and show
  the whole draft, which is worth having. Ask with AskUserQuestion: continue (recommended) or stop. Stop means rule
  7.
- `existing_generation` is not `null` and differs from `generation`: the existing nutrients were exported as another
  generation than the one this project is now. Show both numbers and the likely causes: the lineage was removed, or
  this project was copied from another project together with its `.sdd-export/`. Ask: stop and check first
  (recommended), or continue with `generation` from `check`. Stop means rule 7.
- `nutrients` is `"edited"` or `"unknown"`: the existing nutrients were changed after the last export (or that
  cannot be told, because `.sdd-export/README.md` is missing or was changed). Tell the maintainer. Treat whatever
  the file says now as the maintainer's decisions: stage 4 asks before changing any of it.
- In every case that continues: tell the maintainer which generation this export is (`generation`; when `lineage`
  is `"none"`, say the project counts as the first generation), whether nutrients already exist and this is a
  re-export (`export_dir` is `"ours"`), and whether a constitution and specs were found (`constitution`, `specs`).
  Keep `state` from this `check`: stage 8 needs it. Go to stage 2.

## Stage 2: Scope

Decide what to read before reading anything. A large project cannot be read in one conversation, and you must not
start reading before the maintainer has chosen a part of it.

- If the maintainer gave paths after `/sdd-export`, use them: run `files` with one `--scope` per path.
- If not, and `inventory.too_large` from `check` is `false`, run `files` without `--scope`.
- If not, and `inventory.too_large` is `true`, do not read or open any project file yet. Show `inventory.areas`:
  each area's path, number of files, size and package manifests. Ask with AskUserQuestion, with multiSelect so
  several areas can be chosen, which areas to export now; recommend one coherent area (for example the one with the
  main package manifest) and say why. Then run `files` with one `--scope` per chosen area.

```text
uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_export.py" files --scope <path> --scope <path>
```

`files` lists the readable files of the scope; the constitution and every `specs/*/spec.md` are always included,
because they are the first source of requirements. When the scope is not the whole project, the draft's `scope` is
`partial` and `included` lists the scope paths (as `files` reports them in `scope`). In a re-export whose existing
nutrients are already `partial`, `included` lists the earlier areas together with the new ones, and becomes
`{"coverage": "full", "included": []}` when the maintainer says the batches now cover the whole project. Tell the
maintainer that they can run `/sdd-export` again later for other areas, and that items outside the chosen scope are
kept as they are.

Outcomes:

- `files` succeeded and `too_large` is `false`: go to stage 3 with its `files`, `secret_hits` and `secret_files`.
- `files` exits with 1 and `reason` is `"usage"`: a scope path does not exist, is outside the project, or is
  excluded from reading (`error` names it). Tell the maintainer which path and why, and ask again which scope to
  use.
- `too_large` is still `true` for the chosen scope: the scope is still too large to read. Say so and ask the
  maintainer for a smaller scope; you may list the folder names inside the chosen area with Glob to offer choices.
- The maintainer refuses to narrow the scope: explain that the whole project cannot be read in one conversation
  and recommend exporting in batches: each confirmed batch is written and kept, and the next run adds to it. If they
  still decline, say that nothing was written and stop.
- The maintainer chooses to stop: rule 7 (nothing is saved).
- `files` exits with 3: the project changed since `check`; handle `reason` as the same outcome of stage 1.

## Stage 3: Reading

Read only the files in the `files` list. Always read the constitution and the specs it includes (`check` listed
them in `constitution` and `specs`). Never open a file in `secret_files`, and never repeat the values on the lines
in `secret_hits`. Read efficiently: the list may be long, so start with the constitution, specs, README and other
documents, then configuration, tests and the structure of the code.

How to find the features and requirements:

- A feature with a spec takes its requirements from the spec (`source` `spec`). A feature without a spec, or one
  whose spec covers only part of it, is derived from documents, configuration, tests and the structure of the code.
  When a spec covers only part of a feature, the feature's `source` is `mixed` and each requirement says where it
  came from in its own `source`.
- A requirement derived from code describes only what the code actually does now, never what it should do or was
  meant to do, and it names the files it rests on as `evidence`. When you cannot tell for sure, mark it `pending`.
- Requirements describe user needs and testable behaviour only, not how it is implemented: "the maintainer can undo
  the last deploy", not "a backup folder keeps the previous files".
- Keep doubts apart from requirements. A doubt is anything you notice but should not decide: a suspected bug,
  documentation that contradicts the code, a spec that contradicts the code, or an improvement worth considering.
  When a spec and the code disagree, write down both sides and do not pick one. A secret found in `secret_hits` can
  be a doubt that names only the file and line. Doubts that earlier exports already discarded (`discarded` entries
  of kind `doubt` in `existing` or in the lineage) are not raised again.
- The nutrients never contain plans, tasks or code. Plan-like documents (plans, research notes, task lists,
  changelogs) are read only as evidence for lessons; never copy their content into requirements.

How to find the lessons: from the project's documents, from specs and plan-like documents, and, when `check`
reported `git` as `true`, from the history with read-only git commands (for example
`git --no-pager log --oneline -n 200` and `git --no-pager show --stat <hash>`). Sort them into important decisions
with their reasons (`decision`), pitfalls the project ran into (`pitfall`), and approaches that were tried and
reversed (`reversed`). Each lesson names its evidence: a file, or `commit:<hash>` with the hash as git prints it in
lowercase. A lesson without evidence is `pending`. If you find no lesson at all, note that; stage 5 asks the
maintainer.

Outcomes:

- You can propose at least one feature with evidence: go to stage 4.
- The content is not enough to propose any requirement with evidence (for example the scope holds only
  configuration files and no recognisable feature): explain why, say that nothing was written, and stop.
- A file cannot be read (permissions, an encoding the Read tool cannot show): skip it and note its path; list such
  files when you present the draft in stage 5. Do not try another way or another command to read it.
- The scope holds more than you can read in this conversation (your context is running out): stop reading, explain
  this, recommend a smaller scope, and go back to stage 2 to choose one. Nothing was written.

## Stage 4: Building the draft

Build the draft in the conversation, following "The draft" above. Do not compute the generation yourself:
`generation` is the one `check` reported. Use `project` from `check` (or the existing nutrients' `project` in a
re-export). Every new item gets a new `id` that is never reused: it must not match any `id` in the lineage or the
existing nutrients, discarded items included. New items have `origin` equal to `generation`, `revised` `[]` and
`derived_from` `[]`.

When `lineage` is `"none"` and there are no existing nutrients, the project is the first generation and every item
has `origin` 1.

When `lineage` is `"present"`, `lineage_content` is the lineage the rebuild left. Carry it on:

- A spec marked `in_lineage` in `specs` belongs to a feature of the lineage (its `spec_dir` is that spec's folder):
  keep that feature's `id` and `origin`, and the `id` and `origin` of its requirements, principles and lessons
  that you can match. When an inherited item's `title`, `text` or `summary` now differs from the lineage, add
  `generation` to its `revised` (only for items whose `origin` is lower than `generation`).
- A spec that is not `in_lineage` is a feature new in this generation: `origin` is `generation`.
- For each feature in `lineage_missing_specs` (its spec folder is gone), ask with AskUserQuestion: keep it, based on
  the lineage's content with `.sdd-rebuild/lineage.json` as evidence, or discard it (recommend what the project's
  current state suggests).
- Ask whether the lineage's lessons still apply, in one question with multiSelect. Lessons that still apply keep
  their `id` and `origin`; the others go to `discarded`.
- Copy every entry of the lineage's `discarded` into the draft's `discarded` exactly as it is, unchanged.
- Any other item of the lineage that you cannot match to anything in the project now: ask whether to keep it
  (from the lineage's content) or discard it. Never let an item of the lineage disappear silently: the script
  refuses a draft where it is neither kept, merged into another item (listed in that item's `derived_from`) nor
  discarded.

When `export_dir` is `"ours"`, this is a re-export and `existing` holds the current nutrients. Use them as the
starting point: keep every existing item's `id`; leave the text of items whose evidence has not changed exactly as
it is; keep items outside the chosen scope exactly as they are; copy existing `discarded` entries whose
`discarded_in` is lower than `generation` unchanged. When `nutrients` was `"edited"` or `"unknown"` in stage 1, the
file holds the maintainer's own edits: before changing any existing content, ask about each change, one by one.

When an item from the lineage or from earlier generations is dropped, it moves to `discarded` with `discarded_in`
equal to `generation` (a dropped feature takes its requirements to `discarded` too). An item new in this generation
that the maintainer removes is simply deleted, unless they want it recorded. When the maintainer merges or splits
items, the result gets a new `id`, `origin` equal to `generation` and `derived_from` listing the original `id`s;
the originals then need no `discarded` entry.

Outcomes:

- The draft is built: go to stage 5.
- An item of the lineage cannot be matched to anything in the project now: ask keep or discard as described above,
  then continue.
- The maintainer asks to stop while you ask these questions: rule 7.

## Stage 5: Presenting and deciding

Nothing is written in this stage: do not write any file until stage 8. Present the draft section by section, in
this order, and let the maintainer decide each section before moving on:

1. Generation: the generation, whether it is the first one, how many items are inherited and how many new, the
   scope, and the files that could not be read.
2. Principles.
3. Features, their requirements and dependencies, in dependency order.
4. Doubts.
5. Lessons.

For every item show its source (spec, code, document or maintainer), its generation of origin and its evidence, and
mark items without evidence as pending. Show requirements as text the maintainer can judge, not as raw JSON.

After each section (except doubts) ask whether to accept it all, change some items, or delete some. A deleted item
that came from an earlier generation, or one the maintainer wants recorded, moves to `discarded` with their reason
(stage 4 explains how). After each section is decided, write a short list of what was decided, so that the
decisions survive if the conversation is compacted.

Doubts: one question per doubt, never several in one. The choices are: include it (it becomes a requirement or a
lesson, and the maintainer may change the wording), keep it as a `pending` item, or discard it (it goes to
`discarded` with `kind` `doubt`, a new `id`, `origin` equal to `generation` and the maintainer's reason, so later
exports do not raise it again).

Lessons: when you found no lesson with any evidence, say that you found none and ask with AskUserQuestion whether
the maintainer wants to tell you some. Lessons they tell you have `maintainer` as evidence. If they add none,
`lessons` stays empty and you continue. Never invent a lesson to fill the section.

Outcomes:

- The maintainer accepts, changes or deletes items: update the draft and go on to the next section.
- The maintainer adds a requirement, a lesson or another item: add it to the draft with `maintainer` as evidence (or
  the file they point to, after checking it is in the `files` list) and continue.
- The maintainer wants to change an earlier section that was already decided: rule 8.
- Every section has been decided: go to stage 6.
- The maintainer asks to stop: rule 7 (nothing is saved).

## Stage 6: Validating

Before the final confirmation, give the whole draft to `validate` on stdin, with the heredoc from rule 1:

```text
uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_export.py" validate <<'SDD_EXPORT_DRAFT'
{ ...the draft... }
SDD_EXPORT_DRAFT
```

It checks the format, the evidence and the generation rules, and compares the draft with the existing nutrients.
It changes nothing. Each entry of `errors` has `check` (what failed), `path` (the field, for example
`features[1].requirements[0]`) and `detail`.

Outcomes:

- `ok` is `true`: keep `counts` and `diff` and go to stage 7.
- `reason` is `"secret"`: a text looks like a secret, or a piece of evidence points at a secret file. Rewrite each
  field in `errors` so that it describes what is needed without the value (or remove that evidence), without
  repeating the value in the conversation, then run `validate` again. If this changes what an item says, show the
  maintainer that item.
- `reason` is `"invalid"`: look at the `check` of each error.
  - Format errors (`json`, `field`, `id`, `range`, `code-block`, `dependency`, `scope`, `spec`): fix the draft and
    validate again. Fixes that do not change what an item means need no question.
  - `unsupported` or `evidence`: a confirmed item has no evidence, or its evidence does not exist, is excluded or is
    not a valid commit. Add correct evidence, or make the item `pending`; tell the maintainer which items became
    pending.
  - Generation rules: `generation` (use the number from `check`), `lineage-item-missing` (an item of the lineage is
    neither kept, merged nor discarded), `origin-changed` (an inherited item must keep its `origin`),
    `origin-unknown` (an item claims an earlier generation that neither the lineage nor the existing nutrients
    know), `revision-unmarked` (an inherited item changed: add `generation` to its `revised`), `discard-lost` (an
    earlier `discarded` entry must stay unchanged), `discarded-active` (an `id` is both kept and discarded),
    `derived-unknown` (a `derived_from` names an unknown item), `id-reused` (a new item took an `id` the lineage
    already used: choose a new one). Fix each as its description says. When the fix needs a decision, such as
    whether an item of the lineage is kept or discarded, ask the maintainer one question per item, then validate
    again.
  - If the same error comes back after you fixed it twice and you cannot see why, show the maintainer the error and
    ask how to proceed (or stop, rule 7).
- Exit code 3: the project's state changed during the conversation. Handle `reason` as the same outcome of stage 1.

## Stage 7: Final confirmation

Present the whole result before asking for the one confirmation that allows writing:

- the summary from `counts`: principles, features, requirements, lessons and discarded items, how many are
  inherited and how many new, and how many are pending;
- the list of pending items and the list of discarded items;
- the differences, when `diff.base` is `"nutrients"`: items added, removed and changed (for changed items, the old
  and the new value of each field), whether the generation or the scope changed, and whether the order of the
  features changed. When nothing differs, say plainly that there are no differences. When `diff.base` is `"none"`,
  say this is the first export.

If `view` from `check` is `"edited"`, someone changed `.sdd-export/README.md` by hand. Tell the maintainer that
writing regenerates that file from the nutrients and will overwrite their changes, and ask whether to merge those
changes into the draft (you may read the file to do so) or let them go. Merging changes the draft: validate it again
(stage 6) before you continue.

Then ask one question with AskUserQuestion: confirm and write (recommended), change something, or stop.

Outcomes:

- Confirm: go to stage 8 with exactly this draft.
- Change something: go back to the section of stage 5 that holds it, then through stage 6 and this stage again.
- Stop: rule 7 (nothing is saved).

## Stage 8: Writing

Give the confirmed draft to `write` on stdin, exactly as validated, with the `state` from the latest `check`:

```text
uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_export.py" write --expect <state> <<'SDD_EXPORT_DRAFT'
{ ...the confirmed draft... }
SDD_EXPORT_DRAFT
```

`write` checks that `.sdd-export/` is still as it was when you checked it (that is what `--expect` is for: the
maintainer confirmed differences against that content), validates the draft again, and writes
`.sdd-export/nutrients.json`, `.sdd-export/README.md` (generated from it) and `.sdd-export/.gitattributes` (only if
missing). Each file is written to a temporary file first and then moved into place, so no half-written file is ever
left behind.

Outcomes:

- Exit code 0: go to stage 9 with its output.
- `reason` is `"changed"`: the nutrients were changed while you were talking (for example the maintainer edited the
  file in another window). Tell the maintainer and run `check` again
  (`uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_export.py" check`); if it exits with 3, follow the next two outcomes.
  Otherwise run `validate` with the confirmed draft, which now compares it with the new `existing`; show the new
  differences (they include anything the draft would undo of the new edit, and stage 4's rule applies: ask about
  each such change), and go back to stage 7 to confirm again with the new `state`.
- `reason` is `"conflict"` (exit code 3): something that is not this skill's now occupies `.sdd-export/`. Stop.
  List the paths in `conflicts`, say nothing was overwritten, and show the whole confirmed draft in the conversation
  so the maintainer can keep it. Do not write it anywhere else.
- Any other exit code 3: handle `reason` as the same outcome of stage 1, and show the whole confirmed draft in the
  conversation first.
- `reason` is `"os-error"`: the files could not be written (`error` says why, for example a read-only folder or
  missing permission). Report the cause and show the whole confirmed draft in the conversation. Explain that no
  half-written file was left in `.sdd-export/`. Ask with AskUserQuestion: stop (recommended), or retry after the
  maintainer has fixed the cause.
- The maintainer fixed the cause and asks to retry: run `check` again. If it exits with 3, handle it as in stage 1.
  If its `state` is the same as before, run `write` again with the same confirmed draft and that state. If the state
  is different (this also happens when the first file was already written before the failure), handle it as
  `"changed"` above; the differences may then be empty.
- `reason` is `"invalid"` or `"secret"` (this should not happen, stage 6 passed): go back to stage 6, and then
  through stage 7 again.
- Exit code 1 with `reason` `"usage"`: the command was malformed (for example `--expect` was missing). Fix the
  command and run it again with the same draft.

## Stage 9: Final report

Report from the output of `write`:

- where the nutrients are: `.sdd-export/nutrients.json`, the only source of truth, and its readable version
  `.sdd-export/README.md`;
- the generation, and what was included: the numbers per kind from `counts`, how many items were inherited and how
  many are new;
- the pending items and the discarded items;
- that the maintainer can commit `.sdd-export/` to the repository if they want to; that is their decision, and this
  skill does not commit;
- the next step: in the new project, run `/sdd-rebuild` and point it at this old project's path.

When the scope was `partial`, add that running `/sdd-export` again exports other areas, and that what was exported
now is kept. If the maintainer changes their mind after the write, explain that they can run `/sdd-export` again to
change the nutrients (it starts from them), or edit or delete `.sdd-export/` themselves.

Then stop. Do not commit, do not push, and do not start anything else.
