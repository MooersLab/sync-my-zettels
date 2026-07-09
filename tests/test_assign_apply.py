import json

from sync_my_zettels.config import Config
from sync_my_zettels import assign_apply
from sync_my_zettels.assign_apply import (
    title_with_address,
    address_filename,
    plan_assignments,
)


def test_title_with_address_prepends():
    assert title_with_address("Comparison of Nim and Zig", "8.1") == (
        "8.1 Comparison of Nim and Zig"
    )


def test_address_filename_inserts_slug_after_timestamp():
    got = address_filename("/v/20260115141112-comparison_nim.org", "8.1")
    assert got == "/v/20260115141112-8_1_comparison_nim.org"


def test_address_filename_none_when_no_timestamp():
    assert address_filename("/v/plainname.org", "8.1") is None


def _note(dir_, name, title):
    p = dir_ / name
    p.write_text(f":PROPERTIES:\n:ID: x\n:END:\n#+title: {title}\n\nbody\n")
    return p


def test_plan_guards_note_that_already_has_address(tmp_path):
    _note(tmp_path, "20260101000000-has_addr.org", "8.1 Already Addressed")
    conf = {"confirmed": [{"path": str(tmp_path / "20260101000000-has_addr.org"),
                           "address": "8.2", "title": "Already Addressed"}]}
    (tmp_path / "assignments.json").write_text(json.dumps(conf))
    cfg = Config(state_dir=tmp_path)
    plan = plan_assignments(cfg)
    assert plan[0]["action"] == "skip"
    assert "already has address 8.1" in plan[0]["reason"]


def test_plan_and_apply_assigns_first_address(tmp_path):
    note = _note(tmp_path, "20260101000000-nim.org", "Comparison of Nim")
    conf = {"confirmed": [{"path": str(note), "address": "8.1", "title": "Comparison of Nim"}]}
    (tmp_path / "assignments.json").write_text(json.dumps(conf))

    # dry run: plans an assign, writes nothing
    cfg_dry = Config(state_dir=tmp_path, apply=False)
    plan = plan_assignments(cfg_dry)
    assert plan[0]["action"] == "assign"
    assert plan[0]["new_title"] == "8.1 Comparison of Nim"
    assert plan[0]["new_path"].endswith("20260101000000-8_1_nim.org")
    assert note.read_text().count("#+title: Comparison of Nim") == 1  # untouched

    # apply: monkeypatch the DB reconcile so no Emacs is needed
    applied = [assign_apply._apply_row(r) for r in plan if r["action"] == "assign"]
    assert applied[0]["status"] == "applied"
    moved = tmp_path / "20260101000000-8_1_nim.org"
    assert moved.exists() and not note.exists()
    assert "#+title: 8.1 Comparison of Nim" in moved.read_text()
