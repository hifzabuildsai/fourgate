#!/usr/bin/env python3
"""Fourgate runtime wrap: byte-faithful stdio proxy + legacy classifiers + Outcome Guard."""
import concurrent.futures
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import baseline  # noqa: E402
import classify  # noqa: E402
import launch  # noqa: E402
import observe  # noqa: E402
import outcome  # noqa: E402
import verdict  # noqa: E402
import selfcheck  # noqa: E402

CHUNK_SIZE = 65536
CLASSIFY_BUDGET_SECS = 0.1
DEFAULT_SERVER_LABEL = "server"


def _parse_argv(argv):
    if "--" in argv:
        idx=argv.index("--"); wrap_args,target_cmd=argv[:idx],argv[idx+1:]
    else:
        wrap_args,target_cmd=[],argv
    baseline_path=None; server_label=DEFAULT_SERVER_LABEL; observe_path=None
    outcome_contracts_path=None; outcome_mode="shadow"; outcome_log_path=None
    i=0
    while i < len(wrap_args):
        arg=wrap_args[i]
        if arg=="--baseline" and i+1<len(wrap_args): baseline_path=wrap_args[i+1]; i+=2
        elif arg=="--server-label" and i+1<len(wrap_args): server_label=wrap_args[i+1]; i+=2
        elif arg=="--observe" and i+1<len(wrap_args): observe_path=wrap_args[i+1]; i+=2
        elif arg=="--outcome-contracts" and i+1<len(wrap_args): outcome_contracts_path=wrap_args[i+1]; i+=2
        elif arg=="--outcome-mode" and i+1<len(wrap_args): outcome_mode=wrap_args[i+1]; i+=2
        elif arg=="--outcome-log" and i+1<len(wrap_args): outcome_log_path=wrap_args[i+1]; i+=2
        else: i+=1
    return baseline_path,server_label,observe_path,outcome_contracts_path,outcome_mode,outcome_log_path,target_cmd


def _pump(read_fd, write_target, on_eof=None, on_line=None):
    line_buf=bytearray() if on_line is not None else None
    try:
        while True:
            try: data=os.read(read_fd, CHUNK_SIZE)
            except OSError: break
            if not data: break
            try:
                if isinstance(write_target,int): os.write(write_target,data)
                else: write_target.write(data); write_target.flush()
            except (BrokenPipeError,OSError,ValueError): break
            if on_line is not None:
                line_buf.extend(data)
                while True:
                    idx=line_buf.find(b"\n")
                    if idx==-1: break
                    line=bytes(line_buf[:idx]); del line_buf[:idx+1]; on_line(line)
    finally:
        if on_eof is not None: on_eof()


def _close_quietly(closeable):
    try: closeable.close()
    except OSError: pass


def _try_parse_json_object(line_bytes):
    try: text=line_bytes.decode("utf-8")
    except UnicodeDecodeError: return None
    if not text.strip(): return None
    try: obj=json.loads(text.strip())
    except json.JSONDecodeError: return None
    return obj if isinstance(obj,dict) else None


class CallTracker:
    """Independent bindings for legacy classify, observe, and Outcome Guard."""
    def __init__(self):
        self._lock=threading.Lock()
        self._pending={}
        self._pending_observe={}
        self._pending_outcome={}
    def track_request(self,line_bytes):
        obj=_try_parse_json_object(line_bytes)
        if obj is None or obj.get("method")!="tools/call": return
        req_id=obj.get("id")
        if req_id is None: return
        params=obj.get("params") or {}; tool_name=params.get("name"); arguments=params.get("arguments") or {}
        with self._lock:
            self._pending[req_id]=tool_name
            self._pending_observe[req_id]=tool_name
            self._pending_outcome[req_id]={"tool":tool_name,"arguments":arguments}
    def resolve_response(self,line_bytes):
        obj=_try_parse_json_object(line_bytes)
        if obj is None: return None
        resp_id=obj.get("id")
        if resp_id is None: return None
        with self._lock: tool_name=self._pending.pop(resp_id,None)
        if tool_name is None or "result" not in obj: return None
        return tool_name
    def resolve_for_observe(self,line_bytes):
        obj=_try_parse_json_object(line_bytes)
        if obj is None: return None
        resp_id=obj.get("id")
        if resp_id is None: return None
        with self._lock: return self._pending_observe.pop(resp_id,None)
    def resolve_for_outcome(self,line_bytes):
        obj=_try_parse_json_object(line_bytes)
        if obj is None: return None
        resp_id=obj.get("id")
        if resp_id is None: return None
        with self._lock: ctx=self._pending_outcome.pop(resp_id,None)
        if ctx is None or "result" not in obj: return None
        return ctx


def _bounded_call(fn, fault_env=None, timeout_secs=CLASSIFY_BUDGET_SECS):
    future=concurrent.futures.Future()
    def _worker():
        try:
            fault=os.environ.get(fault_env) if fault_env else None
            if fault=="raise": raise RuntimeError(f"{fault_env}=raise")
            if fault=="hang": time.sleep(5)
            value=fn()
        except Exception as exc:
            future.set_exception(exc)
        else:
            future.set_result(value)
    threading.Thread(target=_worker,daemon=True).start()
    try: return future.result(timeout=timeout_secs)
    except Exception: return None


def _run_classify_gate(result_obj, tool_name, contract):
    return _bounded_call(lambda: classify.classify(result_obj,tool_name,contract), "FOURGATE_FAULT")


def _run_outcome_gate(result_obj, arguments, qualified_tool, contract):
    verifier = contract.get("verifier") if isinstance(contract, dict) else None
    timeout_ms = verifier.get("timeout_ms") if isinstance(verifier, dict) else None
    if not isinstance(timeout_ms, int) or timeout_ms <= 0 or timeout_ms > outcome.MAX_VERIFIER_TIMEOUT_MS:
        timeout_secs = CLASSIFY_BUDGET_SECS
    else:
        # The verifier owns the declared I/O budget. This outer guard adds only
        # bounded process/setup slack so an internal Fourgate hang still fails open.
        timeout_secs = timeout_ms / 1000.0 + 0.15
    return _bounded_call(
        lambda: outcome.evaluate(result_obj, arguments, qualified_tool, contract),
        "FOURGATE_OUTCOME_FAULT",
        timeout_secs=timeout_secs,
    )


def _forward_response_line(line, write_fd, tracker, loaded_baseline, server_label, observe_path=None,
                           outcome_contracts=None, outcome_mode="shadow", outcome_log_path=None):
    result_obj=_try_parse_json_object(line)
    wrote_rewritten_line=False
    legacy_verdict=None

    outcome_ctx=tracker.resolve_for_outcome(line)
    if outcome_ctx is not None and result_obj is not None:
        tool_name=outcome_ctx.get("tool")
        contract=outcome.lookup(outcome_contracts, tool_name)
        if contract is not None:
            qualified_tool=f"{server_label}/{tool_name}"
            gate_started=time.monotonic()
            evaluation=_run_outcome_gate(result_obj,outcome_ctx.get("arguments") or {},qualified_tool,contract)
            gate_ms=int((time.monotonic()-gate_started)*1000)
            if evaluation is None:
                evaluation={"status":"unknown","reason_code":"gate_timeout_or_error"}
            outcome.append_record(outcome_log_path, outcome.record(server_label,tool_name,outcome_mode,evaluation,gate_ms=gate_ms))
            if outcome_mode=="enforce" and evaluation.get("status")=="fail":
                try:
                    rewritten=verdict.attach_prepend(result_obj,evaluation["verdict"])
                    os.write(write_fd,verdict.to_line(rewritten)); wrote_rewritten_line=True
                except Exception:
                    wrote_rewritten_line=False

    tool_name=tracker.resolve_response(line)
    if not wrote_rewritten_line and tool_name is not None and result_obj is not None:
        contract=baseline.lookup(loaded_baseline,tool_name)
        qualified_tool=f"{server_label}/{tool_name}"
        legacy_verdict=_run_classify_gate(result_obj,qualified_tool,contract)
        if legacy_verdict is not None:
            try:
                os.write(write_fd,verdict.to_line(verdict.attach(result_obj,legacy_verdict))); wrote_rewritten_line=True
            except Exception: wrote_rewritten_line=False

    if not wrote_rewritten_line:
        try: os.write(write_fd,line+b"\n")
        except OSError: pass

    observe_tool_name=tracker.resolve_for_observe(line)
    if observe_path is not None and observe_tool_name is not None:
        try:
            obj=result_obj if result_obj is not None else _try_parse_json_object(line)
            if obj is not None and "result" in obj:
                rec=observe.build_record(line,obj,observe_tool_name,server_label,legacy_verdict is not None)
            else:
                rec=observe.build_error_record(line,observe_tool_name,server_label)
            observe.append_record(observe_path,rec)
        except Exception: pass


def _pump_responses(read_fd,write_fd,tracker,loaded_baseline,server_label,observe_path=None,
                    outcome_contracts=None,outcome_mode="shadow",outcome_log_path=None,on_eof=None):
    buf=bytearray()
    try:
        while True:
            try: data=os.read(read_fd,CHUNK_SIZE)
            except OSError: break
            if not data: break
            buf.extend(data)
            while True:
                idx=buf.find(b"\n")
                if idx==-1: break
                line=bytes(buf[:idx]); del buf[:idx+1]
                _forward_response_line(line,write_fd,tracker,loaded_baseline,server_label,observe_path,
                                       outcome_contracts,outcome_mode,outcome_log_path)
        if buf:
            try: os.write(write_fd,bytes(buf))
            except OSError: pass
    finally:
        if on_eof is not None: on_eof()


def _server_env(secret_names):
    """Wrapped-server environment without verifier-only secrets; None inherits unchanged."""
    if not secret_names: return None
    # Windows env names are case-insensitive, so withhold every casing there.
    fold=(lambda name: name.upper()) if os.name=="nt" else (lambda name: name)
    withheld={fold(name) for name in secret_names}
    return {k:v for k,v in os.environ.items() if fold(k) not in withheld}


def run_proxy(target_cmd,loaded_baseline=None,server_label=DEFAULT_SERVER_LABEL,observe_path=None,
              outcome_contracts=None,outcome_mode="shadow",outcome_log_path=None):
    # The verifier subprocess still receives the full environment (outcome.evaluate).
    server_env=_server_env(outcome.secret_env_names(outcome_contracts))
    proc=subprocess.Popen(launch.resolve_command(target_cmd,server_env),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=None,bufsize=0,env=server_env)
    tracker=CallTracker()
    t1=threading.Thread(target=_pump,args=(0,proc.stdin),kwargs={"on_eof":lambda:_close_quietly(proc.stdin),"on_line":tracker.track_request},daemon=True)
    t2=threading.Thread(target=_pump_responses,args=(proc.stdout.fileno(),1,tracker,loaded_baseline,server_label),
                        kwargs={"observe_path":observe_path,"outcome_contracts":outcome_contracts,"outcome_mode":outcome_mode,"outcome_log_path":outcome_log_path},daemon=True)
    t1.start(); t2.start(); rc=proc.wait(); t2.join(timeout=2); return rc


def main():
    argv=sys.argv[1:]
    if "--selfcheck" in argv: sys.exit(selfcheck.run())
    baseline_path,server_label,observe_path,outcome_contracts_path,outcome_mode,outcome_log_path,target_cmd=_parse_argv(argv)
    if not target_cmd:
        print("usage: wrap.py [--baseline PATH] [--server-label LABEL] [--observe PATH] [--outcome-contracts PATH] [--outcome-mode shadow|enforce] [--outcome-log PATH] -- <command> [args...]",file=sys.stderr); sys.exit(2)
    if outcome_mode not in outcome.VALID_MODES:
        print("fourgate: --outcome-mode must be shadow or enforce",file=sys.stderr); sys.exit(2)
    loaded_baseline=baseline.load(baseline_path)
    loaded_outcomes=outcome.load(outcome_contracts_path)
    try:
        rc=run_proxy(target_cmd,loaded_baseline,server_label,observe_path,loaded_outcomes,outcome_mode,outcome_log_path)
    except FileNotFoundError as exc:
        print(f"fourgate: failed to start wrapped server: {exc}",file=sys.stderr); sys.exit(1)
    sys.exit(rc if rc is not None else 1)

if __name__=="__main__": main()
