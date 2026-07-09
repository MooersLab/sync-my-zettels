import json

from sync_my_zettels.config import Config
from sync_my_zettels.wire_backlinks import paths_from_assign_apply, run
from sync_my_zettels import wire_backlinks


def test_paths_from_assign_apply_uses_applied_new_paths(tmp_path):
    (tmp_path / "assign-apply.json").write_text(json.dumps({
        "applied": [
            {"status": "applied", "new_path": "/v/a.org"},
            {"status": "applied", "new_path": "/v/b.org"},
        ],
        "skipped": [{"status": "skip", "path": "/v/c.org"}],
    }))
    cfg = Config(state_dir=tmp_path)
    assert paths_from_assign_apply(cfg) == ["/v/a.org", "/v/b.org"]


def test_paths_empty_when_no_assign_apply(tmp_path):
    assert paths_from_assign_apply(Config(state_dir=tmp_path)) == []


def test_dry_run_does_not_touch_emacs(tmp_path, monkeypatch):
    (tmp_path / "assign-apply.json").write_text(json.dumps({
        "applied": [{"status": "applied", "new_path": "/v/a.org"}],
    }))

    def boom(*a, **k):
        raise AssertionError("driver must not run on a dry run")

    monkeypatch.setattr(wire_backlinks, "_run_emacs_driver", boom)
    result = run(Config(state_dir=tmp_path, apply=False))
    assert result["apply"] is False
    assert result["paths"] == ["/v/a.org"]
    assert result["wired"] == []


def test_apply_partitions_results(tmp_path, monkeypatch):
    (tmp_path / "assign-apply.json").write_text(json.dumps({
        "applied": [{"status": "applied", "new_path": "/v/a.org"},
                    {"status": "applied", "new_path": "/v/b.org"}],
    }))

    def fake(config, paths):
        return [{"path": "/v/a.org", "status": "wired", "parent": "Root"},
                {"path": "/v/b.org", "status": "skipped", "message": "no parent"}]

    monkeypatch.setattr(wire_backlinks, "_run_emacs_driver", fake)
    result = run(Config(state_dir=tmp_path, apply=True))
    assert [w["status"] for w in result["wired"]] == ["wired"]
    assert [s["status"] for s in result["skipped"]] == ["skipped"]
