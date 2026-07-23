"""
test_audit_log.py, Permission Bridge audit trail, per-user and per-org
scoping. No external credentials needed, this is an in-memory/local-file
log, not a call to any external service.
"""

import os

from permission_bridge.permission_bridge import AuditLog, NodeAction


def _log(tmp_path):
    return AuditLog(log_path=str(tmp_path / "test_audit.log"))


def test_records_and_retrieves_entries(tmp_path):
    log = _log(tmp_path)
    action = NodeAction("http_request", "example.com", "read")
    log.record("n1", "Node A", action, "allowed", "within scope", user_id="alice")

    entries = log.get_recent(10)
    assert len(entries) == 1
    assert entries[0]["user_id"] == "alice"
    assert entries[0]["outcome"] == "allowed"


def test_single_user_scoping(tmp_path):
    log = _log(tmp_path)
    action = NodeAction("http_request", "example.com", "read")
    log.record("n1", "Node A", action, "allowed", "ok", user_id="alice")
    log.record("n2", "Node B", action, "allowed", "ok", user_id="bob")

    alice_entries = log.get_recent(10, user_id="alice")
    assert len(alice_entries) == 1
    assert alice_entries[0]["user_id"] == "alice"


def test_org_level_multi_user_scoping_excludes_outsiders(tmp_path):
    """The exact scenario an org admin's audit export relies on: everyone
    on the team, nobody outside it."""
    log = _log(tmp_path)
    action = NodeAction("http_request", "example.com", "read")
    log.record("n1", "Node A", action, "allowed", "ok", user_id="alice")   # org member
    log.record("n2", "Node B", action, "allowed", "ok", user_id="bob")     # org member
    log.record("n3", "Node C", action, "allowed", "ok", user_id="carol")  # NOT in the org

    org_members = {"alice", "bob"}
    org_entries = log.get_recent(100, user_ids=org_members)

    assert len(org_entries) == 2
    assert {e["user_id"] for e in org_entries} == org_members
    assert "carol" not in {e["user_id"] for e in org_entries}


def test_entries_without_user_id_excluded_from_scoped_queries(tmp_path):
    """Entries recorded before per-tenant auditing existed have user_id=None
   , a scoped query should never accidentally include them."""
    log = _log(tmp_path)
    action = NodeAction("http_request", "example.com", "read")
    log.record("n1", "Legacy node", action, "allowed", "ok")  # no user_id at all

    assert log.get_recent(10, user_id="alice") == []
    assert log.get_recent(10, user_ids={"alice"}) == []
    assert len(log.get_recent(10)) == 1  # unscoped query still sees it
