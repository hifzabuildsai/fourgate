import json
import os
import sys
import time
from pathlib import Path

from _support import ScriptedSession, run_initialize

REPO_ROOT=Path(__file__).resolve().parent.parent
WRAP=REPO_ROOT/"wrap"/"wrap.py"
SERVER=REPO_ROOT/"fixtures"/"outcome_server.py"
CONTRACTS=REPO_ROOT/"fixtures"/"contracts"/"outcome_demo.json"
MARKER="[FOURGATE]"


def _cmd(mode="enforce", log=None):
    cmd=[sys.executable,str(WRAP),"--outcome-contracts",str(CONTRACTS),"--outcome-mode",mode,"--server-label","demo"]
    if log is not None: cmd += ["--outcome-log",str(log)]
    cmd += ["--",sys.executable,str(SERVER)]
    return cmd


def _direct_cmd(): return [sys.executable,str(SERVER)]


def _session(cmd, store, server_mode="broken", verifier_mode="normal", log=None):
    env=os.environ.copy(); env["FOURGATE_DEMO_STORE"]=str(store); env["FOURGATE_DEMO_MODE"]=server_mode; env["FOURGATE_DEMO_VERIFIER"]=verifier_mode
    s=ScriptedSession(cmd,env=env); run_initialize(s)
    tools=s.send_request("tools/list",{}); assert tools is not None and "result" in tools
    return s


def _call(s,title="CANARY-TITLE-do-not-log"):
    return s.send_request("tools/call",{"name":"create_issue","arguments":{"title":title}})


def _verdict(response):
    content=response["result"]["content"]
    text=content[0]["text"]
    assert text.startswith(MARKER)
    return json.loads(text[len(MARKER):].strip())


def test_broken_write_gets_outcome_failed_and_preserves_original(tmp_path):
    store=tmp_path/"issues.json"
    s=_session(_cmd("enforce"),store,"broken")
    try: response=_call(s)
    finally: s.close()
    v=_verdict(response)
    assert v=={
        "kind":"outcome_failed",
        "tool":"demo/create_issue",
        "evidence":{"reason_code":"record_missing","checked_fields":["issue_id","title"]},
        "recovery":"stop",
    }
    assert response["result"]["content"][1]["text"]=="Created ISSUE-001"
    assert response["result"]["structuredContent"]=={"issue_id":"ISSUE-001"}
    assert not store.exists()


def test_healthy_write_passes_through_unchanged(tmp_path):
    direct_store=tmp_path/"direct.json"; wrapped_store=tmp_path/"wrapped.json"
    d=_session(_direct_cmd(),direct_store,"healthy")
    try:
        direct=_call(d,"healthy title")
        direct_bytes=d.close()
    finally:
        if d.proc.poll() is None: d.proc.kill()
    w=_session(_cmd("enforce"),wrapped_store,"healthy")
    try:
        wrapped=_call(w,"healthy title")
        wrapped_bytes=w.close()
    finally:
        if w.proc.poll() is None: w.proc.kill()
    assert wrapped==direct
    assert wrapped_bytes==direct_bytes
    assert MARKER not in wrapped["result"]["content"][0]["text"]
    assert wrapped_store.exists()


def test_shadow_records_failure_but_does_not_change_response(tmp_path):
    store=tmp_path/"issues.json"; log=tmp_path/"outcomes.jsonl"; title="SECRET-CUSTOMER-TITLE-7f31"
    direct=_session(_direct_cmd(),store,"broken")
    try:
        expected=_call(direct,title)
        expected_bytes=direct.close()
    finally:
        if direct.proc.poll() is None: direct.proc.kill()
    shadow=_session(_cmd("shadow",log),store,"broken")
    try:
        got=_call(shadow,title)
        got_bytes=shadow.close()
    finally:
        if shadow.proc.poll() is None: shadow.proc.kill()
    assert got==expected
    assert got_bytes==expected_bytes
    record=json.loads(log.read_text().strip())
    assert record["status"]=="fail" and record["reason_code"]=="record_missing"
    assert record["checked_fields"]==["issue_id","title"]
    assert title not in log.read_text()
    assert "ISSUE-001" not in log.read_text()


def test_verifier_crash_timeout_and_malformed_fail_open(tmp_path):
    for verifier_mode in ("crash","hang","malformed","unapproved"):
        store=tmp_path/f"{verifier_mode}.json"
        direct=_session(_direct_cmd(),store,"broken",verifier_mode)
        try: expected=_call(direct,"x")
        finally: direct.close()
        wrapped=_session(_cmd("enforce"),store,"broken",verifier_mode)
        start=time.monotonic()
        try:
            got=_call(wrapped,"x")
            elapsed=time.monotonic()-start
        finally: wrapped.close()
        assert got==expected, verifier_mode
        assert MARKER not in got["result"]["content"][0]["text"]
        assert elapsed < 1.25, (verifier_mode,elapsed)


def test_internal_outcome_gate_hang_fails_open(tmp_path):
    store=tmp_path/"issues.json"; env=os.environ.copy(); env["FOURGATE_DEMO_STORE"]=str(store); env["FOURGATE_DEMO_MODE"]="broken"; env["FOURGATE_OUTCOME_FAULT"]="hang"
    s=ScriptedSession(_cmd("enforce"),env=env); run_initialize(s); s.send_request("tools/list",{})
    start=time.monotonic()
    try:
        got=_call(s,"x")
        elapsed=time.monotonic()-start
    finally: s.close()
    assert MARKER not in got["result"]["content"][0]["text"]
    assert elapsed < 1.25


def test_argument_result_correlation_isolated():
    import importlib.util
    spec=importlib.util.spec_from_file_location("fourgate_wrap",WRAP); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    t=mod.CallTracker()
    def req(i,title): return json.dumps({"jsonrpc":"2.0","id":i,"method":"tools/call","params":{"name":"create_issue","arguments":{"title":title}}}).encode()
    def resp(i): return json.dumps({"jsonrpc":"2.0","id":i,"result":{"structuredContent":{"issue_id":f"ISSUE-{i}"}}}).encode()
    t.track_request(req(1,"one")); t.track_request(req(2,"two"))
    assert t.resolve_for_outcome(resp(2))=={"tool":"create_issue","arguments":{"title":"two"}}
    assert t.resolve_for_outcome(resp(1))=={"tool":"create_issue","arguments":{"title":"one"}}


def test_field_mismatch_is_confirmed_without_leaking_values(tmp_path):
    store=tmp_path/"issues.json"
    store.write_text(json.dumps([{"id":"ISSUE-001","title":"different-secret-title"}]), encoding="utf-8")
    s=_session(_cmd("enforce"),store,"broken")
    try: response=_call(s,"requested-secret-title")
    finally: s.close()
    v=_verdict(response)
    assert v["evidence"]=={"reason_code":"field_mismatch","checked_fields":["issue_id","title"]}
    encoded=json.dumps(v)
    assert "different-secret-title" not in encoded
    assert "requested-secret-title" not in encoded


def test_uncontracted_tool_path_is_transparent(tmp_path):
    store=tmp_path/"issues.json"
    env=os.environ.copy(); env["FOURGATE_DEMO_STORE"]=str(store); env["FOURGATE_DEMO_MODE"]="broken"
    cmd=[sys.executable,str(WRAP),"--server-label","demo","--",sys.executable,str(SERVER)]
    s=ScriptedSession(cmd,env=env); run_initialize(s); s.send_request("tools/list",{})
    try: response=_call(s,"x")
    finally: s.close()
    assert response["result"]["content"][0]["text"]=="Created ISSUE-001"
    assert MARKER not in response["result"]["content"][0]["text"]


def test_shadow_is_default_mode():
    import importlib.util
    spec=importlib.util.spec_from_file_location("fourgate_wrap_defaults",WRAP); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    parsed=mod._parse_argv(["--outcome-contracts",str(CONTRACTS),"--",sys.executable,str(SERVER)])
    assert parsed[4]=="shadow"
