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


# ------------------------------------------------------------ own folder


def own_folder_state(folder: Path) -> str:
    """"absent", "ok", or "conflict" when .specify/sdd-rebuild/ holds anything sdd-rebuild did not create."""
    if not folder.exists() and not folder.is_symlink():
        return "absent"
    if folder.is_symlink() or not folder.is_dir():
        return "conflict"
    for entry in folder.iterdir():
        if entry.name not in OWN_FILES or entry.is_symlink() or not entry.is_file():
            return "conflict"
    gitignore = folder / GITIGNORE_NAME
    if gitignore.exists() and E().normalize_newlines(gitignore.read_bytes()) != OWN_GITIGNORE.encode("utf-8"):
        return "conflict"
    return "ok"


def write_file(path: Path, data: bytes) -> None:
    """Write through a temporary file in the same folder (sdd-grill's atomic_write); path is in the new project."""
    G().atomic_write(path, data)


def ensure_own_folder(root: Path) -> Path:
    folder = root / OWN_DIR
    folder.mkdir(parents=True, exist_ok=True)
    if not (folder / GITIGNORE_NAME).exists():
        write_file(folder / GITIGNORE_NAME, OWN_GITIGNORE.encode("utf-8"))
    return folder


def remove_own_files(folder: Path) -> bool:
    """Remove the two files of .specify/sdd-rebuild/ and the folder once empty; True when progress.json was there."""
    had_progress = (folder / PROGRESS_NAME).is_file()
    for name in OWN_FILES:
        path = folder / name
        if path.is_file():
            path.unlink()
    if folder.is_dir() and not any(folder.iterdir()):
        folder.rmdir()
    return had_progress


# --------------------------------------------------------------- progress

PHASES = ("deciding", "confirmed")
STAGES = ("items", "new", "lessons", "summary")
OLD_LINEAGE = ("used", "not-needed", "skipped")
ACTIONS = ("create", "amend", "keep")
BASES = ("inherit", "derived", "new")
GENERATION_STATES = ("pending", "written", "reviewed", "not-needed")
PROGRESS_FIELDS = (
    "schema", "tool", "old_project", "language", "phase", "stage", "old_lineage", "constitution", "target",
    "discards", "pending_decided", "adjustments", "deferred", "for_plan", "generation",
)
SCRIPT_FIELDS = ("source", "rebuilt_at", "saved_at", "fingerprint", "baseline", "lineage_written")
STORED_ORDER = (
    "schema", "tool", "old_project", "language", "phase", "stage", "source", "old_lineage", "constitution", "target",
    "discards", "pending_decided", "adjustments", "deferred", "for_plan", "generation", "rebuilt_at", "saved_at",
    "fingerprint", "baseline", "lineage_written",
)
ITEM_FIELDS = {
    "principles": ("id", "basis", "from", "title", "text"),
    "features": ("id", "basis", "from", "title", "summary", "depends_on", "existing_spec", "spec_dir", "reviewed",
                 "requirements"),
    "requirements": ("id", "basis", "from", "kind", "text"),
    "lessons": ("id", "basis", "from", "kind", "title", "text"),
}
SOURCE_FIELDS = ("nutrients", "nutrients_sha256", "lineage_state", "lineage", "lineage_sha256")


class Invalid(Exception):
    def __init__(self, path: str, message: str):
        super().__init__(f"the progress is invalid at {path}: {message}")
        self.path = path


def _join(path: str, key) -> str:
    if isinstance(key, int):
        return f"{path}[{key}]"
    return f"{path}.{key}" if path else key


def _object(value, path: str, fields: tuple, optional: tuple = ()) -> dict:
    if not isinstance(value, dict):
        raise Invalid(path or "(top level)", "must be an object")
    for key in fields:
        if key not in value:
            raise Invalid(_join(path, key), "is missing")
    for key in value:
        if key not in fields and key not in optional:
            raise Invalid(_join(path, key), "is not a field of the progress; remove it")
    return {key: value[key] for key in fields}


def _text(value, path: str, nullable: bool = False):
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        raise Invalid(path, "must be a string" + (" or null" if nullable else ""))
    if not value.strip():
        raise Invalid(path, "must not be empty")
    return value


def _choice(value, path: str, choices: tuple):
    if not isinstance(value, str) or value not in choices:
        raise Invalid(path, "must be one of " + ", ".join(choices))
    return value


def _array(value, path: str) -> list:
    if not isinstance(value, list):
        raise Invalid(path, "must be an array")
    return value


def _id(value, path: str) -> str:
    if not E().valid_id(value):
        raise Invalid(path, "must be an id: lowercase letters and digits joined by single hyphens, at most 64 characters")
    return value


def is_spec_dir_form(value) -> bool:
    return isinstance(value, str) and G().is_spec_dir_form(value)


def validate_entry(section: str, value, path: str, phase: str, earlier: list[str]) -> dict:
    entry = _object(value, path, ITEM_FIELDS[section])
    _id(entry["id"], path + ".id")
    basis = _choice(entry["basis"], path + ".basis", BASES)
    sources = _array(entry["from"], path + ".from")
    if basis == "derived" and not sources:
        raise Invalid(path + ".from", "a merged or split item lists at least one source")
    if basis != "derived" and sources:
        raise Invalid(path + ".from", "only a merged or split item (basis derived) has sources")
    for index, source in enumerate(sources):
        _id(source, f"{path}.from[{index}]")
    for field in ITEM_FIELDS[section]:
        if field in ("title", "text", "summary"):
            _text(entry[field], f"{path}.{field}", nullable=basis == "inherit")
        if field == "kind":
            kinds = E().REQUIREMENT_KINDS if section == "requirements" else E().LESSON_KINDS
            if not (entry["kind"] is None and basis == "inherit"):
                _choice(entry["kind"], path + ".kind", kinds)
    if section != "features":
        return entry
    for index, dependency in enumerate(_array(entry["depends_on"], path + ".depends_on")):
        if not isinstance(dependency, str) or dependency not in earlier:
            raise Invalid(f"{path}.depends_on[{index}]", "must be the id of a feature listed before this one")
    existing = entry["existing_spec"]
    if existing is not None and not is_spec_dir_form(existing):
        raise Invalid(path + ".existing_spec", "must be null or a folder directly under specs/, written as specs/<name>")
    spec_dir = entry["spec_dir"]
    if spec_dir is not None and not is_spec_dir_form(spec_dir):
        raise Invalid(path + ".spec_dir", "is recorded by claim; send the value the saved progress holds")
    if not isinstance(entry["reviewed"], bool):
        raise Invalid(path + ".reviewed", "must be true or false")
    if existing is not None:
        if spec_dir is not None and spec_dir != existing:
            raise Invalid(path + ".spec_dir", "of a feature matched to an existing spec is that spec's folder or null")
    else:
        if phase == "deciding" and spec_dir is not None:
            raise Invalid(path + ".spec_dir", "is recorded by claim after the confirmation; send null")
        if entry["reviewed"] and spec_dir is None:
            raise Invalid(path + ".reviewed", "can only be true once claim recorded the feature's spec folder")
    requirements = _array(entry["requirements"], path + ".requirements")
    if not requirements:
        raise Invalid(path + ".requirements", "a feature needs at least one requirement")
    entry["requirements"] = [validate_entry("requirements", item, f"{path}.requirements[{index}]", phase, [])
                             for index, item in enumerate(requirements)]
    return entry


def validate_progress(data) -> dict:
    """The rules of data-model.md that need nothing but the progress itself; returns its fields in order.

    Raises Invalid with the path of the first field that breaks a rule.
    """
    progress = _object(data, "", PROGRESS_FIELDS, SCRIPT_FIELDS)
    schema = progress["schema"]
    if isinstance(schema, bool) or schema != SCHEMA:
        raise Invalid("schema", f"must be {SCHEMA}")
    if progress["tool"] != TOOL:
        raise Invalid("tool", f"must be {TOOL}")
    old = _text(progress["old_project"], "old_project")
    if not os.path.isabs(old):
        raise Invalid("old_project", "must be the absolute path that check reports as old.path")
    _text(progress["language"], "language", nullable=True)
    phase = _choice(progress["phase"], "phase", PHASES)
    stage = _choice(progress["stage"], "stage", STAGES)
    _choice(progress["old_lineage"], "old_lineage", OLD_LINEAGE)
    constitution = _object(progress["constitution"], "constitution", ("action", "governance"))
    action = _choice(constitution["action"], "constitution.action", ACTIONS)
    for index, rule in enumerate(_array(constitution["governance"], "constitution.governance")):
        _text(rule, f"constitution.governance[{index}]")
    progress["constitution"] = constitution

    target = _object(progress["target"], "target", ("principles", "features", "lessons"))
    ids: dict[str, str] = {}
    features: list[str] = []
    for section in ("principles", "features", "lessons"):
        entries = []
        for index, value in enumerate(_array(target[section], f"target.{section}")):
            path = f"target.{section}[{index}]"
            entry = validate_entry(section, value, path, phase, list(features))
            for kind, item_path, item in [(section, path, entry)] + [
                    ("requirements", f"{path}.requirements[{n}]", r) for n, r in enumerate(entry.get("requirements") or [])]:
                if item["id"] in ids:
                    raise Invalid(item_path + ".id", f"repeats the id {item['id']} of {ids[item['id']]}")
                ids[item["id"]] = item_path
            if section == "features":
                features.append(entry["id"])
            entries.append(entry)
        target[section] = entries
    progress["target"] = target

    discards = []
    for index, value in enumerate(_array(progress["discards"], "discards")):
        path = f"discards[{index}]"
        entry = _object(value, path, ("id", "text", "reason"))
        _id(entry["id"], path + ".id")
        _text(entry["text"], path + ".text", nullable=True)
        _text(entry["reason"], path + ".reason", nullable=True)
        discards.append(entry)
    progress["discards"] = discards
    decided = _array(progress["pending_decided"], "pending_decided")
    for index, value in enumerate(decided):
        _id(value, f"pending_decided[{index}]")
        if value in decided[:index]:
            raise Invalid(f"pending_decided[{index}]", f"repeats {value}")
    adjustments = []
    for index, value in enumerate(_array(progress["adjustments"], "adjustments")):
        path = f"adjustments[{index}]"
        entry = _object(value, path, ("lesson", "change", "adopted"))
        _id(entry["lesson"], path + ".lesson")
        _text(entry["change"], path + ".change")
        if entry["adopted"] is not None and not isinstance(entry["adopted"], bool):
            raise Invalid(path + ".adopted", "must be true, false or null (not decided yet)")
        adjustments.append(entry)
    progress["adjustments"] = adjustments
    for name, fields in (("deferred", ("item", "reason", "feature")), ("for_plan", ("item", "feature"))):
        entries = []
        for index, value in enumerate(_array(progress[name], name)):
            path = f"{name}[{index}]"
            entry = _object(value, path, fields)
            for field in fields[:-1]:
                _text(entry[field], f"{path}.{field}")
            if entry["feature"] is not None and entry["feature"] not in features:
                raise Invalid(path + ".feature", "must be null or the id of a feature of the target")
            entries.append(entry)
        progress[name] = entries
    generation = _object(progress["generation"], "generation", ("constitution",))
    state = _choice(generation["constitution"], "generation.constitution", GENERATION_STATES)
    progress["generation"] = generation
    if action == "keep" and state != "not-needed":
        raise Invalid("generation.constitution", 'must be "not-needed" when the constitution is kept')
    if action != "keep" and phase == "deciding" and state != "pending":
        raise Invalid("generation.constitution", 'must be "pending" until the summary is confirmed')
    if action != "keep" and state == "not-needed":
        raise Invalid("generation.constitution", f'cannot be "not-needed" when the action is {action}')

    for path, value in E().strings_of({"target": progress["target"], "discards": progress["discards"]}):
        if E().CODE_FENCE.search(value):
            raise Invalid(path, "code blocks do not belong in the lineage; describe the behaviour instead")
    if phase == "confirmed":
        if stage != "summary":
            raise Invalid("stage", 'must be "summary" when the phase is "confirmed"')
        if progress["language"] is None:
            raise Invalid("language", 'must be set when the phase is "confirmed"')
        for index, entry in enumerate(adjustments):
            if entry["adopted"] is None:
                raise Invalid(f"adjustments[{index}].adopted", "every adjustment is decided before the confirmation")
    return progress


def snapshot_problem(progress: dict, snapshot: dict) -> Invalid | None:
    """Rule 3 (old_lineage against the snapshot) and the lessons that adjustments name."""
    state = snapshot["lineage_state"]
    generation = snapshot["nutrients"].get("generation")
    if state == "present":
        allowed = "used"
    elif state == "none" and generation == 1:
        allowed = "not-needed"
    else:
        allowed = "skipped"
    if progress["old_lineage"] != allowed:
        return Invalid("old_lineage", f'must be "{allowed}": the old project\'s lineage is {state} and the nutrients '
                       f"are generation {generation}")
    lessons = {item_id for item_id, (section, _, _) in E().active_items(snapshot["nutrients"]).items()
               if section == "lessons"}
    for index, entry in enumerate(progress["adjustments"]):
        if entry["lesson"] not in lessons:
            return Invalid(f"adjustments[{index}].lesson", "must be the id of a lesson of the nutrients")
    return None


def stored_shape_ok(data: dict) -> bool:
    source = data.get("source")
    fingerprint = data.get("fingerprint")
    baseline = data.get("baseline")
    return (
        all(key in data for key in SCRIPT_FIELDS)
        and isinstance(source, dict) and all(key in source for key in SOURCE_FIELDS)
        and isinstance(source["nutrients"], dict) and isinstance(source["nutrients"].get("generation"), int)
        and isinstance(source["lineage_state"], str)
        and (source["lineage"] is None or isinstance(source["lineage"], dict))
        and (data["rebuilt_at"] is None or isinstance(data["rebuilt_at"], str))
        and isinstance(data["saved_at"], str)
        and isinstance(fingerprint, dict) and set(fingerprint) == {"constitution", "specs", "head"}
        and (baseline is None or (isinstance(baseline, dict)
                                  and set(baseline) == {"constitution", "specs", "confirmed_counts"}
                                  and isinstance(baseline["specs"], dict)
                                  and isinstance(baseline["confirmed_counts"], dict)))
        and (data["lineage_written"] is None or isinstance(data["lineage_written"], str))
    )


def load_progress(root: Path) -> tuple[str, dict | None]:
    """("none" | "present" | "unreadable" | "conflict", the stored progress when present)."""
    folder = root / OWN_DIR
    if own_folder_state(folder) == "conflict":
        return "conflict", None
    path = folder / PROGRESS_NAME
    if not path.is_file():
        return "none", None
    try:
        data = json.loads(path.read_bytes().decode("utf-8"))
        validate_progress(data)
    except (OSError, ValueError, Invalid):
        return "unreadable", None
    if not stored_shape_ok(data) or snapshot_problem(data, data["source"]) is not None:
        return "unreadable", None
    return "present", data


def stored(progress: dict, script: dict) -> dict:
    merged = {**progress, **script}
    return {key: merged[key] for key in STORED_ORDER}


# ------------------------------------------------------------ old project


def fold_case() -> bool:
    """Whether paths compare without case (Windows)."""
    return os.name == "nt"


def path_key(path) -> str:
    real = os.path.realpath(path)
    return os.path.normcase(real).lower() if fold_case() else real


def relation(new: Path, old: Path) -> str:
    """"ok", "same", "old-inside-new" or "new-inside-old", comparing real paths."""
    a, b = path_key(new), path_key(old)
    if a == b:
        return "same"
    if b.startswith(a.rstrip("/\\") + os.sep) or b.startswith(a.rstrip("/\\") + "/"):
        return "old-inside-new"
    if a.startswith(b.rstrip("/\\") + os.sep) or a.startswith(b.rstrip("/\\") + "/"):
        return "new-inside-old"
    return "ok"


def old_state(root: Path, old: str) -> tuple[str, str]:
    """(real path, state) of the old project given on the command line or kept in the progress."""
    real = os.path.realpath(root / old)
    if not os.path.exists(real):
        return real, "missing"
    if not os.path.isdir(real):
        return real, "not-folder"
    found = relation(root, Path(real))
    return real, ("ok" if found == "ok" else found)


def lineage_hash(old: Path) -> str | None:
    path = old / REBUILD_DIR / LINEAGE_NAME
    return E().content_hash(path.read_bytes()) if path.is_file() else None


def read_old(old: Path) -> dict:
    """What sdd-export's code says about the old project's .sdd-export/ and .sdd-rebuild/lineage.json (read only)."""
    folder = E().export_folder(old)
    nutrients = folder["existing"] if folder["export_dir"] == "ours" else None
    state, lineage, problems = E().load_lineage(old / REBUILD_DIR / LINEAGE_NAME)
    if state == "present" and nutrients is not None and lineage.get("generation") != nutrients.get("generation"):
        state, lineage = "mismatch", None
    raw = old / EXPORT_DIR / "nutrients.json"
    return {
        "export_dir": folder["export_dir"],
        "conflicts": folder["conflicts"],
        "edited": folder["export_dir"] == "ours" and folder["nutrients"] in ("edited", "unknown"),
        "errors": [p.as_dict() for p in folder["errors"]] if folder["export_dir"] in ("invalid", "unreadable") else [],
        "nutrients": nutrients,
        "nutrients_sha256": E().content_hash(raw.read_bytes()) if nutrients is not None else None,
        "lineage_state": state,
        "lineage": lineage,
        "lineage_errors": [p.as_dict() for p in problems],
        "lineage_sha256": lineage_hash(old),
    }


def take_snapshot(root: Path, old_project: str) -> dict | None:
    real, state = old_state(root, old_project)
    if state != "ok":
        return None
    found = read_old(Path(real))
    if found["nutrients"] is None:
        return None
    return {key: found[key] for key in SOURCE_FIELDS}


# ------------------------------------------------------------ .sdd-rebuild/


def rebuild_dir_state(root: Path) -> tuple[str, list[str]]:
    """data-model "RebuildDir": none, empty, ours, conflict (with the paths) or invalid."""
    folder = root / REBUILD_DIR
    if not folder.exists() and not folder.is_symlink():
        return "none", []
    if folder.is_symlink() or not folder.is_dir():
        return "conflict", [REBUILD_DIR]
    entries = sorted(folder.iterdir(), key=lambda p: p.name)
    if not entries:
        return "empty", []
    strangers = [f"{REBUILD_DIR}/{e.name}" for e in entries
                 if e.name not in REBUILD_FILES or e.is_symlink() or not e.is_file()]
    if not strangers and not (folder / LINEAGE_NAME).is_file():
        strangers = [f"{REBUILD_DIR}/{e.name}" for e in entries]
    if strangers:
        return "conflict", strangers
    state, _, _ = E().load_lineage(folder / LINEAGE_NAME)
    if state == "conflict":
        return "conflict", [f"{REBUILD_DIR}/{LINEAGE_NAME}"]
    if state != "present":
        return "invalid", []
    return "ours", []


# -------------------------------------------------------------- next step


def generated(progress: dict) -> list[dict]:
    return [f for f in progress["target"]["features"] if f["existing_spec"] is None]


def candidates_of(root: Path, progress: dict) -> tuple[list[str], list[str]]:
    """New spec folders a claim may record, and new folders without a spec.md (data-model, cli.md claim)."""
    baseline = (progress.get("baseline") or {}).get("specs") or {}
    recorded = {f.get("spec_dir") for f in progress["target"]["features"]} | \
               {f.get("existing_spec") for f in progress["target"]["features"]}
    candidates, incomplete = [], []
    specs = root / SPECS_DIR
    if specs.is_dir():
        for entry in sorted(specs.iterdir(), key=lambda p: p.name):
            folder = f"{SPECS_DIR}/{entry.name}"
            if entry.is_symlink() or not entry.is_dir() or f"{folder}/spec.md" in baseline or folder in recorded:
                continue
            (candidates if (entry / "spec.md").is_file() else incomplete).append(folder)
    return candidates, incomplete


def focus_target(progress: dict) -> str | None:
    features = generated(progress)
    return features[0]["spec_dir"] if features else None


def next_step(root: Path, progress: dict | None) -> dict:
    step = {"step": "start", "feature": None, "candidates": []}
    if progress is None:
        return step
    if progress["phase"] == "deciding":
        return {**step, "step": "decide"}
    if progress["lineage_written"] is not None:
        target = focus_target(progress)
        path = root / FEATURE_JSON_PATH
        current = G().read_feature_directory(path) if path.is_file() else None
        return {**step, "step": "clear" if target is None or current == target else "focus"}
    constitution = progress["generation"]["constitution"]
    if constitution == "pending":
        return {**step, "step": "constitution"}
    if constitution == "written":
        return {**step, "step": "review-constitution"}
    for feature in generated(progress):
        if feature["spec_dir"] is None:
            candidates, _ = candidates_of(root, progress)
            if candidates:
                return {"step": "claim", "feature": feature["id"], "candidates": candidates}
            return {**step, "step": "specify", "feature": feature["id"]}
        if not feature["reviewed"]:
            return {**step, "step": "review", "feature": feature["id"]}
    return {**step, "step": "verify"}


# ------------------------------------------------------------------- check

CHECK_ERRORS = {
    "old-mismatch": "the progress belongs to another old project ({}); clear it or use that path",
    "speckit-missing": "Spec Kit is not set up in this project; run /sdd-init first",
    "speckit-incomplete": "Spec Kit in this project lacks files needed to generate a constitution and specs",
    "old-required": "give the old project's path with --old; there is no saved progress",
    "old-missing": "the old project's path does not exist",
    "old-not-folder": "the old project's path is not a folder",
    "same-project": "the old project is this project",
    "old-inside-new": "the old project is inside this project",
    "new-inside-old": "this project is inside the old project",
    "rebuilt": "this project was rebuilt already (.sdd-rebuild/lineage.json exists); a project is rebuilt only once",
    "rebuild-conflict": ".sdd-rebuild/ holds files sdd-rebuild did not write, or its lineage.json cannot be used",
    "nutrients-conflict": "the old project's .sdd-export/ holds files sdd-export did not create",
    "nutrients-unreadable": "the old project's .sdd-export/nutrients.json cannot be read",
    "nutrients-invalid": "the old project's .sdd-export/nutrients.json does not match the nutrients format",
    "nutrients-newer": "the old project's nutrients come from a newer sdd-export; update the skills",
    "progress-unreadable": "the saved progress in .specify/sdd-rebuild/ cannot be read; clear it to start over",
}
NUTRIENT_REASONS = {"conflict": "nutrients-conflict", "unreadable": "nutrients-unreadable",
                    "invalid": "nutrients-invalid", "newer": "nutrients-newer"}


def changed_since(root: Path, saved: dict) -> list[str]:
    now = G().fingerprint(root)
    then = saved["fingerprint"]
    changed = [key for key in ("constitution", "specs") if now[key] != then[key]]
    if now["head"] is not None and now["head"] != then["head"]:
        changed.append("head")
    return changed


def command_check(io: Io, options: dict) -> int:
    root = io.root
    speckit, missing = G().speckit_state(root)
    rebuild_dir, rebuild_conflicts = rebuild_dir_state(root)
    progress_state, saved = load_progress(root)
    out = {key: None for key in CHECK_KEYS}
    out.update({
        "dependencies": {skill: "ok" for skill, _ in NEIGHBOURS},
        "export_skill": export_skill_present(),
        "speckit": speckit,
        "missing": missing,
        "constitution": G().constitution_state(root),
        "numbering": G().numbering(root),
        "specs": G().existing_specs(root),
        "rebuild_dir": rebuild_dir,
        "rebuild_conflicts": rebuild_conflicts,
        "progress": progress_state,
        "changed": changed_since(root, saved) if saved else [],
        "saved": saved,
        "old": {"path": None, "state": None},
    })
    reason = None
    given = options["old"]
    old_path = given if given is not None else (saved["old_project"] if saved else None)
    if saved and given is not None and path_key(root / given) != path_key(saved["old_project"]):
        reason = "old-mismatch"
    if old_path is not None:
        real, state = old_state(root, old_path)
        out["old"] = {"path": real, "state": state}
        if state == "ok":
            found = read_old(Path(real))
            nutrients = found["nutrients"]
            out.update({
                "export_dir": found["export_dir"],
                "nutrients_edited": found["edited"],
                "nutrients_errors": found["errors"],
                "conflicts": found["conflicts"],
                "nutrients": nutrients,
                "pending": [item_id for item_id, (_, _, item) in E().active_items(nutrients).items()
                            if item.get("status") == "pending"] if nutrients else [],
                "old_lineage": found["lineage_state"],
                "old_lineage_errors": found["lineage_errors"],
                "needs_old_lineage": nutrients["generation"] >= 2 if nutrients else None,
            })
            if saved:
                snapshot = saved["source"]
                out["source_state"] = "available" if nutrients is not None else "unavailable"
                if nutrients is not None:
                    nutrients_changed = found["nutrients_sha256"] != snapshot["nutrients_sha256"]
                    out["source_changed"] = {"nutrients": nutrients_changed,
                                             "lineage": found["lineage_sha256"] != snapshot["lineage_sha256"]}
                    if nutrients_changed:
                        out["source_diff"] = E().compute_diff(snapshot["nutrients"], nutrients)
        elif saved:
            out["source_state"] = "unavailable"
    out["next"] = next_step(root, saved)

    has_progress = progress_state == "present"
    old_state_value = out["old"]["state"]
    if reason is None and speckit != "ok":
        reason = f"speckit-{speckit}"
    if reason is None and not has_progress and old_path is None:
        reason = "old-required"
    if reason is None and not has_progress and old_state_value in ("missing", "not-folder"):
        reason = f"old-{old_state_value}"
    if reason is None and old_state_value in ("same", "old-inside-new", "new-inside-old"):
        reason = "same-project" if old_state_value == "same" else old_state_value
    if reason is None and rebuild_dir == "ours" and progress_state == "none":
        reason = "rebuilt"
    if reason is None and rebuild_dir in ("conflict", "invalid"):
        reason = "rebuild-conflict"
    if reason is None and not has_progress and out["export_dir"] in NUTRIENT_REASONS:
        reason = NUTRIENT_REASONS[out["export_dir"]]
    if reason is None and progress_state == "unreadable":
        reason = "progress-unreadable"
    if reason is None:
        return io.emit(out)
    message = CHECK_ERRORS[reason]
    if reason == "old-mismatch":
        message = message.format(saved["old_project"])
    return io.fail(message, reason, EXIT_FAILED if reason == "old-mismatch" else EXIT_STATE, **out)


# -------------------------------------------------------------------- save

NOT_JSON = "the progress is not a JSON object in UTF-8"
SECRET = "the progress at {} looks like a secret; describe what is needed instead of recording the value"
FROZEN = "the confirmed summary cannot change at {}"
FINISHED = "the lineage is written; only focus and clear are left"
SOURCE = "the old project's nutrients cannot be read now; check again"
CONFLICT = ".specify/sdd-rebuild/ holds files sdd-rebuild did not create; nothing was written"
COULD_NOT_WRITE = "could not write: {}"
PREVIEW_INVALID = "the decisions do not yet make a valid lineage"
GENERATION_ORDER = {"pending": 0, "written": 1, "reviewed": 2, "not-needed": 0}


def frozen_part(feature_free: dict) -> dict:
    """The target without what may still move after the confirmation (spec_dir, reviewed)."""
    target = copy.deepcopy(feature_free)
    for feature in target["features"]:
        feature.pop("spec_dir", None)
        feature.pop("reviewed", None)
    return target


def frozen_problem(progress: dict, previous: dict) -> str | None:
    """The first field that a save of confirmed progress may not change, or None."""
    if progress["phase"] == "deciding":
        if any(f["spec_dir"] for f in generated(previous)) or \
                previous["generation"]["constitution"] not in ("pending", "not-needed"):
            return "phase"
        return None
    for key in ("language", "old_lineage", "discards", "pending_decided", "adjustments"):
        if progress[key] != previous[key]:
            return key
    if frozen_part(progress["target"]) != frozen_part(previous["target"]):
        return "target"
    if progress["constitution"]["action"] != previous["constitution"]["action"]:
        return "constitution.action"
    for path, now, then in (("constitution.governance", progress["constitution"]["governance"],
                             previous["constitution"]["governance"]),
                            ("deferred", progress["deferred"], previous["deferred"]),
                            ("for_plan", progress["for_plan"], previous["for_plan"])):
        if now[:len(then)] != then:
            return path
    if GENERATION_ORDER[progress["generation"]["constitution"]] < GENERATION_ORDER[previous["generation"]["constitution"]]:
        return "generation.constitution"
    for index, (now, then) in enumerate(zip(progress["target"]["features"], previous["target"]["features"])):
        if then["reviewed"] and not now["reviewed"]:
            return f"target.features[{index}].reviewed"
    return None


def read_stdin_json(io: Io):
    raw = io.stdin.read()
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    try:
        value = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        raise Invalid("(top level)", "is not JSON in UTF-8") from None
    return value


def command_save(io: Io, options: dict) -> int:
    root = io.root
    if own_folder_state(root / OWN_DIR) == "conflict":
        return io.fail(CONFLICT, "conflict")
    _, previous = load_progress(root)
    if previous is not None and previous["lineage_written"] is not None:
        return io.fail(FINISHED, "finished")
    try:
        progress = validate_progress(read_stdin_json(io))
    except Invalid as error:
        return io.fail(str(error), "invalid", path=error.path)
    secret = G().find_secret(progress)
    if secret is not None:
        return io.fail(SECRET.format(secret), "secret", path=secret)
    for feature in progress["target"]["features"]:
        if feature["existing_spec"] is not None:
            feature["reviewed"] = True
            feature["spec_dir"] = feature["existing_spec"] if progress["phase"] == "confirmed" else None
    if previous is not None:
        if path_key(progress["old_project"]) != path_key(previous["old_project"]):
            error = Invalid("old_project", "must stay the old project of the saved progress")
            return io.fail(str(error), "invalid", path=error.path)
        if options["refresh"] and (progress["phase"] == "confirmed" or previous["phase"] == "confirmed"
                                   and frozen_problem(progress, previous)):
            return io.fail(FROZEN.format("the snapshot (--refresh-source works only before the confirmation)"), "frozen")
        if previous["phase"] == "confirmed":
            field = frozen_problem(progress, previous)
            if field is not None:
                return io.fail(FROZEN.format(field), "frozen", path=field)
    before = {f["id"]: f["spec_dir"] for f in previous["target"]["features"]} if previous else {}
    for index, feature in enumerate(progress["target"]["features"]):
        if feature["existing_spec"] is None and feature["spec_dir"] != before.get(feature["id"]):
            path = f"target.features[{index}].spec_dir"
            error = Invalid(path, "is recorded by claim; send the value the saved progress holds")
            return io.fail(str(error), "invalid", path=path)

    if previous is None or options["refresh"]:
        snapshot = take_snapshot(root, progress["old_project"])
        if snapshot is None:
            return io.fail(SOURCE, "source")
        made = "created" if previous is None else "refreshed"
    else:
        snapshot, made = previous["source"], "kept"
    error = snapshot_problem(progress, snapshot)
    if error is not None:
        return io.fail(str(error), "invalid", path=error.path)

    confirmed_before = previous is not None and previous["phase"] == "confirmed"
    rebuilt_at = previous["rebuilt_at"] if confirmed_before else None
    if progress["phase"] == "confirmed" and rebuilt_at is None:
        rebuilt_at = utc_today()
    if progress["phase"] == "confirmed":
        problems = preview_problems(snapshot, {**progress, "rebuilt_at": rebuilt_at}, root)
        if problems:
            return io.fail(PREVIEW_INVALID, "invalid", errors=problems)
    fingerprint = G().fingerprint(root)
    recorded = False
    baseline = None
    if progress["phase"] == "confirmed":
        if confirmed_before and previous["baseline"] is not None:
            baseline = previous["baseline"]
        else:
            # confirmed_counts: how long the append-only lists were at the confirmation; entries after these were
            # added later and are not part of the lineage (data-model, rule 7).
            baseline = {"constitution": fingerprint["constitution"], "specs": fingerprint["specs"],
                        "confirmed_counts": {"governance": len(progress["constitution"]["governance"]),
                                             "deferred": len(progress["deferred"]),
                                             "for_plan": len(progress["for_plan"])}}
            recorded = True
    data = stored(progress, {"source": snapshot, "rebuilt_at": rebuilt_at if progress["phase"] == "confirmed" else None,
                             "saved_at": utc_now(), "fingerprint": fingerprint, "baseline": baseline,
                             "lineage_written": None})
    folder = ensure_own_folder(root)
    write_file(folder / PROGRESS_NAME, dumps(data))
    return io.emit({"saved": f"{OWN_DIR}/{PROGRESS_NAME}", "phase": progress["phase"], "baseline": recorded,
                    "snapshot": made})


def resave(root: Path, data: dict) -> None:
    """Save stored progress again after a script field changed (claim, lineage)."""
    data = {**data, "saved_at": utc_now(), "fingerprint": G().fingerprint(root)}
    write_file(root / OWN_DIR / PROGRESS_NAME, dumps({key: data[key] for key in STORED_ORDER}))


# ----------------------------------------------------------------- preview

NO_PROGRESS = "there is no saved progress for this"
NO_CONFIRMED = "there is no confirmed summary yet"


def lineage_entries(lineage: dict):
    for section in ("principles", "features", "lessons"):
        for item in lineage.get(section) or []:
            yield section, item
            if section == "features":
                for requirement in item.get("requirements") or []:
                    yield "requirements", requirement


def counts_of(lineage: dict) -> dict:
    return {
        "principles": len(lineage["principles"]),
        "features": len(lineage["features"]),
        "requirements": sum(len(f["requirements"]) for f in lineage["features"]),
        "lessons": len(lineage["lessons"]),
        "discarded": len(lineage["discarded"]),
    }


def summarize(snapshot: dict, progress: dict, lineage: dict) -> dict:
    found = E().active_items(snapshot["nutrients"])
    generation = lineage["generation"]
    summary: dict = {key: [] for key in ("kept", "modified", "merged", "split", "added", "discarded")}
    for (section, _, entry), (_, item) in zip(target_entries(progress["target"]), lineage_entries(lineage)):
        line = {"section": section, "id": entry["id"], "title": E().item_title(item)}
        if entry["basis"] == "inherit":
            source = found.get(entry["id"])
            if source is None or source[0] != section:
                continue
            modified = generation in item["revised"] and generation not in (source[2].get("revised") or [])
            summary["modified" if modified else "kept"].append(line)
        elif entry["basis"] == "derived":
            summary["merged" if len(entry["from"]) >= 2 else "split"].append({**line, "from": list(entry["from"])})
        else:
            summary["added"].append(line)
    for entry in progress["discards"]:
        record = discard_record(entry, found, generation)
        if record is not None:
            summary["discarded"].append({"section": found[entry["id"]][0], "id": entry["id"], "title": record["text"],
                                         "reason": record["reason"]})
    summary["pending_decided"] = list(progress["pending_decided"])
    summary["adjustments"] = [dict(entry) for entry in progress["adjustments"]]
    summary["order"] = [{"id": f["id"], "title": f["title"], "depends_on": list(f["depends_on"]),
                         "existing_spec": entry["existing_spec"]}
                        for f, entry in zip(lineage["features"], progress["target"]["features"])]
    return summary


def command_preview(io: Io, options: dict) -> int:
    state, progress = load_progress(io.root)
    if progress is None:
        return io.fail(NO_PROGRESS, "no-progress")
    snapshot = progress["source"]
    problems = preview_problems(snapshot, progress, io.root)
    lineage = compose_lineage(snapshot, progress)
    out = {"ok": not problems, "errors": problems, "generation": lineage["generation"], "lineage": lineage,
           "summary": summarize(snapshot, progress, lineage), "counts": counts_of(lineage)}
    if problems:
        return io.fail(PREVIEW_INVALID, "invalid", **out)
    return io.emit(out)


def confirmed_progress(io: Io) -> tuple[dict | None, int | None]:
    state, progress = load_progress(io.root)
    if progress is None or progress["phase"] != "confirmed":
        return None, io.fail(NO_CONFIRMED, "no-progress")
    return progress, None


# ------------------------------------------------------------------- claim

NOT_NEXT = "{} is not the next feature whose spec is to be generated"
CLAIM_ERRORS = {
    "none": "no new spec folder with a spec.md was found; speckit-specify did not generate the spec",
    "ambiguous": "more than one new spec folder was found; choose one with --dir after the maintainer confirms",
    "mismatch": "the new spec folder is not the one .specify/feature.json points at; confirm it and use --dir",
}


def command_claim(io: Io, options: dict) -> int:
    root = io.root
    if own_folder_state(root / OWN_DIR) == "conflict":
        return io.fail(CONFLICT, "conflict")
    progress, failure = confirmed_progress(io)
    if progress is None:
        return failure
    feature_id = options["feature"]
    pending = [f for f in generated(progress) if f["spec_dir"] is None]
    if not pending or pending[0]["id"] != feature_id:
        return io.fail(NOT_NEXT.format(feature_id), "not-next")
    candidates, incomplete = candidates_of(root, progress)
    path = root / FEATURE_JSON_PATH
    directory = G().read_feature_directory(path) if path.is_file() else None
    out = {"feature": feature_id, "spec_dir": None, "feature_directory": directory, "candidates": candidates,
           "incomplete": incomplete}
    if options["dir"] is not None:
        if options["dir"] not in candidates:
            return io.fail(f"--dir must be one of the candidates: {', '.join(candidates) or 'none'}", "usage", **out)
        chosen = options["dir"]
    elif not candidates:
        return io.fail(CLAIM_ERRORS["none"], "none", **out)
    elif len(candidates) > 1:
        return io.fail(CLAIM_ERRORS["ambiguous"], "ambiguous", **out)
    elif candidates[0] != directory:
        return io.fail(CLAIM_ERRORS["mismatch"], "mismatch", **out)
    else:
        chosen = candidates[0]
    for feature in progress["target"]["features"]:
        if feature["id"] == feature_id:
            feature["spec_dir"] = chosen
    resave(root, progress)
    return io.emit({**out, "spec_dir": chosen})


# ------------------------------------------------------------------ verify

MISMATCH = "the generated documents do not match the confirmed summary"


def verify_documents(root: Path, progress: dict) -> dict:
    """sdd-grill's verify_generated on the generated features, plus sdd-rebuild's two checks (research R2)."""
    features = progress["target"]["features"]
    existing = {f["id"]: f["existing_spec"] for f in features if f["existing_spec"] is not None}
    shaped = {
        "baseline": progress["baseline"],
        "constitution": {"action": progress["constitution"]["action"]},
        "features": [{"id": f["id"], "spec_dir": f["spec_dir"], "depends_on": [existing.get(d, d) for d in f["depends_on"]]}
                     for f in generated(progress)],
    }
    result = G().verify_generated(root, shaped)
    failures = list(result["failures"])
    for feature in features:
        if feature["existing_spec"] is not None and not (root / feature["existing_spec"] / "spec.md").is_file():
            failures.append({"check": "existing-spec-missing", "detail": f'feature "{feature["id"]}" is matched to '
                             f'{feature["existing_spec"]}, but its spec.md does not exist'})
    if progress["generation"]["constitution"] not in ("reviewed", "not-needed"):
        failures.append({"check": "not-reviewed", "detail": "the constitution was not compared with the summary yet"})
    for feature in features:
        if not feature["reviewed"]:
            failures.append({"check": "not-reviewed", "detail": f'the spec of feature "{feature["id"]}" was not '
                             "compared with the summary yet"})
    dirs = {f["id"]: f["spec_dir"] or f["existing_spec"] for f in features}
    return {
        "ok": not failures,
        "failures": failures,
        "constitution": result["constitution"],
        "specs": [{"feature": f["id"], "dir": dirs[f["id"]], "depends_on": [dirs.get(d) or d for d in f["depends_on"]],
                   "existing": f["existing_spec"] is not None} for f in features],
        "unexpected": [d for d in result["unexpected"] if d not in existing.values()],
    }


def command_verify(io: Io, options: dict) -> int:
    progress, failure = confirmed_progress(io)
    if progress is None:
        return failure
    result = verify_documents(io.root, progress)
    if not result["ok"]:
        return io.fail(MISMATCH, "mismatch-documents", **result)
    return io.emit(result)


# ----------------------------------------------------------------- lineage

LINEAGE_CHANGED = ".sdd-rebuild/lineage.json exists with other content; it was not overwritten"
INTERNAL = "sdd-export does not accept the lineage sdd-rebuild composed; this is a defect of sdd-rebuild, nothing was written"
REBUILD_CONFLICT = ".sdd-rebuild/ holds files sdd-rebuild did not write, or its lineage.json cannot be used; nothing was written"


def record_lineage_written(root: Path, progress: dict, digest: str) -> None:
    resave(root, {**progress, "lineage_written": digest})


def command_lineage(io: Io, options: dict) -> int:
    root = io.root
    if own_folder_state(root / OWN_DIR) == "conflict":
        return io.fail(CONFLICT, "conflict")
    progress, failure = confirmed_progress(io)
    if progress is None:
        return failure
    state, conflicts = rebuild_dir_state(root)
    if state in ("conflict", "invalid"):
        return io.fail(REBUILD_CONFLICT, "rebuild-conflict", EXIT_STATE, rebuild_conflicts=conflicts)
    result = verify_documents(root, progress)
    if not result["ok"]:
        return io.fail(MISMATCH, "mismatch-documents", **result)
    snapshot = progress["source"]
    own = own_problems(snapshot, progress, root)
    if own:
        return io.fail(PREVIEW_INVALID, "invalid", errors=own)
    lineage = compose_lineage(snapshot, progress)
    theirs = preview_problems(snapshot, progress, root)
    if theirs:
        return io.fail(INTERNAL, "internal", errors=theirs)
    data = E().serialize(lineage, "lineage")
    folder = root / REBUILD_DIR
    path = folder / LINEAGE_NAME
    written: list[str] = []
    unchanged = False
    if path.is_file():
        if E().normalize_newlines(path.read_bytes()) != data:
            return io.fail(LINEAGE_CHANGED, "lineage-changed")
        unchanged = True
    folder.mkdir(exist_ok=True)
    if not unchanged:
        write_file(path, data)
        written.append(f"{REBUILD_DIR}/{LINEAGE_NAME}")
    if not (folder / ATTRIBUTES_NAME).exists():
        write_file(folder / ATTRIBUTES_NAME, LINEAGE_ATTRIBUTES.encode("utf-8"))
        written.append(f"{REBUILD_DIR}/{ATTRIBUTES_NAME}")
    record_lineage_written(root, progress, E().content_hash(path.read_bytes()))
    return io.emit({"written": written, "unchanged": unchanged, "lineage": f"{REBUILD_DIR}/{LINEAGE_NAME}",
                    "generation": lineage["generation"], "counts": counts_of(lineage)})


# ------------------------------------------------------------ focus, clear

NOT_REGULAR = ".specify/feature.json is not a regular file; nothing was written"
FOCUS_MISMATCH = MISMATCH + "; .specify/feature.json was not changed"


def command_focus(io: Io, options: dict) -> int:
    root = io.root
    progress, failure = confirmed_progress(io)
    if progress is None:
        return failure
    if progress["lineage_written"] is None:
        return io.fail("the lineage is not written yet; run lineage first", "no-progress")
    result = verify_documents(root, progress)
    if not result["ok"]:
        return io.fail(FOCUS_MISMATCH, "mismatch-documents", failures=result["failures"])
    path = root / FEATURE_JSON_PATH
    if (path.exists() or path.is_symlink()) and (path.is_symlink() or not path.is_file()):
        return io.fail(NOT_REGULAR, "not-regular")
    previous = G().read_feature_directory(path) if path.is_file() else None
    target = focus_target(progress)
    if target is None:
        return io.emit({"feature_directory": None, "previous": previous, "changed": False})
    changed = previous != target
    if changed:
        write_file(path, dumps({"feature_directory": target}))
    return io.emit({"feature_directory": target, "previous": previous, "changed": changed})


def command_clear(io: Io, options: dict) -> int:
    folder = io.root / OWN_DIR
    state = own_folder_state(folder)
    if state == "conflict":
        return io.fail(CONFLICT.replace("written", "removed"), "conflict")
    if state == "absent":
        return io.emit({"cleared": False})
    return io.emit({"cleared": remove_own_files(folder)})


HANDLERS = {
    "check": command_check, "save": command_save, "preview": command_preview, "claim": command_claim,
    "verify": command_verify, "lineage": command_lineage, "focus": command_focus, "clear": command_clear,
}


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
    try:
        return HANDLERS[command](io, options)
    except OSError as error:
        return io.fail(COULD_NOT_WRITE.format(error.strerror or error), "os-error")


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
