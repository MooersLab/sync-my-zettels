import json

from sync_my_zettels.config import Config
from sync_my_zettels import normalize
from sync_my_zettels.normalize import build_plan, group_subtrees, _driver_groups


def _matches(rows):
    """Wrap (old, new) org-roam retitles as a matches payload."""
    return {
        "matched": [
            {
                "obsidian": {"folgezettel": new},
                "org_roam": {"path": f"/vault/{old}.org", "folgezettel": old},
            }
            for old, new in rows
        ]
    }


def test_build_plan_includes_matches_and_confirmed_assignments():
    matches = _matches([("1.9", "1.14"), ("2.", "2.")])  # second is unchanged
    assignments = {"confirmed": [{"path": "/vault/new.org", "address": "30.3i"}]}
    plan = build_plan(matches, assignments)
    # unchanged pair (2.->2.) is dropped; changed pair + assignment remain
    assert [(r["old_folgezettel"], r["new_folgezettel"]) for r in plan] == [
        ("1.9", "1.14"),
        (None, "30.3i"),
    ]
    assert plan[1]["source"] == "confirmed-assignment"


def test_group_subtrees_folds_consistent_leaves():
    rows = [
        {"path": "p", "old_folgezettel": "1.9", "new_folgezettel": "1.14"},
        {"path": "a", "old_folgezettel": "1.9a", "new_folgezettel": "1.14a"},
        {"path": "b", "old_folgezettel": "1.9b", "new_folgezettel": "1.14b"},
        {"path": "s", "old_folgezettel": "36.", "new_folgezettel": "117."},
    ]
    groups = group_subtrees(rows)
    roots = {g["root"]["old_folgezettel"]: len(g["leaves"]) for g in groups}
    assert roots == {"1.9": 2, "36.": 0}  # 1.9 owns 2 leaves; 36. is a singleton
    dg = {g["old_address"]: g["mode"] for g in _driver_groups(groups)}
    assert dg == {"1.9": "subtree", "36.": "single"}


def test_group_subtrees_keeps_inconsistent_leaf_separate():
    # 1.9b's new address is NOT 1.14 + "b", so it must not fold under 1.9.
    rows = [
        {"path": "p", "old_folgezettel": "1.9", "new_folgezettel": "1.14"},
        {"path": "b", "old_folgezettel": "1.9b", "new_folgezettel": "3.2"},
    ]
    groups = group_subtrees(rows)
    roots = sorted(g["root"]["old_folgezettel"] for g in groups)
    assert roots == ["1.9", "1.9b"]  # both are their own roots


def _config(tmp_path, apply):
    (tmp_path / "matches.json").write_text(
        json.dumps(_matches([("1.9", "1.14"), ("1.9a", "1.14a")]))
    )
    (tmp_path / "assignments.json").write_text(
        json.dumps({"confirmed": [{"path": "/vault/x.org", "address": "30.3i"}]})
    )
    return Config(state_dir=tmp_path, apply=apply)


def test_run_dry_does_not_touch_emacs(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("emacs driver must not run on a dry run")

    monkeypatch.setattr(normalize, "_run_emacs_driver", boom)
    result = normalize.run(_config(tmp_path, apply=False))
    assert result["apply"] is False
    assert result["applied"] == []
    # one subtree group (1.9 + leaf 1.9a); the None-address assignment is unsupported
    assert len(result["groups"]) == 1
    assert result["groups"][0]["mode"] == "subtree"
    assert any(s["status"] == "unsupported" for s in result["skipped"])


def test_run_apply_partitions_driver_results(tmp_path, monkeypatch):
    def fake_driver(config, driver_groups):
        return [{"old_address": "1.9", "new_address": "1.14",
                 "status": "applied", "descendants": 1}]

    monkeypatch.setattr(normalize, "_run_emacs_driver", fake_driver)
    result = normalize.run(_config(tmp_path, apply=True))
    assert [a["status"] for a in result["applied"]] == ["applied"]
    # the unsupported assignment row is still reported as skipped
    assert any(s["status"] == "unsupported" for s in result["skipped"])
    written = json.loads((tmp_path / "normalize.json").read_text())
    assert written["applied"] == result["applied"]
