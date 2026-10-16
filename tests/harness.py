"""Shared fixtures for test_e2e.py. Everything is derived from this file's location or
created under a throwaway directory, so the suite runs on any machine and never touches
the real ~/.claude, the real me/ files, or any project's real .claude/memory/."""
import atexit, os, subprocess, sys, time, shutil, json, tempfile, venv
from pathlib import Path

BRAIN = Path(__file__).resolve().parent.parent
HOOKS = BRAIN / "hooks"
PY = sys.executable

# One scratch root for the whole run: fixture projects, a fake home, the stub-git venv.
SP = Path(tempfile.mkdtemp(prefix="brain-tests-"))

def _force_rmtree(path):
    # git objects are read-only on Windows; clear the bit and retry
    shutil.rmtree(path, onerror=lambda f, pth, e: (os.chmod(pth, 0o700), f(pth)), ignore_errors=False)

def _cleanup():
    try:
        _force_rmtree(SP)
    except OSError as e:
        print(f"warning: could not remove {SP}: {e}", file=sys.stderr)
atexit.register(_cleanup)

# Redirect "home" for this process and every child it spawns, so brain-state snapshots land
# in the scratch root instead of the real ~/.claude/brain-state. Path.home() reads
# USERPROFILE on Windows and HOME elsewhere.
HOME = SP / "home"
HOME.mkdir()
os.environ["USERPROFILE"] = str(HOME)
os.environ["HOME"] = str(HOME)

def sh(*a, cwd=None):
    return subprocess.run(list(a), cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()

def make_project(name, now_text, review_ref=None, code_after_review=False):
    p = SP / "fx" / name
    if p.exists():
        _force_rmtree(p)
    mem = p / ".claude" / "memory"
    mem.mkdir(parents=True)
    sh("git", "init", "-q", cwd=p)
    sh("git", "config", "user.email", "t@t", cwd=p); sh("git", "config", "user.name", "t", cwd=p)
    (p / "a.py").write_text("x=1\n"); sh("git", "add", "-A", cwd=p); sh("git", "commit", "-qm", "one", cwd=p)
    first = sh("git", "rev-parse", "HEAD", cwd=p)
    (p / "b.py").write_text("y=1\n"); sh("git", "add", "-A", cwd=p); sh("git", "commit", "-qm", "two", cwd=p)
    head = sh("git", "rev-parse", "HEAD", cwd=p)
    (mem / "NOW.md").write_text(now_text.replace("{HEAD}", head[:7]).replace("{FIRST}", first[:7]), encoding="utf-8")
    (mem / "CHECKLIST.md").write_text("▶ NOW: 1 - x\n- [ ] 1 thing\n", encoding="utf-8")
    (mem / "PLAN.md").write_text("# Goal\nVerify: pytest\n## 1 thing\nwhy\n", encoding="utf-8")
    ref = review_ref.replace("{FIRST}", first[:7]).replace("{HEAD}", head[:7]) if review_ref else None
    if ref:
        (mem / "REVIEW.md").write_text(f"# Review\n- ref: {ref}\n", encoding="utf-8")
    return p, mem, first, head

_STUB_SITECUSTOMIZE = '''import os, sys, time, subprocess
mode = os.environ.get("STUBGIT_MODE")
if mode:
    args = sys.orig_argv[1:]
    if mode == "fail":
        os._exit(1)
    if mode == "hang" or (mode == "hang_on" and set(os.environ.get("STUBGIT_SUB", "").split(",")) & set(args)):
        time.sleep(float(os.environ.get("STUBGIT_SECS", "60")))
        os._exit(0)
    if mode == "hang_on":  # delegate everything else to the real git
        r = subprocess.run([os.environ["STUBGIT_REAL"], *args], stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr)
        os._exit(r.returncode)
'''

def build_stub_git():
    """Build a venv whose 'git' is a copy of its python plus a sitecustomize that can hang,
    fail, or delegate to the real git (STUBGIT_MODE). Returns the dir to put on PATH."""
    root = SP / "stubvenv"
    venv.EnvBuilder(with_pip=False, clear=True).create(root)
    scripts = root / ("Scripts" if os.name == "nt" else "bin")
    exe = "python.exe" if os.name == "nt" else "python"
    shutil.copy2(scripts / exe, scripts / ("git.exe" if os.name == "nt" else "git"))
    site = next((root / "Lib").glob("site-packages")) if os.name == "nt" else next((root / "lib").glob("python*/site-packages"))
    (site / "sitecustomize.py").write_text(_STUB_SITECUSTOMIZE, encoding="utf-8")
    return scripts

def env_with(path_prefix=None, **extra):
    e = dict(os.environ)
    if path_prefix:
        e["PATH"] = str(path_prefix) + os.pathsep + e["PATH"]
    e.update(extra)
    return e

def run_hook(script, project, stdin="{}", env=None, isolated=False, timeout=60):
    e = dict(env or os.environ); e["CLAUDE_PROJECT_DIR"] = str(project)
    cmd = [PY] + (["-I"] if isolated else []) + [str(HOOKS / script)]
    t = time.time()
    r = subprocess.run(cmd, input=stdin, capture_output=True, text=True, encoding="utf-8", env=e, cwd=str(project), timeout=timeout)
    return r.returncode, r.stdout, r.stderr, time.time() - t
