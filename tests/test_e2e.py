import sys, os, json, shutil, time
from pathlib import Path

# Windows-only: section B holds memory files open with an exclusive kernel32 handle, and
# section D strips PATH to the Windows system dirs. Skip cleanly elsewhere, with the reason.
if os.name != "nt":
    print("SKIP test_e2e.py: needs Windows (exclusive file locks via kernel32, Windows PATH layout)")
    sys.exit(0)
if shutil.which("git") is None:
    print("SKIP test_e2e.py: git is not on PATH")
    sys.exit(0)

import ctypes
from ctypes import wintypes
sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import *

STUB = build_stub_git()
real_git = shutil.which("git")
print("real git:", real_git)
STATE = Path.home() / ".claude" / "brain-state"

def show(label, rc, out, err, dt, extra=""):
    print(f"{label:46s} rc={rc} secs={dt:4.1f} memory_printed={'Project memory' in out} rot={'MEMORY ROT' in out} drift={'LEDGER DRIFT' in out} {extra} stderr={err.strip()[-120:]!r}")

# ---------- A. normal + isolated (-I) ----------
p, mem, first, head = make_project("e1", "HEAD {HEAD}\n", review_ref="{HEAD}")
for iso in (False, True):
    rc, out, err, dt = run_hook("memory_load.py", p, '{"session_id":"e2e-1"}', isolated=iso)
    show(f"loader normal (isolated={iso})", rc, out, err, dt)
snap = STATE / "e2e-1.memsnap.json"
print("snapshot written after print:", snap.exists(), json.loads(snap.read_text()) if snap.exists() else None)

# ---------- B. locked memory file (exclusive handle, like a cloud-sync client or antivirus) ----------
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.CreateFileW.restype = wintypes.HANDLE
k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
def hold(path):
    h = k32.CreateFileW(str(path), 0x80000000, 0, None, 3, 0x80, None)  # GENERIC_READ, share=0, OPEN_EXISTING
    assert h not in (None, wintypes.HANDLE(-1).value, 0xFFFFFFFFFFFFFFFF, -1), ctypes.get_last_error()
    return h
for victim in ("NOW.md", "CHECKLIST.md", "PLAN.md", "REVIEW.md"):
    h = hold(mem / victim)
    try:
        try:
            (mem / victim).read_bytes(); locked = False
        except PermissionError:
            locked = True
        rc, out, err, dt = run_hook("memory_load.py", p, '{"session_id":"e2e-lock"}')
        show(f"loader, {victim} held exclusively (locked={locked})", rc, out, err, dt)
        rc2, out2, err2, dt2 = run_hook("memory_stop.py", p, json.dumps({"session_id": "e2e-lock", "last_assistant_message": "done\nmemory: none"}))
        print(f"{'':46s} stop hook same lock: rc={rc2} out={out2.strip()[:100]!r} stderr={err2.strip()[-100:]!r}")
    finally:
        k32.CloseHandle(h)

# ---------- C. loader still prints when the snapshot path fails ----------
import importlib
env = dict(os.environ)
# make the snapshot dir unusable: point HOME-derived STATE_DIR at a file by overriding USERPROFILE
fake_home = SP / "fakehome"; shutil.rmtree(fake_home, ignore_errors=True); fake_home.mkdir()
(fake_home / ".claude").write_text("i am a file, not a directory")
env["USERPROFILE"] = str(fake_home); env["HOME"] = str(fake_home)
rc, out, err, dt = run_hook("memory_load.py", p, '{"session_id":"e2e-badstate"}', env)
show("loader with unusable state dir", rc, out, err, dt)

# ---------- D. no git on PATH (executed, not read) ----------
p2, mem2, first2, head2 = make_project("e2", "HEAD {FIRST}\nREVIEW.md is at {FIRST}\n", review_ref="{FIRST}")
rc, out, err, dt = run_hook("memory_load.py", p2, '{"session_id":"e2e-nogit"}', None)
show("with git on PATH (control: rot + drift expected)", rc, out, err, dt)
nogit_env = dict(os.environ); sysroot = os.environ.get("SystemRoot", "")
nogit_env["PATH"] = os.pathsep.join([str(Path(sysroot) / "System32"), sysroot])
import subprocess
chk = subprocess.run(["where", "git"], capture_output=True, text=True, env=nogit_env)
print("where git under stripped PATH ->", "NOT FOUND" if chk.returncode else chk.stdout.strip())
rc, out, err, dt = run_hook("memory_load.py", p2, '{"session_id":"e2e-nogit"}', nogit_env)
show("NO git on PATH", rc, out, err, dt)
# prove the executed path really was the FileNotFound path
code = ("import sys; sys.path.insert(0, r'%s'); import memrot, pathlib; "
        "print('head_full ->', memrot.head_full(pathlib.Path(r'%s'))); "
        "import subprocess\ntry:\n subprocess.run(['git','--version'])\nexcept Exception as e: print('subprocess ->', type(e).__name__)" % (HOOKS, p2))
r = subprocess.run([PY, "-c", code], capture_output=True, text=True, env=nogit_env)
print(r.stdout.strip(), r.stderr.strip()[-200:])

# ---------- E. hung git: budget ----------
for sub in ("cat-file", "diff", "rev-parse"):
    env = env_with(STUB, STUBGIT_MODE="hang_on", STUBGIT_SUB=sub, STUBGIT_SECS="30", STUBGIT_REAL=real_git)
    rc, out, err, dt = run_hook("memory_load.py", p2, '{"session_id":"e2e-hang"}', env, timeout=90)
    show(f"git hangs on '{sub}' (30s)", rc, out, err, dt)
env = env_with(STUB, STUBGIT_MODE="hang", STUBGIT_SECS="30")
rc, out, err, dt = run_hook("memory_load.py", p2, '{"session_id":"e2e-hang"}', env, timeout=90)
show("every git call hangs", rc, out, err, dt)
env = env_with(STUB, STUBGIT_MODE="fail")
rc, out, err, dt = run_hook("memory_load.py", p2, '{"session_id":"e2e-hang"}', env, timeout=90)
show("every git call exits 1", rc, out, err, dt)

# ---------- F. review gate itself still works ----------
gate_in = json.dumps({"tool_name": "Agent", "tool_input": {"subagent_type": "coder"}})
rc, out, err, dt = run_hook("review_gate.py", p2, gate_in, isolated=True)
print("review_gate (stale ref, coder agent):", rc, out.strip()[:140], err.strip()[-100:])
rc, out, err, dt = run_hook("review_gate.py", p, gate_in, isolated=True)
print("review_gate (ref==HEAD, coder agent):", rc, repr(out.strip()[:80]), err.strip()[-100:])

# ---------- G. stop hook end to end ----------
p3, mem3, _, _ = make_project("e3", "HEAD {HEAD}\n", review_ref="{HEAD}")
sid = "e2e-stop"
run_hook("memory_load.py", p3, json.dumps({"session_id": sid}))
def stop(msg, **kw):
    rc, out, err, dt = run_hook("memory_stop.py", p3, json.dumps({"session_id": sid, "last_assistant_message": msg, **kw}), isolated=True)
    return rc, out.strip()[:170], err.strip()[-100:]
print("stop: nothing changed, 'memory: none'      ->", stop("ok\nmemory: none"))
print("stop: nothing changed, 'memory: n/a'       ->", stop("ok\nmemory: n/a"))
print("stop: nothing changed, quote in fence only ->", stop("The rule is\n```\nmemory: none\n```\nand that's it"))
(mem3 / "REVIEW.md").write_text("# Review\n- ref: changed\n", encoding="utf-8")
print("stop: REVIEW.md changed, 'REVIEW.md ticked' ->", stop("ok\nmemory: REVIEW.md ticked 3 findings"))
(mem3 / "NOW.md").write_text("changed\n", encoding="utf-8")
print("stop: NOW.md changed, 'none'               ->", stop("ok\nmemory: none"))
# corrupt baseline (valid JSON, not an object)
(STATE / f"{sid}.memsnap.json").write_text("[]")
print("stop: baseline is '[]'                      ->", stop("ok\nmemory: none"))

# cleanup state files we made
for f in STATE.glob("e2e-*.memsnap.json"):
    f.unlink()
