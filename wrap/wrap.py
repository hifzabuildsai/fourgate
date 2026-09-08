#!/usr/bin/env python3
"""
Fourgate — runtime wrap (Step 1: raw byte proxy)

Spawns a command-configured local stdio MCP server as a child process and
pumps bytes between the real client (this process's own stdin/stdout) and
the child, unchanged, in both directions.

This step deliberately does no JSON-RPC parsing, no classification, and no
rewriting — see specs/runtime-wrap.md FR-1 and plan.md Step 1. Later steps
add inspection on top of this proxy without touching what it forwards.

Design decisions (plan.md D1-D4):

  D1 - The exact bytes read from one side are the exact bytes written to
       the other. No JSON decode/re-encode touches the forwarded stream,
       so a healthy session stays byte-identical to running the server
       unwrapped.
  D2 - Both directions move raw bytes: this process's own stdin/stdout via
       `os.read`/`os.write` on the raw file descriptors (bypassing Python's
       TextIOWrapper, which would translate `\n` <-> `\r\n` on Windows),
       and the child's pipes opened with `text=False`.
  D3 - The child's stderr is inherited (not piped), so server logs reach
       the client's log exactly as they would unwrapped, and there is no
       stderr pipe for a chatty server to fill and deadlock on.
  D4 - Two plain reader threads (client->child, child->client) rather than
       `selectors` - `select()` on Windows does not accept subprocess
       pipes (see checker/preflight.py for the same constraint).

Usage:
    python wrap/wrap.py -- <command> [args...]
"""

import os
import subprocess
import sys
import threading

CHUNK_SIZE = 65536


def _parse_argv(argv):
    """Split `[wrap options...] -- <command> [args...]` into the two halves.

    Step 1 has no wrap-side options yet, so anything before `--` is
    ignored; later steps add --server-label/--baseline/--selfcheck here
    without changing how the command half is found.
    """
    if "--" not in argv:
        return argv
    idx = argv.index("--")
    return argv[idx + 1 :]


def _pump(read_fd, write_target, on_eof=None):
    """Copy raw bytes from `read_fd` to `write_target` until EOF or error.

    `write_target` is either a raw fd (int) or a file object with .write()
    (used for the child's stdin pipe). Each read is a single `os.read`
    call, so a small message is forwarded as soon as it arrives instead of
    waiting for a full CHUNK_SIZE buffer to accumulate.
    """
    try:
        while True:
            try:
                data = os.read(read_fd, CHUNK_SIZE)
            except OSError:
                break
            if not data:
                break
            try:
                if isinstance(write_target, int):
                    os.write(write_target, data)
                else:
                    write_target.write(data)
                    write_target.flush()
            except (BrokenPipeError, OSError, ValueError):
                break
    finally:
        if on_eof is not None:
            on_eof()


def _close_quietly(closeable):
    try:
        closeable.close()
    except OSError:
        pass


def run_proxy(target_cmd):
    """Spawn `target_cmd` and proxy stdio bytes until it exits.

    Returns the child's exit code.
    """
    proc = subprocess.Popen(
        target_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=None,  # inherited — D3
        bufsize=0,
    )

    stdin_to_child = threading.Thread(
        target=_pump,
        args=(0, proc.stdin),
        kwargs={"on_eof": lambda: _close_quietly(proc.stdin)},
        daemon=True,
    )
    child_to_stdout = threading.Thread(
        target=_pump,
        args=(proc.stdout.fileno(), 1),
        daemon=True,
    )

    stdin_to_child.start()
    child_to_stdout.start()

    returncode = proc.wait()
    # Let any output already in flight reach our stdout before we exit.
    child_to_stdout.join(timeout=2)

    return returncode


def main():
    target_cmd = _parse_argv(sys.argv[1:])
    if not target_cmd:
        print(
            "usage: wrap.py [options] -- <command> [args...]",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        returncode = run_proxy(target_cmd)
    except FileNotFoundError as exc:
        print(f"fourgate: failed to start wrapped server: {exc}", file=sys.stderr)
        sys.exit(1)

    sys.exit(returncode if returncode is not None else 1)


if __name__ == "__main__":
    main()
