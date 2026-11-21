"""A stand-in for `claude -p` used by the sdd-drive tests (SDD_DRIVE_CLAUDE = [python, this file]).

Only the standard library; no network and no real API. It never runs the real Claude Code.

Environment:
    FAKE_CLAUDE_LOG        file that receives one JSON line per call: {"argv": [...], "stdin": "...", "cwd": "..."}
    FAKE_CLAUDE_COUNTER    file that counts the calls (the n-th call uses the n-th scenario)
    FAKE_CLAUDE_SCENARIOS  JSON array; element n is the scenario of call n (the last one is reused).
                           Each scenario is an object; every key is optional:

    "do"          list of actions, run in order (default: the natural action of the phase:
                  plan -> "plan", tasks -> "tasks", implement -> "implement", check -> nothing)
                  actions: "plan", "plan-template", "tasks", "tasks-template", "implement", "implement-partial",
                  "remove-task", "append", "append-bad", "rewrite-tasks", "check-one", "touch-code", "touch-plan",
                  "touch-spec", "touch-constitution", "touch-template", "dirty", "push"
    "tasks"       number of tasks the "tasks" action writes (default 3)
    "test_command" command written on the **Testing**: line by "plan"
    "files"       {relative path: text} written before committing
    "commit"      false to leave the changes uncommitted (default true)
    "commit_only" list of paths to commit instead of everything
    "sleep"       seconds to sleep before answering
    "report"      the structured_output (default {"status": "completed", "summary": "done"}); null leaves it out
    "result"      fields merged into the result object (e.g. {"is_error": true, "api_error_status": 401})
    "events"      extra stream-json lines written before the result
    "no_result"   true: exit without writing a result line
    "exit"        exit code (default 0)
    "fail_resume" true: when started with --resume, answer like a missing session (is_error, num_turns 0)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path


def env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    return Path(value) if value else None


def next_call() -> int:
    counter = env_path("FAKE_CLAUDE_COUNTER")
    if counter is None:
        return 0
    n = int(counter.read_text(encoding="utf-8")) if counter.is_file() else 0
    counter.write_text(str(n + 1), encoding="utf-8")
    return n


def scenario_for(n: int) -> dict:
    raw = os.environ.get("FAKE_CLAUDE_SCENARIOS")
    scenarios = json.loads(raw) if raw else [{}]
    if not scenarios:
        return {}
    return scenarios[min(n, len(scenarios) - 1)]


def option(argv: list[str], name: str) -> str | None:
    if name in argv:
        index = argv.index(name)
        if index + 1 < len(argv):
            return argv[index + 1]
    return None


def git(*args: str) -> None:
    subprocess.run(["git", *args], check=True, capture_output=True)


def is_git() -> bool:
    done = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True)
    return done.returncode == 0 and done.stdout.strip() == "true"


TASK_LINE = re.compile(r"^(\s*- \[)( |x|X)(\] (T\d{3,})\b.*)$")


def task_lines(text: str) -> list[str]:
    return [m.group(4) for line in text.splitlines() if (m := TASK_LINE.match(line))]


def max_id(text: str) -> int:
    ids = [int(t[1:]) for t in task_lines(text)]
    return max(ids) if ids else 0


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def act(action: str, spec_dir: Path, scenario: dict) -> None:
    plan = spec_dir / "plan.md"
    tasks = spec_dir / "tasks.md"
    if action == "plan":
        command = scenario.get("test_command", "python -c pass")
        write(plan, f"# Implementation Plan: {spec_dir.name}\n\n**Language/Version**: Python 3.11\n\n"
                    f"**Testing**: `{command}`\n\nBody of the plan.\n")
    elif action == "plan-template":
        write(plan, Path(".specify/templates/plan-template.md").read_text(encoding="utf-8"))
    elif action == "tasks":
        count = int(scenario.get("tasks", 3))
        lines = [f"# Tasks: {spec_dir.name}", "", "## Phase 1: Setup", ""]
        lines += [f"- [ ] T{i:03d} Do step {i} in src/step{i}.py" for i in range(1, count + 1)]
        write(tasks, "\n".join(lines) + "\n")
    elif action == "tasks-template":
        write(tasks, Path(".specify/templates/tasks-template.md").read_text(encoding="utf-8"))
    elif action in ("implement", "implement-partial", "check-one"):
        text = tasks.read_text(encoding="utf-8")
        out, done = [], 0
        for line in text.split("\n"):
            m = TASK_LINE.match(line)
            if m and m.group(2) == " ":
                if action == "implement" or (action in ("implement-partial", "check-one") and done == 0):
                    line = m.group(1) + "x" + m.group(3)
                    done += 1
                    write(Path("src") / f"{m.group(4).lower()}.txt", f"work for {m.group(4)}\n")
            out.append(line)
        write(tasks, "\n".join(out))
    elif action == "remove-task":
        text = tasks.read_text(encoding="utf-8")
        lines = text.split("\n")
        for i in range(len(lines) - 1, -1, -1):
            if TASK_LINE.match(lines[i]):
                del lines[i]
                break
        write(tasks, "\n".join(lines))
    elif action == "append":
        text = tasks.read_text(encoding="utf-8")
        m = max_id(text)
        extra = (f"\n## Phase 9: Convergence\n\n"
                 f"- [ ] T{m + 1:03d} Implement the missing retry per FR-008 (missing)\n"
                 f"  with a second indented line\n"
                 f"- [ ] T{m + 2:03d} Remove the unrequested cache per plan.md (unrequested)\n")
        write(tasks, text + ("" if text.endswith("\n") else "\n") + extra)
    elif action == "append-bad":
        text = tasks.read_text(encoding="utf-8")
        write(tasks, text + "\nsome free text that is not a task\n")
    elif action == "rewrite-tasks":
        text = tasks.read_text(encoding="utf-8")
        write(tasks, text.replace("Do step 1", "Do the first step"))
    elif action == "touch-code":
        write(Path("src") / "extra.py", "print('extra')\n")
    elif action == "touch-plan":
        write(plan, plan.read_text(encoding="utf-8") + "\nChanged by the check.\n")
    elif action == "touch-spec":
        spec = spec_dir / "spec.md"
        write(spec, spec.read_text(encoding="utf-8") + "\nChanged.\n")
    elif action == "touch-constitution":
        path = Path(".specify/memory/constitution.md")
        write(path, path.read_text(encoding="utf-8") + "\nChanged.\n")
    elif action == "touch-template":
        path = Path(".specify/templates/plan-template.md")
        write(path, path.read_text(encoding="utf-8") + "\nChanged.\n")
    elif action == "dirty":
        write(Path("left-behind.txt"), "not committed\n")
    elif action == "push":
        pass  # handled after the commit
    else:
        raise SystemExit(f"fake claude: unknown action {action}")


NATURAL = {"plan": ["plan"], "tasks": ["tasks"], "implement": ["implement"], "check": []}


def main() -> int:
    argv = sys.argv[1:]
    stdin = sys.stdin.buffer.read().decode("utf-8")
    log = env_path("FAKE_CLAUDE_LOG")
    if log is not None:
        with open(log, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"argv": argv, "stdin": stdin, "cwd": os.getcwd()}) + "\n")
    scenario = scenario_for(next_call())
    session = option(argv, "--session-id") or option(argv, "--resume") or "00000000-0000-4000-8000-000000000000"
    model = option(argv, "--model") or "unknown"
    out = sys.stdout

    def emit(obj: dict) -> None:
        out.write(json.dumps(obj) + "\n")
        out.flush()

    emit({"type": "system", "subtype": "init", "session_id": session, "model": model})
    if scenario.get("fail_resume") and "--resume" in argv:
        emit({"type": "result", "subtype": "error_during_execution", "is_error": True, "num_turns": 0,
              "terminal_reason": "error", "api_error_status": None,
              "result": "No conversation found with session ID", "session_id": session, "modelUsage": {}})
        return 1

    match = re.search(r"^Spec directory: (specs/\S+)$", stdin, re.MULTILINE)
    phase_match = re.search(r"^Phase: (\w+)$", stdin, re.MULTILINE)
    spec_dir = Path(match.group(1)) if match else Path("specs/unknown")
    phase = phase_match.group(1) if phase_match else "plan"
    actions = scenario.get("do", NATURAL.get(phase, []))
    for action in actions:
        act(action, spec_dir, scenario)
    for rel, text in (scenario.get("files") or {}).items():
        write(Path(rel), text)
    if is_git() and scenario.get("commit", True):
        if scenario.get("commit_only"):
            git("add", "--", *scenario["commit_only"])
        else:
            git("add", "-A")
        staged = subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode != 0
        if staged:
            git("commit", "--quiet", "-m", f"fake {phase} for {spec_dir.name}")
    if "push" in actions:
        git("push", "--quiet", "origin", "HEAD")
    if scenario.get("sleep"):
        time.sleep(float(scenario["sleep"]))
    for event in scenario.get("events") or []:
        emit(event)
    emit({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "working"}]},
          "session_id": session})
    if scenario.get("no_result"):
        return int(scenario.get("exit", 1))
    result = {
        "type": "result", "subtype": "success", "is_error": False, "terminal_reason": "completed",
        "api_error_status": None, "num_turns": 3, "result": "done", "session_id": session,
        "modelUsage": {f"claude-{model}-test": {"inputTokens": 1}}, "permission_denials": [],
    }
    report = scenario.get("report", {"status": "completed", "summary": "done"})
    if report is not None:
        result["structured_output"] = report
    result.update(scenario.get("result") or {})
    emit(result)
    return int(scenario.get("exit", 0))


if __name__ == "__main__":
    sys.exit(main())
