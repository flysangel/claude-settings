# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Rebuild a new project from an old project's nutrients: check, save, preview, claim, verify, lineage, focus, clear.

Usage:
    uv run sdd_rebuild.py check   [--old <dir>]                      new and old project, saved progress, next step
    uv run sdd_rebuild.py save    [--refresh-source]                 validate the full progress read from stdin, save it
    uv run sdd_rebuild.py preview                                    compose the lineage from the saved progress, check it
    uv run sdd_rebuild.py claim   <feature-id> [--dir <specs/name>]  record the spec folder just generated for a feature
    uv run sdd_rebuild.py verify                                     check the generated constitution and specs
    uv run sdd_rebuild.py lineage                                    write .sdd-rebuild/lineage.json
    uv run sdd_rebuild.py focus                                      point .specify/feature.json at the first new spec
    uv run sdd_rebuild.py clear                                      remove the saved progress

Run it from the root of the new project. Output is one JSON object on stdout. The old project is only read.
The neighbouring sdd-export and sdd-grill scripts are loaded when a command first needs them; nothing is loaded
or run when this file is imported.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

EXIT_OK = 0
EXIT_FAILED = 1
# 2 is reserved (it means "conflict" for the deploy tool); 4 is not used (no network).
EXIT_STATE = 3

SCHEMA = 1
TOOL = "sdd-rebuild"

COMMANDS = ("check", "save", "preview", "claim", "verify", "lineage", "focus", "clear")
USAGE = (
    "usage: sdd_rebuild.py check [--old <dir>] | save [--refresh-source] | preview | "
    "claim <feature-id> [--dir <specs/name>] | verify | lineage | focus | clear"
)

OWN_DIR = ".specify/sdd-rebuild"
PROGRESS_NAME = "progress.json"
GITIGNORE_NAME = ".gitignore"
OWN_FILES = (GITIGNORE_NAME, PROGRESS_NAME)
OWN_GITIGNORE = "# Created by sdd-rebuild. Local rebuild progress; never committed.\n*\n"

REBUILD_DIR = ".sdd-rebuild"
LINEAGE_NAME = "lineage.json"
ATTRIBUTES_NAME = ".gitattributes"
REBUILD_FILES = (LINEAGE_NAME, ATTRIBUTES_NAME)
LINEAGE_ATTRIBUTES = "# Created by sdd-rebuild; keeps the lineage LF on every platform.\n* text eol=lf\n"

EXPORT_DIR = ".sdd-export"
FEATURE_JSON_PATH = ".specify/feature.json"
SPECS_DIR = "specs"
PENDING_SPEC_DIR = "specs/pending"

# Lineage data, not a message: the text of a lineage is Traditional Chinese (sdd-export's schema 1). It reads
# "the maintainer decided to discard".
DEFAULT_DISCARD_REASON = "\u7dad\u8b77\u8005\u6c7a\u5b9a\u6368\u68c4"


def utc_today() -> str:
    """Today's date in UTC as YYYY-MM-DD; the only source of rebuilt_at (tests replace it)."""
    return datetime.now(timezone.utc).date().isoformat()


def utc_now() -> str:
    """The time in UTC to the second; the only source of saved_at (tests replace it)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# -------------------------------------------------------------- neighbours

NEIGHBOURS = (("sdd-export", "sdd_export"), ("sdd-grill", "sdd_grill"))
_cache: dict[str, object] = {}


def neighbour_cache() -> dict:
    """The neighbour modules loaded so far (empty until a command needs them)."""
    return dict(_cache)


def neighbour_path(skill: str, module: str) -> Path:
    """<this file>/../../../<skill>/scripts/<module>.py, in the repository and once installed."""
    return Path(os.path.abspath(__file__)).parents[2] / skill / "scripts" / f"{module}.py"


def load_neighbour(skill: str, module: str):
    """The neighbouring skill's script as a module, or None when it is missing or fails to load."""
    if skill in _cache:
        return _cache[skill]
    path = neighbour_path(skill, module)
    if not path.is_file():
        return None
    loaded = sys.modules.get(module)
    loaded_file = getattr(loaded, "__file__", None)
    if loaded_file:
        try:
            if os.path.samefile(loaded_file, path):
                _cache[skill] = loaded
                return loaded
        except OSError:
            pass
    # A copy somewhere else must not replace a module of that name that is already loaded.
    name = module if module not in sys.modules else f"_sdd_rebuild_{module}_{id(path)}"
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    try:
        spec.loader.exec_module(result)
    except BaseException:
        sys.modules.pop(name, None)
        return None
    _cache[skill] = result
    return result


def neighbours() -> tuple[object, object, list[str]]:
    """(sdd_export, sdd_grill, names of the missing skills)."""
    found = {skill: load_neighbour(skill, module) for skill, module in NEIGHBOURS}
    return found["sdd-export"], found["sdd-grill"], [skill for skill, _ in NEIGHBOURS if found[skill] is None]


def E():
    """sdd-export's script; only called after neighbours() found it."""
    return _cache["sdd-export"]


def G():
    """sdd-grill's script; only called after neighbours() found it."""
    return _cache["sdd-grill"]


# --------------------------------------------------- ancestors (research R5)


def build_ancestors(nutrients: dict, old_lineage: dict | None) -> dict[str, list[str]]:
    """id -> derived_from of every active item of the nutrients, joined with the old lineage's (nutrients first)."""
    ancestors: dict[str, list[str]] = {}
    for data in (nutrients, old_lineage):
        for item_id, (_, _, item) in E().active_items(data).items():
            entries = ancestors.setdefault(item_id, [])
            for entry in item.get("derived_from") or []:
                if isinstance(entry, str) and entry not in entries:
                    entries.append(entry)
    return ancestors


def expand(direct: list[str], ancestors: dict[str, list[str]]) -> list[str]:
    """The direct sources in order, then each one's ancestors depth first (pre-order); every id once."""
    result: list[str] = []
    seen: set[str] = set()
    for entry in direct:
        if entry not in seen:
            seen.add(entry)
            result.append(entry)
    for entry in list(result):
        stack = [iter(ancestors.get(entry, ()))]
        while stack:
            child = next(stack[-1], None)
            if child is None:
                stack.pop()
                continue
            if child not in seen:
                seen.add(child)
                result.append(child)
                stack.append(iter(ancestors.get(child, ())))
    return result


def derived_from_of(entry: dict, ancestors: dict[str, list[str]]) -> list[str]:
    """The derived_from the lineage records for a target entry (data-model: ancestors and expansion)."""
    if entry["basis"] == "inherit":
        return expand(ancestors.get(entry["id"], []), ancestors)
    if entry["basis"] == "derived":
        return expand(entry["from"], ancestors)
    return []


# ----------------------------------------------- the target and the lineage

SECTION_OF_KIND = {"principles": "principles", "features": "features", "requirements": "requirements",
                   "lessons": "lessons"}
CONTENT_FIELDS = {
    "principles": ("title", "text"),
    "features": ("title", "summary"),
    "requirements": ("kind", "text"),
    "lessons": ("kind", "title", "text"),
}
TEXT_FIELDS = ("title", "text", "summary")


def target_entries(target: dict):
    """(section, path, entry) for every principle, feature, requirement and lesson of a target."""
    for section in ("principles", "features", "lessons"):
        for index, entry in enumerate(target.get(section) or []):
            path = f"target.{section}[{index}]"
            yield section, path, entry
            if section == "features":
                for number, requirement in enumerate(entry.get("requirements") or []):
                    yield "requirements", f"{path}.requirements[{number}]", requirement


def lineage_generation(nutrients: dict) -> int:
    return nutrients["generation"] + 1


def compose_item(section: str, entry: dict, found: dict, ancestors: dict, generation: int) -> dict:
    """One lineage item from a target entry (data-model: composing the lineage)."""
    source = found.get(entry["id"]) if entry["basis"] == "inherit" else None
    source = source[2] if source and source[0] == section else None
    if entry["basis"] == "derived":
        sources = [found[i][2] for i in entry["from"] if i in found and found[i][0] == section]
    else:
        sources = []
    item: dict = {"id": entry["id"]}
    if source is not None:
        item["origin"] = source["origin"]
    else:
        item["origin"] = generation
    for field in CONTENT_FIELDS[section]:
        value = entry.get(field)
        item[field] = source.get(field) if value is None and source is not None else value
    if source is not None:
        changed = any(field in item and item[field] != source.get(field) for field in TEXT_FIELDS)
        item["revised"] = list(source.get("revised") or []) + ([generation] if changed else [])
    else:
        item["revised"] = []
    item["derived_from"] = derived_from_of(entry, ancestors)
    if section != "lessons":
        if source is not None:
            item["source"] = source.get("source")
        elif sources:
            item["source"] = sources[0].get("source")
        else:
            item["source"] = E().REBUILD
    if section == "features":
        item["spec_dir"] = entry.get("spec_dir") or entry.get("existing_spec")
        if source is not None:
            item["spec"] = source.get("spec")
        else:
            item["spec"] = next((s["spec"] for s in sources if s.get("spec") is not None), None)
        item["depends_on"] = list(entry.get("depends_on") or [])
        item["requirements"] = [compose_item("requirements", r, found, ancestors, generation)
                                for r in entry.get("requirements") or []]
    return item


def discard_record(entry: dict, found: dict, generation: int) -> dict | None:
    source = found.get(entry["id"])
    if source is None:
        return None
    section, _, item = source
    return {
        "id": entry["id"],
        "kind": E().SINGULAR[section],
        "origin": item.get("origin"),
        "discarded_in": generation,
        "text": entry.get("text") or E().item_title(item),
        "reason": entry.get("reason") or DEFAULT_DISCARD_REASON,
    }


def old_lineage_for(snapshot: dict, progress: dict) -> dict | None:
    """The old project's lineage when the progress uses it for the ancestors."""
    return snapshot.get("lineage") if progress.get("old_lineage") == "used" else None


def compose_lineage(snapshot: dict, progress: dict, placeholders: bool = False) -> dict:
    """The lineage the snapshot and the decisions make; placeholders fill what is not decided yet (for the checks)."""
    nutrients = snapshot["nutrients"]
    ancestors = build_ancestors(nutrients, old_lineage_for(snapshot, progress))
    found = E().active_items(nutrients)
    generation = lineage_generation(nutrients)
    target = progress["target"]
    lineage = {
        "tool": TOOL,
        "schema": SCHEMA,
        "generation": generation,
        "rebuilt_at": progress.get("rebuilt_at") or (utc_today() if placeholders else None),
        "source": {"project": nutrients["project"], "generation": nutrients["generation"],
                   "nutrients_schema": nutrients["schema"]},
    }
    for section in ("principles", "features", "lessons"):
        lineage[section] = [compose_item(section, entry, found, ancestors, generation) for entry in target[section]]
    if placeholders:
        for feature in lineage["features"]:
            feature["spec_dir"] = feature["spec_dir"] or PENDING_SPEC_DIR
    records = [discard_record(entry, found, generation) for entry in progress.get("discards") or []]
    lineage["discarded"] = copy.deepcopy(nutrients.get("discarded") or []) + [r for r in records if r is not None]
    return lineage


# ------------------------------------------------ the checks (research R6)


def used_ids(nutrients: dict, old_lineage: dict | None, ancestors: dict, lineage: dict | None,
             inherited: list[str]) -> set[str]:
    """The set U of used ids (data-model): no derived or new item may take one of these."""
    used: set[str] = set()
    for data in (nutrients, old_lineage, lineage):
        if not data:
            continue
        for item_id, (_, _, item) in E().active_items(data).items():
            if data is not lineage:
                used.add(item_id)
            used.update(entry for entry in item.get("derived_from") or [] if isinstance(entry, str))
        if data is not lineage:
            used.update(item["id"] for _, item in E().discarded_items(data))
    for item_id, entries in ancestors.items():
        used.add(item_id)
        used.update(entries)
    used.update(inherited)
    return used


def problem(check: str, path: str, detail: str) -> dict:
    return {"check": check, "path": path, "detail": detail}


def own_problems(snapshot: dict, progress: dict, root: Path | None) -> list[dict]:
    """The first layer: sdd-rebuild's own writing rules, which sdd-export cannot check when it reads."""
    nutrients = snapshot["nutrients"]
    found = E().active_items(nutrients)
    target = progress["target"]
    problems: list[dict] = []
    entries = list(target_entries(target))
    inherited: dict[str, str] = {}
    in_from: set[str] = set()
    for section, path, entry in entries:
        if entry["basis"] == "inherit":
            source = found.get(entry["id"])
            if source is None or source[0] != section:
                problems.append(problem("inherit-unknown", f"{path}.id", f"'{entry['id']}' is not a {E().SINGULAR[section]} "
                                        "of the nutrients, so it cannot be kept"))
            elif entry["id"] in inherited:
                problems.append(problem("inherit-twice", f"{path}.id", f"'{entry['id']}' is already kept at "
                                        f"{inherited[entry['id']]}"))
            else:
                inherited[entry["id"]] = path
        for index, source_id in enumerate(entry.get("from") or []):
            in_from.add(source_id)
            source = found.get(source_id)
            if source is None or source[0] != section:
                problems.append(problem("from-unknown", f"{path}.from[{index}]", f"'{source_id}' is not a "
                                        f"{E().SINGULAR[section]} of the nutrients"))

    ancestors = build_ancestors(nutrients, old_lineage_for(snapshot, progress))
    lineage = compose_lineage(snapshot, progress, placeholders=True)
    used = used_ids(nutrients, old_lineage_for(snapshot, progress), ancestors, lineage, list(inherited))
    created = {}
    for section, path, entry in entries:
        if entry["basis"] in ("derived", "new"):
            if entry["id"] in used:
                problems.append(problem("id-taken", f"{path}.id", f"the id '{entry['id']}' was already used by the "
                                        "nutrients, the old lineage or another item's sources; choose a new id"))
            elif entry["id"] in created:
                problems.append(problem("id-taken", f"{path}.id", f"the id '{entry['id']}' is already used at "
                                        f"{created[entry['id']]}"))
            created.setdefault(entry["id"], path)

    discarded: dict[str, str] = {}
    for index, entry in enumerate(progress.get("discards") or []):
        path = f"discards[{index}].id"
        item_id = entry["id"]
        if item_id not in found:
            problems.append(problem("discard-conflict", path, f"'{item_id}' is not an item of the nutrients"))
        elif item_id in inherited or item_id in in_from:
            problems.append(problem("discard-conflict", path, f"'{item_id}' is discarded but also kept or used as "
                                    "a source"))
        elif item_id in discarded:
            problems.append(problem("discard-conflict", path, f"'{item_id}' is already discarded at {discarded[item_id]}"))
        discarded.setdefault(item_id, path)

    for item_id, (section, path, _) in found.items():
        if item_id not in inherited and item_id not in in_from and item_id not in discarded:
            problems.append(problem("unaccounted", f"nutrients.{path}", f"{E().SINGULAR[section]} '{item_id}' of the "
                                    "nutrients is neither kept, merged or split into another item, nor discarded"))

    decided = set(progress.get("pending_decided") or [])
    for item_id, (section, path, item) in found.items():
        if item.get("status") == "pending" and item_id not in decided:
            problems.append(problem("pending-undecided", f"nutrients.{path}", f"the pending {E().SINGULAR[section]} "
                                    f"'{item_id}' has no decision yet; ask the maintainer and add it to pending_decided"))

    problems += existing_spec_problems(target, root)
    return problems


def existing_spec_problems(target: dict, root: Path | None) -> list[dict]:
    problems: list[dict] = []
    seen: dict[str, str] = {}
    generated_before = None
    for index, feature in enumerate(target.get("features") or []):
        path = f"target.features[{index}].existing_spec"
        value = feature.get("existing_spec")
        if value is None:
            generated_before = generated_before or feature["id"]
            continue
        if root is not None and not (root / value / "spec.md").is_file():
            problems.append(problem("existing-spec", path, f"{value} is not a folder of this project that holds a spec.md"))
        if value in seen:
            problems.append(problem("existing-spec", path, f"{value} is already matched at {seen[value]}"))
        seen.setdefault(value, path)
        if generated_before is not None:
            problems.append(problem("existing-spec", path, f"a feature matched to an existing spec must come before "
                                    f"the features whose specs are generated ('{generated_before}' comes first)"))
    return problems


def preview_problems(snapshot: dict, progress: dict, root: Path | None) -> list[dict]:
    """All three layers of research R6: sdd-export's checks run only once sdd-rebuild's own rules pass."""
    problems = own_problems(snapshot, progress, root)
    if problems:
        return problems
    lineage = compose_lineage(snapshot, progress, placeholders=True)
    problems += [problem("lineage-format", f"lineage.{p.path}" if p.path else "lineage", p.detail)
                 for p in E().lineage_problems(lineage)]
    problems += [problem("next-export", f"lineage.{p.path}" if p.path else "lineage", p.detail)
                 for p in E().generation_problems(lineage, lineage, None)]
    return problems


# ------------------------------------------------------------------ output


def dumps(data) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


class Usage(Exception):
    pass


class Io:
    def __init__(self, root: Path, stdin, stdout, stderr):
        self.root = root
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr

    def emit(self, data: dict, code: int = EXIT_OK) -> int:
        self.stdout.write(dumps(data))
        if "error" in data:
            self.stderr.write((data["error"] + "\n").encode("utf-8"))
        return code

    def fail(self, message: str, reason: str, code: int = EXIT_FAILED, **fields) -> int:
        return self.emit({**fields, "error": message, "reason": reason}, code)


def parse_args(argv: list[str]) -> tuple[str, dict]:
    if not argv or argv[0] not in COMMANDS:
        raise Usage()
    command, rest = argv[0], list(argv[1:])
    options: dict = {"old": None, "refresh": False, "feature": None, "dir": None}
    flags = {"check": ("--old",), "save": ("--refresh-source",), "claim": ("--dir",)}.get(command, ())
    while rest:
        word = rest.pop(0)
        if word.startswith("--"):
            name, has_value, value = word.partition("=")
            if name not in flags:
                raise Usage()
            if name == "--refresh-source":
                if has_value or options["refresh"]:
                    raise Usage()
                options["refresh"] = True
                continue
            if not has_value:
                if not rest:
                    raise Usage()
                value = rest.pop(0)
            key = name[2:]
            if options[key] is not None or not value:
                raise Usage()
            options[key] = value
        elif command == "claim" and options["feature"] is None:
            options["feature"] = word
        else:
            raise Usage()
    if command == "claim" and options["feature"] is None:
        raise Usage()
    return command, options


NOT_YET = "this command is not implemented yet"


def command_not_yet(io: Io, options: dict) -> int:
    return io.fail(NOT_YET, "internal")


HANDLERS: dict = {}


def main(argv: list[str] | None = None, root: Path | None = None, stdin=None, stdout=None, stderr=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    io = Io(
        Path(root) if root is not None else Path.cwd(),
        stdin if stdin is not None else sys.stdin.buffer,
        stdout if stdout is not None else sys.stdout.buffer,
        stderr if stderr is not None else sys.stderr.buffer,
    )
    try:
        command, options = parse_args(argv)
    except Usage:
        io.stderr.write((USAGE + "\n").encode("utf-8"))
        return io.emit({"error": USAGE, "reason": "usage"}, EXIT_FAILED)
    _, _, missing = neighbours()
    if missing:
        return dependency_failure(io, command, missing)
    return HANDLERS.get(command, command_not_yet)(io, options)


DEPENDENCY = "sdd-rebuild needs the sdd-export and sdd-grill skills installed next to it; missing: {}"


def dependency_failure(io: Io, command: str, missing: list[str]) -> int:
    fields: dict = {}
    if command == "check":
        fields = {key: None for key in CHECK_KEYS}
        fields["dependencies"] = {skill: ("missing" if skill in missing else "ok") for skill, _ in NEIGHBOURS}
        fields["export_skill"] = export_skill_present()
    fields["missing"] = missing
    return io.fail(DEPENDENCY.format(", ".join(missing)), "dependency", EXIT_STATE, **fields)


def export_skill_present() -> bool:
    return (Path(os.path.abspath(__file__)).parents[2] / "sdd-export" / "SKILL.md").is_file()


CHECK_KEYS = (
    "dependencies", "export_skill", "speckit", "missing", "constitution", "numbering", "specs", "rebuild_dir",
    "rebuild_conflicts", "progress", "changed", "saved", "old", "export_dir", "nutrients_edited", "nutrients_errors",
    "conflicts", "nutrients", "pending", "old_lineage", "old_lineage_errors", "needs_old_lineage", "source_state",
    "source_changed", "source_diff", "next",
)


if __name__ == "__main__":
    sys.exit(main())
