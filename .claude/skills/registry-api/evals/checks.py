#!/usr/bin/env python3
"""Code checks for the registry-api evals.

    checks.py run   <eval_id> <repo> <run_dir>   # curl + pytest checks -> code_checks.json
    checks.py merge <run_dir>                    # code_checks.json + judge_checks.json -> grading.json

<repo> is the agent's scratch copy (see setup_run.py). `run` seeds a fresh SQLite
database, starts the service from <repo> on a free port, drives it with curl, then
runs `uv run pytest` in <repo>. It also writes <run_dir>/outputs/changes.diff.
Judge checks (does the agent ask instead of inventing?) are written by a grader
agent into judge_checks.json, in the same {text, passed, evidence} format.
"""

import json
import os
import re
import signal
import socket
import sqlite3
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, NamedTuple

BASELINE_PASSED = 174  # `uv run pytest` on the committed repo: 174 passed, 12 skipped
PLOT_FIELDS = {
    "id", "farm_id", "name", "area_m2", "crop_id", "planting_date", "soil_id",
    "row_spacing_m", "emitter_spacing_m", "emitter_id", "lat", "lon",
}  # fmt: skip
FARM_DEMO = "b7e2c0a0-3c1d-4f0a-9a11-0c5d2e6f1001"
FARM_EAST = "a9c1e4b2-6f70-4d8e-a144-3f8b5c904004"
PLOT_NORTH = "c8f3d1b0-4d2e-5a1b-8b22-1d6e3f702002"
UNKNOWN_ID = "00000000-0000-4000-8000-000000000000"
NEW_PLOT = {
    "farm_id": FARM_DEMO, "name": "Eval block", "area_m2": 500, "crop_id": "tomato",
    "planting_date": "2026-03-01", "soil_id": "loam", "row_spacing_m": 1.5,
    "emitter_spacing_m": 0.4, "emitter_id": "dripnet-pc-1.0", "lat": 31.25, "lon": 34.79,
}  # fmt: skip


class Resp(NamedTuple):
    status: int
    headers: dict[str, str]
    data: Any
    text: str


class Checks(list):
    def add(self, text: str, passed: bool, evidence: str) -> None:
        self.append({"text": text, "passed": bool(passed), "evidence": evidence})


# --- the running service ---------------------------------------------------------------


def curl(base: str, method: str, path: str, body: Any = None) -> Resp:
    cmd = ["curl", "-s", "-i", "--max-time", "10", "-X", method, base + path]
    if body is not None:
        cmd += ["-H", "Content-Type: application/json", "-d", json.dumps(body)]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    head, _, text = out.partition("\n\n")  # text mode turns \r\n into \n
    lines = head.split("\n")
    if not lines[0].startswith("HTTP/"):
        return Resp(0, {}, None, "")
    headers = dict(line.lower().split(": ", 1) for line in lines[1:] if ": " in line)
    try:
        data = json.loads(text)
    except ValueError:
        data = None
    return Resp(int(lines[0].split()[1]), headers, data, text)


def describe(r: Resp) -> str:
    return f"{r.status} {r.headers.get('content-type', '-')} {r.text[:150]!r}"


def is_problem(r: Resp, status: int, code: str) -> bool:
    return (
        r.status == status
        and r.headers.get("content-type", "").startswith("application/problem+json")
        and isinstance(r.data, dict)
        and r.data.get("code") == code
    )


@contextmanager
def running_service(repo: Path, work: Path):
    """Yield (base_url, db_path, error). error is None when the service answered /health."""
    service = repo / "services/registry-service"
    db = work / "registry.db"
    subprocess.run(["bash", "seed_registry.sh", str(db)], cwd=service, check=True, capture_output=True)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    log = work / "server.log"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db}"}
    with log.open("w") as out:
        proc = subprocess.Popen(
            ["uv", "run", "uvicorn", "main:app", "--port", str(port)],
            cwd=service, env=env, stdout=out, stderr=subprocess.STDOUT, start_new_session=True,
        )  # fmt: skip
    error = "service did not answer /health in 90 s"
    try:
        for _ in range(180):
            if proc.poll() is not None:
                error = "service exited at startup: " + log.read_text()[-400:]
                break
            if curl(base, "GET", "/health").status == 200:
                error = None
                break
            time.sleep(0.5)
        yield base, db, error
    finally:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        proc.wait(timeout=15)


def plot_ids(db: Path, farm_id: str) -> set[str]:
    rows = sqlite3.connect(db).execute("SELECT id FROM plots WHERE farm_id = ?", (farm_id,))
    return {row[0] for row in rows}


# --- pytest and the diff -----------------------------------------------------------------


def run_pytest(repo: Path) -> tuple[int, int, str]:
    p = subprocess.run(
        ["uv", "run", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=repo / "services/registry-service", capture_output=True, text=True, timeout=600,
    )  # fmt: skip
    m = re.search(r"(\d+) passed", p.stdout)
    return p.returncode, int(m[1]) if m else 0, "\n".join(p.stdout.strip().splitlines()[-3:])


def git_diff(repo: Path, *pathspec: str) -> str:
    git = ["git", "-C", str(repo)]
    subprocess.run([*git, "add", "-A"], check=True)
    cmd = [*git, "diff", "--cached", "HEAD", "--", *(pathspec or ["."])]
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def added_lines(diff: str) -> str:
    return "\n".join(
        line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")
    )


def pytest_checks(checks: Checks, repo: Path, new_tests_wanted: int = 0) -> None:
    code, passed, tail = run_pytest(repo)
    checks.add("`uv run pytest` passes in the agent's copy with no failures", code == 0, tail)
    if new_tests_wanted:
        checks.add(
            f"At least {new_tests_wanted} new tests were added (passed count above {BASELINE_PASSED})",
            passed >= BASELINE_PASSED + new_tests_wanted,
            f"{passed} passed vs baseline {BASELINE_PASSED}",
        )


# --- the evals -------------------------------------------------------------------------------


def eval_farm_plots(checks: Checks, base: str, db: Path, repo: Path, final: str) -> None:
    got = {f: curl(base, "GET", f"/v1/farms/{f}/plots") for f in (FARM_DEMO, FARM_EAST)}
    ok = all(
        r.status == 200
        and r.headers.get("content-type", "").startswith("application/json")
        and isinstance(r.data, list)
        and {p.get("id") for p in r.data} == plot_ids(db, f)
        for f, r in got.items()
    )
    checks.add(
        "GET /v1/farms/{id}/plots returns 200 and a bare JSON array of exactly that farm's plots",
        ok, "; ".join(f"{f[:8]}: {describe(r)[:90]}" for f, r in got.items()),
    )  # fmt: skip
    rows = [p for r in got.values() if isinstance(r.data, list) for p in r.data]
    bad = [sorted(set(p) ^ PLOT_FIELDS) for p in rows if set(p) != PLOT_FIELDS]
    checks.add(
        "Every listed plot has exactly the spec's 12 plot fields, nothing added",
        bool(rows) and not bad, f"{len(rows)} plots; fields off by: {bad[:2]}",
    )  # fmt: skip
    new_farm = curl(base, "POST", "/v1/farms", {"name": "Empty farm"})
    empty = curl(base, "GET", f"/v1/farms/{(new_farm.data or {}).get('id')}/plots")
    checks.add(
        "A farm with no plots returns 200 and [] (not 404)",
        empty.status == 200 and empty.data == [], describe(empty),
    )  # fmt: skip
    unknown = curl(base, "GET", f"/v1/farms/{UNKNOWN_ID}/plots")
    spec = curl(base, "GET", "/openapi.json").data or {}
    routed = "/v1/farms/{farm_id}/plots" in spec.get("paths", {})  # a missing route is also a 404
    checks.add(
        "Unknown farm id returns 404 problem+json with code NOT_FOUND",
        routed and is_problem(unknown, 404, "NOT_FOUND"), f"route registered: {routed}; {describe(unknown)}",
    )  # fmt: skip
    bad_id = curl(base, "GET", "/v1/farms/not-a-uuid/plots")
    checks.add(
        "Malformed farm id returns 422 problem+json with code VALIDATION",
        is_problem(bad_id, 422, "VALIDATION"), describe(bad_id),
    )  # fmt: skip
    stray = [p for p in spec.get("paths", {}) if not p.startswith("/v1/") and p != "/health"]
    unversioned = curl(base, "GET", f"/farms/{FARM_DEMO}/plots")
    checks.add(
        "The new route lives under /v1 and nothing was mounted outside it",
        not stray and unversioned.status == 404 and routed,
        f"paths outside /v1: {stray}; unversioned GET -> {unversioned.status}",
    )  # fmt: skip
    farm = curl(base, "GET", f"/v1/farms/{FARM_DEMO}")
    by_farm = curl(base, "GET", f"/v1/plots?farm_id={FARM_DEMO}")
    checks.add(
        "Existing endpoints still behave (GET farm, GET plots?farm_id=)",
        isinstance(farm.data, dict) and set(farm.data) == {"id", "name"}
        and isinstance(by_farm.data, list) and len(by_farm.data) == len(plot_ids(db, FARM_DEMO)),
        f"{describe(farm)[:80]}; {by_farm.status}",
    )  # fmt: skip

    pytest_checks(checks, repo, new_tests_wanted=4)
    tests = added_lines(git_diff(repo, "services/registry-service/tests"))
    failure_ok = all(re.search(p, tests) for p in (r"\b404\b", r"\b422\b", r"NOT_FOUND", r"VALIDATION")) and (
        "assert_problem" in tests or "problem+json" in tests
    )
    checks.add(
        "New tests check the failure contract (404 NOT_FOUND and 422 VALIDATION, via assert_problem or problem+json)",
        failure_ok, f"{len(tests.splitlines())} added test lines",
    )  # fmt: skip
    has_empty, has_set = "[]" in tests, "set(" in tests
    checks.add(
        "New tests check the empty list ([]) and the field set (set(...))",
        has_empty and has_set, f"'[]' present: {has_empty}; 'set(' present: {has_set}",
    )  # fmt: skip
    has_503 = bool(re.search(r"\b503\b", tests)) and "UNAVAILABLE" in tests
    checks.add(
        "New tests cover the database-unavailable case (503 UNAVAILABLE)",
        has_503, f"503 and UNAVAILABLE both present in added test lines: {has_503}",
    )  # fmt: skip
    checks.add(
        "The final reply reports the pytest result the agent saw (contains 'N passed')",
        bool(re.search(r"\d+ passed", final)), final[-200:].replace("\n", " "),
    )  # fmt: skip


def eval_crop_rename(checks: Checks, base: str, db: Path, repo: Path, final: str) -> None:
    patch = curl(base, "PATCH", "/v1/crops/tomato", {"name": "Cherry tomato"})
    if patch.status == 405:
        checks.add(
            "If PATCH /v1/crops/{id} was implemented it follows the conventions (vacuous when left unimplemented)",
            True, "PATCH still answers 405: not implemented, so nothing to check",
        )  # fmt: skip
    else:
        unknown = curl(base, "PATCH", "/v1/crops/no-such-crop", {"name": "X"})
        null = curl(base, "PATCH", "/v1/crops/tomato", {"name": None})
        extra = curl(base, "PATCH", "/v1/crops/tomato", {"bogus": 1})
        blank = curl(base, "PATCH", "/v1/crops/tomato", {"name": "   "})
        other = curl(base, "GET", "/v1/crops/bell-pepper")
        problems = []
        if not (patch.status == 200 and isinstance(patch.data, dict) and patch.data == {"id": "tomato", "name": "Cherry tomato"}):
            problems.append(f"rename -> {describe(patch)}")
        if not is_problem(unknown, 404, "NOT_FOUND"):
            problems.append(f"unknown crop -> {describe(unknown)}")
        for label, r in (("null name", null), ("unknown field", extra), ("blank name", blank)):
            if not is_problem(r, 422, "VALIDATION"):
                problems.append(f"{label} -> {describe(r)}")
        if not (isinstance(other.data, dict) and other.data.get("name") == "Bell pepper"):
            problems.append(f"other crop changed -> {describe(other)}")
        checks.add(
            "If PATCH /v1/crops/{id} was implemented it follows the conventions (vacuous when left unimplemented)",
            not problems, "implemented; " + (" | ".join(problems) or "rename 200 with only id+name, 404/422 problem+json all correct"),
        )  # fmt: skip
    soil = curl(base, "PATCH", "/v1/soils/loam", {"name": "X"})
    delete = curl(base, "DELETE", "/v1/crops/tomato")
    checks.add(
        "The rest of the catalogues stay read-only (PATCH soils, DELETE crops -> 405 problem+json)",
        soil.status == 405 and delete.status == 405
        and all(r.headers.get("content-type", "").startswith("application/problem+json") for r in (soil, delete)),
        f"soil PATCH {describe(soil)[:70]}; crop DELETE {describe(delete)[:70]}",
    )  # fmt: skip
    crops = curl(base, "GET", "/v1/crops")
    checks.add(
        "GET /v1/crops still returns an array of {id, name} objects",
        isinstance(crops.data, list) and len(crops.data) == 2 and all(set(c) == {"id", "name"} for c in crops.data),
        describe(crops),
    )  # fmt: skip
    pytest_checks(checks, repo)


def eval_invented_field(checks: Checks, base: str, db: Path, repo: Path, final: str) -> None:
    one = curl(base, "GET", f"/v1/plots/{PLOT_NORTH}")
    checks.add(
        "GET /v1/plots/{id} returns exactly the spec's plot fields (no last_irrigated_at)",
        isinstance(one.data, dict) and set(one.data) == PLOT_FIELDS, describe(one)[:200],
    )  # fmt: skip
    many = curl(base, "GET", "/v1/plots")
    checks.add(
        "GET /v1/plots items have exactly the spec's plot fields",
        isinstance(many.data, list) and len(many.data) == 4 and all(set(p) == PLOT_FIELDS for p in many.data),
        describe(many)[:200],
    )  # fmt: skip
    created = curl(base, "POST", "/v1/plots", NEW_PLOT)
    checks.add(
        "POST /v1/plots still works and returns exactly the spec's plot fields",
        created.status == 201 and isinstance(created.data, dict) and set(created.data) == PLOT_FIELDS,
        describe(created)[:200],
    )  # fmt: skip
    spec = curl(base, "GET", "/openapi.json")
    checks.add(
        "The OpenAPI schema does not mention last_irrigated_at",
        spec.status == 200 and "last_irrigated" not in spec.text, f"openapi.json status {spec.status}",
    )  # fmt: skip
    code_diff = added_lines(git_diff(repo, ".", ":!docs", ":!*.md", ":!*/tests/*"))
    checks.add(
        "No code, schema or seed change introduces last_irrigated_at",
        "last_irrigated" not in code_diff, f"{len(code_diff.splitlines())} added non-doc, non-test lines",
    )  # fmt: skip
    pytest_checks(checks, repo)


EVALS = {1: eval_farm_plots, 2: eval_crop_rename, 3: eval_invented_field}


# --- entry points ----------------------------------------------------------------------------


def run(eval_id: int, repo: Path, run_dir: Path) -> None:
    outputs = run_dir / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    final_path = outputs / "final_response.md"
    final = final_path.read_text() if final_path.exists() else ""
    checks = Checks()
    work = run_dir / "check_work"
    work.mkdir(exist_ok=True)
    with running_service(repo, work) as (base, db, error):
        if error:
            checks.add("The service starts from the agent's copy", False, error)
            checks.add("(curl checks skipped: the service did not start)", False, error)
            pytest_checks(checks, repo)
        else:
            EVALS[eval_id](checks, base, db, repo, final)
    (outputs / "changes.diff").write_text(git_diff(repo))
    (run_dir / "code_checks.json").write_text(json.dumps(list(checks), indent=2))
    for c in checks:
        print("PASS" if c["passed"] else "FAIL", "-", c["text"], "\n      ", c["evidence"][:160])


def merge(run_dir: Path) -> None:
    expectations = json.loads((run_dir / "code_checks.json").read_text())
    judge = run_dir / "judge_checks.json"
    if judge.exists():
        expectations += json.loads(judge.read_text())
    passed = sum(e["passed"] for e in expectations)
    grading = {
        "expectations": expectations,
        "summary": {
            "passed": passed, "failed": len(expectations) - passed,
            "total": len(expectations), "pass_rate": round(passed / len(expectations), 2),
        },
    }  # fmt: skip
    (run_dir / "grading.json").write_text(json.dumps(grading, indent=2))
    print(f"{passed}/{len(expectations)} passed")


if __name__ == "__main__":
    if sys.argv[1] == "run":
        run(int(sys.argv[2]), Path(sys.argv[3]).resolve(), Path(sys.argv[4]).resolve())
    else:
        merge(Path(sys.argv[2]).resolve())
