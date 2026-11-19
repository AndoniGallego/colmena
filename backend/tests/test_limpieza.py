import asyncio
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone

import pytest

from conftest import ORIGIN
from orquestador import limpieza as limpieza_mod
from orquestador.enchufe import FakeTerminales
from orquestador.limpieza import GitNoData, LimpiezaService, run_git
from terminales_support import aplicar_snapshot, snap_de

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
SID1 = "aaaaaaaa-2222-3333-4444-555555555551"
SID2 = "aaaaaaaa-2222-3333-4444-555555555552"


def ago(days):
    return (NOW - timedelta(days=days)).isoformat()


def agent(n, status="idle", days=9, cwd="/nonexistent", unread=False):
    return {"pane_id": f"p{n}", "kind": "claude", "status": status, "session_id": f"aaaaaaaa-2222-3333-4444-5555555555{n:02d}",
            "cwd": cwd, "title": f"t{n}", "doing": f"Haciendo {n}", "pending": "pendiente", "asks_user": False,
            "last_activity": ago(days), "unread": unread}


def term(n, estado="prompt"):
    return {"pane_id": f"x{n}", "terminal_id": f"term-x{n}", "titulo": "", "cwd": "", "proceso": "", "estado": estado,
            "protegida": False}


def tab(tid, agents=(), terms=(), label=None):
    return {"id": tid, "label": label or tid, "agents": list(agents), "terminales": list(terms)}


def ws(wid, label, tabs, pinned=False):
    return {"id": wid, "number": 1, "label": label, "pinned": pinned, "status": "idle", "tabs": tabs}


def snapshot_of(board):
    snap = {"workspaces": [], "tabs": [], "panes": [], "agents": []}
    for w in board["workspaces"]:
        snap["workspaces"].append({"workspace_id": w["id"], "label": w["label"], "number": 1})
        for t in w["tabs"]:
            snap["tabs"].append({"tab_id": t["id"], "workspace_id": w["id"], "label": t["label"]})
            for a in t["agents"]:
                snap["agents"].append({"pane_id": a["pane_id"], "tab_id": t["id"], "workspace_id": w["id"],
                                       "agent": "claude", "agent_status": a["status"], "cwd": a["cwd"],
                                       "state_change_seq": 1,
                                       "agent_session": {"kind": "id", "value": a["session_id"]}})
                snap["panes"].append({"pane_id": a["pane_id"], "tab_id": t["id"], "workspace_id": w["id"]})
            for x in t["terminales"]:
                snap["panes"].append({"pane_id": x["pane_id"], "tab_id": t["id"], "workspace_id": w["id"],
                                      "state_change_seq": 1})
    return snap


class FakeHub:
    def __init__(self, board):
        self.board = board

    async def current(self):
        return self.board

    async def refresh(self, force=False):
        return self.board


class Clock:
    def __init__(self, now=NOW.timestamp()):
        self.now = now

    def __call__(self):
        return self.now


def service(tmp_path, board, git=None, own=(), protected=("Super orquestador",), dias=7, clock=None):
    enchufe = FakeTerminales.desde_snapshot(snapshot_of(board), poll=0.01)
    kwargs = {"git": git} if git else {}
    svc = LimpiezaService(enchufe, FakeHub(board), lambda: set(own), list(protected), tmp_path, lambda: dias,
                          clock=clock or Clock(), **kwargs)
    return svc


def run(coro):
    return asyncio.run(coro)


def ids(result):
    return [(i["tipo"], i["target_id"]) for i in result["items"]]


def board_two(a_tab, b_tab=None):
    return {"workspaces": [ws("w1", "Uno", [a_tab, b_tab or tab("w1:t9", [agent(90, "working")])]),
                           ws("w2", "Dos", [tab("w2:t1", [agent(91, "working")])])]}


def test_quiet_by_days_with_default_seven(tmp_path):
    board = board_two(tab("w1:t1", [agent(1, days=9)]), tab("w1:t2", [agent(2, days=6)]))
    result = run(service(tmp_path, board).candidatos())
    assert result["dias"] == 7 and ids(result) == [("tab", "w1:t1")]
    item = result["items"][0]
    assert item["razones"] == [{"tipo": "quieto", "dias": 9}] and item["marcado"] and item["bloqueado"] is None
    assert item["sesiones"][0]["titulo"] == "Haciendo 1" and item["sesiones"][0]["pendiente"] == "pendiente"


def test_days_is_configurable_and_clamped(tmp_path):
    board = board_two(tab("w1:t1", [agent(1, days=9)]), tab("w1:t2", [agent(2, days=6)]))
    svc = service(tmp_path, board, dias=5)
    assert ids(run(svc.candidatos())) == [("workspace", "w1")]
    assert ids(run(svc.candidatos(8))) == [("tab", "w1:t1")]
    assert ids(run(svc.candidatos(10))) == []
    assert svc.dias(0) == 1 and svc.dias(500) == 90


def test_default_days_come_from_config(tmp_path):
    board = board_two(tab("w1:t1", [agent(1, days=3)]))
    assert ids(run(service(tmp_path, board, dias=3).candidatos())) == [("tab", "w1:t1")]
    assert ids(run(service(tmp_path, board, dias=4).candidatos())) == []


def test_never_candidates_working_blocked_unknown_or_missing_activity(tmp_path):
    for status in ("working", "blocked", "unknown"):
        board = board_two(tab("w1:t1", [agent(1, status)]))
        assert run(service(tmp_path, board).candidatos())["items"] == []
    a = agent(1)
    a["last_activity"] = None
    assert run(service(tmp_path, board_two(tab("w1:t1", [a]))).candidatos())["items"] == []


def test_protected_workspace_pinned_and_own_pane_are_excluded(tmp_path):
    protected = {"workspaces": [ws("w1", "Super orquestador", [tab("w1:t1", [agent(1)]), tab("w1:t2", [], [term(2)])]),
                                ws("w2", "Dos", [tab("w2:t1", [agent(3, "working")])])]}
    assert run(service(tmp_path, protected).candidatos())["items"] == []
    pinned = {"workspaces": [ws("w1", "Otro", [tab("w1:t1", [agent(1)])], pinned=True),
                             ws("w2", "Dos", [tab("w2:t1", [agent(3, "working")])])]}
    assert run(service(tmp_path, pinned).candidatos())["items"] == []
    board = board_two(tab("w1:t1", [agent(1)], [term(5)]))
    assert run(service(tmp_path, board, own={"x5"}).candidatos())["items"] == []


def test_unread_and_running_process_are_listed_but_blocked(tmp_path):
    board = board_two(tab("w1:t1", [agent(1, unread=True)]), tab("w1:t2", [agent(2)], [term(3, "corriendo")]))
    result = run(service(tmp_path, board).candidatos())
    assert [(i["target_id"], i["bloqueado"], i["marcado"]) for i in result["items"]] == [
        ("w1:t1", "sin_leer", False), ("w1:t2", "corriendo", False)]


def test_unknown_terminal_state_is_doubt_not_candidate(tmp_path):
    board = board_two(tab("w1:t1", [agent(1)], [term(3, "desconocido")]))
    assert run(service(tmp_path, board).candidatos())["items"] == []


def test_too_many_panes_or_pane_mismatch_excluded(tmp_path):
    board = board_two(tab("w1:t1", [agent(1)], [term(i) for i in range(12)]))
    assert run(service(tmp_path, board).candidatos())["items"] == []
    board = board_two(tab("w1:t1", [agent(1)]))
    svc = service(tmp_path, board)
    snap = snap_de(svc.enchufe)
    snap["panes"].append({"pane_id": "extra", "tab_id": "w1:t1", "workspace_id": "w1"})
    aplicar_snapshot(svc.enchufe, snap)
    assert run(svc.candidatos())["items"] == []


def test_whole_workspace_becomes_one_item(tmp_path):
    board = {"workspaces": [ws("w1", "Uno", [tab("w1:t1", [agent(1)]), tab("w1:t2", [agent(2, days=12)])]),
                            ws("w2", "Dos", [tab("w2:t1", [agent(3, "working")])])]}
    result = run(service(tmp_path, board).candidatos())
    assert ids(result) == [("workspace", "w1")]
    assert len(result["items"][0]["sesiones"]) == 2


def test_only_open_workspace_is_never_proposed_whole(tmp_path):
    board = {"workspaces": [ws("w1", "Uno", [tab("w1:t1", [agent(1)]), tab("w1:t2", [agent(2)])])]}
    assert run(service(tmp_path, board).candidatos())["items"] == []


def test_workspace_with_blocked_tab_lists_tabs_separately(tmp_path):
    board = {"workspaces": [ws("w1", "Uno", [tab("w1:t1", [agent(1)]), tab("w1:t2", [agent(2, unread=True)])]),
                            ws("w2", "Dos", [tab("w2:t1", [agent(3, "working")])])]}
    result = run(service(tmp_path, board).candidatos())
    assert ids(result) == [("tab", "w1:t1"), ("tab", "w1:t2")] and result["items"][1]["bloqueado"] == "sin_leer"


def test_tab_without_claude_needs_days_since_first_seen_and_no_state_change(tmp_path):
    board = board_two(tab("w1:t1", [], [term(1)]))
    clock = Clock()
    svc = service(tmp_path, board, clock=clock)
    assert run(svc.candidatos())["items"] == []
    clock.now += 8 * 86400
    result = run(svc.candidatos(fresh=True))
    assert ids(result) == [("tab", "w1:t1")] and result["items"][0]["razones"][0]["tipo"] == "sin_claude"
    snap = snap_de(svc.enchufe)
    next(p for p in snap["panes"] if p["pane_id"] == "x1")["state_change_seq"] = 2
    aplicar_snapshot(svc.enchufe, snap)
    clock.now += 86400
    assert run(svc.candidatos(fresh=True))["items"] == []
    stored = json.loads((tmp_path / "limpieza-visto.json").read_text())
    assert set(stored) == {"w1:t1"} and all(isinstance(v, str) for v in stored.values())


def test_candidates_are_cached_for_60_seconds(tmp_path):
    board = board_two(tab("w1:t1", [agent(1)]))
    mono = [0.0]
    svc = service(tmp_path, board)
    svc.monotonic = lambda: mono[0]
    first = run(svc.candidatos())
    calls = []
    real = svc.enchufe.tablero

    async def counting():
        calls.append(1)
        return await real()

    svc.enchufe.tablero = counting
    assert run(svc.candidatos()) is first and not calls
    mono[0] = 61
    run(svc.candidatos())
    assert calls


def git(cwd, *args):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, env=env)


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    (path / "a").write_text("1")
    git(path, "add", "a")
    git(path, "commit", "-qm", "uno")
    git(path, "update-ref", "refs/remotes/origin/main", "main")
    return path


def feature(repo, name="feature/PS9-71", merged=True):
    git(repo, "checkout", "-qb", name)
    (repo / "f").write_text(name)
    git(repo, "add", "f")
    git(repo, "commit", "-qm", "f")
    if merged:
        git(repo, "checkout", "-q", "main")
        git(repo, "merge", "-q", "--no-ff", "-m", "m", name)
        git(repo, "update-ref", "refs/remotes/origin/main", "main")
        git(repo, "checkout", "-q", name)


def merged_service(tmp_path, repo, days=0, **kw):
    board = board_two(tab("w1:t1", [agent(1, days=days, cwd=str(repo))]))
    return service(tmp_path, board, dias=30, **kw)


def test_merged_branch_by_local_origin_ref(tmp_path, repo):
    feature(repo)
    result = run(merged_service(tmp_path, repo).candidatos())
    assert ids(result) == [("tab", "w1:t1")]
    assert result["items"][0]["razones"] == [{"tipo": "mergeada", "rama": "feature/PS9-71", "base": "origin/main"}]
    assert result["git"] == "ok"


def test_unmerged_branch_is_not_a_candidate(tmp_path, repo):
    feature(repo, merged=False)
    assert run(merged_service(tmp_path, repo).candidatos())["items"] == []


def test_fresh_branch_equal_to_base_is_not_merged(tmp_path, repo):
    git(repo, "checkout", "-qb", "feature/nueva")
    assert run(merged_service(tmp_path, repo).candidatos())["items"] == []


def test_base_branch_itself_is_never_merged(tmp_path, repo):
    assert run(merged_service(tmp_path, repo).candidatos())["items"] == []


def test_upstream_gone_counts_as_merged(tmp_path, repo):
    feature(repo, merged=False)
    git(repo, "config", "remote.origin.url", "/nonexistent")
    git(repo, "config", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*")
    git(repo, "config", "branch.feature/PS9-71.remote", "origin")
    git(repo, "config", "branch.feature/PS9-71.merge", "refs/heads/feature/PS9-71")
    result = run(merged_service(tmp_path, repo).candidatos())
    assert ids(result) == [("tab", "w1:t1")]


def test_origin_head_is_resolved_and_falls_back_to_main_then_develop(tmp_path, repo):
    feature(repo)
    git(repo, "update-ref", "refs/remotes/origin/develop", "main")
    git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/develop")
    result = run(merged_service(tmp_path, repo).candidatos())
    assert result["items"][0]["razones"][0]["base"] == "origin/develop"
    git(repo, "symbolic-ref", "--delete", "refs/remotes/origin/HEAD")
    result = run(merged_service(tmp_path, repo).candidatos())
    assert result["items"][0]["razones"][0]["base"] == "origin/main"
    git(repo, "update-ref", "-d", "refs/remotes/origin/main")
    result = run(merged_service(tmp_path, repo).candidatos())
    assert result["items"][0]["razones"][0]["base"] == "origin/develop"


def test_no_base_means_no_merged_signal(tmp_path, repo):
    feature(repo)
    git(repo, "update-ref", "-d", "refs/remotes/origin/main")
    assert run(merged_service(tmp_path, repo).candidatos())["items"] == []


def test_git_timeout_marks_partial_and_never_proposes(tmp_path, repo):
    feature(repo)

    async def slow(argv, cwd, timeout=2.0):
        raise GitNoData("timeout")

    result = run(merged_service(tmp_path, repo, git=slow).candidatos())
    assert result["items"] == [] and result["git"] in {"parcial", "sin_datos"}


def test_idle_session_still_proposed_by_inactivity_when_git_has_no_data(tmp_path, repo):
    async def none(argv, cwd, timeout=2.0):
        raise GitNoData("x")

    board = board_two(tab("w1:t1", [agent(1, days=9, cwd=str(repo))]))
    result = run(service(tmp_path, board, git=none).candidatos())
    assert ids(result) == [("tab", "w1:t1")] and result["git"] != "ok"


def test_git_argv_is_read_only_and_never_touches_network(tmp_path, repo):
    feature(repo)
    seen = []

    async def spy(argv, cwd, timeout=2.0):
        seen.append(list(argv))
        return await run_git(argv, cwd, timeout)

    run(merged_service(tmp_path, repo, git=spy).candidatos())
    assert seen
    for argv in seen:
        assert argv[0] == "git" and "--no-optional-locks" in argv and "-C" in argv
        sub = next(a for a in argv[3:] if not a.startswith("-"))
        assert sub in {"rev-parse", "symbolic-ref", "branch", "for-each-ref"}
        assert not {"fetch", "pull", "push", "gc", "remote", "checkout", "update-ref"} & set(argv)


@pytest.mark.parametrize("sub", ["fetch", "pull", "push", "gc", "remote", "checkout", "update-ref", "config"])
def test_run_git_refuses_anything_that_is_not_read_only(sub, tmp_path):
    with pytest.raises(GitNoData):
        run(run_git(["git", "-C", str(tmp_path), "--no-optional-locks", sub], str(tmp_path)))


def test_invalid_cwd_gives_no_git_data(tmp_path):
    for cwd in ("", "relativo", "/no/existe", str(tmp_path) + "\n/etc"):
        assert limpieza_mod._valid_cwd(cwd) is False
    assert limpieza_mod._valid_cwd(str(tmp_path)) is True


def test_at_most_twenty_repos_per_computation(tmp_path):
    agents = []
    repos = []
    for n in range(25):
        d = tmp_path / f"r{n}"
        d.mkdir()
        repos.append(d)
        agents.append(agent(n, days=0, cwd=str(d)))
    tabs = [tab(f"w1:t{n}", [a]) for n, a in enumerate(agents)]
    board = {"workspaces": [ws("w1", "Uno", tabs), ws("w2", "Dos", [tab("w2:t1", [agent(99, "working")])])]}
    tops = set()

    async def fake(argv, cwd, timeout=2.0):
        if "--show-toplevel" in argv:
            tops.add(cwd)
            return cwd + "\nfeature/x\n"
        raise GitNoData("sin base")

    result = run(service(tmp_path, board, git=fake).candidatos())
    assert result["git"] == "parcial"


def test_run_git_ignores_inherited_git_env_and_neutralizes_repo_hooks(tmp_path, repo, monkeypatch):
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "otro"))
    monkeypatch.setenv("GIT_CONFIG_PARAMETERS", "'core.fsmonitor'='touch /tmp/x'")
    top = run(run_git(["git", "-C", str(repo), "--no-optional-locks", "rev-parse", "--show-toplevel"], str(repo)))
    assert top.strip() == str(repo)
    seen = {}
    real = asyncio.create_subprocess_exec

    async def spy(*argv, **kw):
        seen.update(kw["env"])
        return await real(*argv, **kw)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)
    run(run_git(["git", "-C", str(repo), "--no-optional-locks", "rev-parse", "HEAD"], str(repo)))
    pairs = {seen[f"GIT_CONFIG_KEY_{i}"]: seen[f"GIT_CONFIG_VALUE_{i}"] for i in range(int(seen["GIT_CONFIG_COUNT"]))}
    assert pairs["core.fsmonitor"] == "false" and pairs["core.hooksPath"] == "/dev/null"
    assert "GIT_DIR" not in seen and "GIT_CONFIG_PARAMETERS" not in seen


def test_origin_head_pointing_to_dash_ref_is_ignored(tmp_path, repo):
    feature(repo)
    git(repo, "update-ref", "refs/remotes/-x", "main")
    git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/-x")
    item = run(merged_service(tmp_path, repo).candidatos())["items"][0]
    assert {"tipo": "mergeada", "rama": "feature/PS9-71", "base": "origin/main"} in item["razones"]
