"""Verify this repository's changes and run its existing local test suites."""

import argparse
import ast
from collections import Counter
import os
from pathlib import Path
import subprocess
import sys
import tempfile


AUDIT = "skills/audit-codex-work-quality/scripts/"
CHECKER = "scripts/check-repo.py"
SHARED = {CHECKER, ".github/workflows/ci.yml", ".githooks/pre-commit"}
DECLARATIONS = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def git(*args):
    """Read Git data without shell interpretation of paths."""
    return subprocess.check_output(["git", *args])


def check_python(path, previous, current):
    """Lint Python syntax and require docstrings on new or changed declarations."""
    compile(current, path, "exec")
    before = Counter(
        ast.dump(node) for node in ast.walk(ast.parse(previous, path))
        if isinstance(node, DECLARATIONS)
    )
    ok = True
    for node in ast.walk(ast.parse(current, path)):
        # Match unchanged syntax so existing declarations need no bulk rewrite.
        if not isinstance(node, DECLARATIONS):
            continue
        declaration = ast.dump(node)
        if before[declaration]:
            before[declaration] -= 1
        elif not (ast.get_docstring(node) or "").strip():
            print(f"{path}:{node.lineno}: {node.name} needs a docstring", file=sys.stderr)
            ok = False
    return ok


def check_diff(base, staged):
    """Check the selected Git diff and return the paths used to route tests."""
    comparison = ["--cached"] if staged else [base, "HEAD"]
    subprocess.run(["git", "diff", "--check", *comparison, "--"], check=True)
    changes = git("diff", "--name-status", "-z", "--no-renames", *comparison, "--")
    entries = os.fsdecode(changes).split("\0")[:-1]
    ok = True
    paths = set()
    for change, path in zip(entries[::2], entries[1::2], strict=True):
        # Deleted files still select suites, but only current Python text is linted.
        paths.add(path)
        if change == "D" or not (path == CHECKER or (path.startswith(AUDIT) and path.endswith(".py"))):
            continue
        previous = b"" if change == "A" else git("show", f"{base}:{path}")
        current = git("show", f"{'' if staged else 'HEAD'}:{path}")
        ok = check_python(path, previous, current) and ok
    if not ok:
        raise SystemExit(1)
    return paths


def audit_tests(root, env=None):
    """Run the public audit entry-point syntax checks and regression suites."""
    for name in ("collect_session_evidence.py", "audit_history.py"):
        # Compile in memory so verification does not modify the checkout.
        path = root / AUDIT / name
        compile(path.read_bytes(), str(path), "exec")
    subprocess.run([
        sys.executable, "-X", "utf8", "-B", "-m", "unittest",
        AUDIT + "test_collect_session_evidence.py", AUDIT + "test_audit_history.py",
    ], cwd=root, env=env, check=True)


def staged_tests(paths):
    """Run affected suites against the index rather than the working files."""
    audit = bool(paths & SHARED) or any(path.startswith(AUDIT) for path in paths)
    hooks = bool(paths & (SHARED | {"hooks.json"})) or any(path.startswith("hooks/") for path in paths)
    if hooks and sys.platform != "win32":
        print("Windows hook tests require Windows; run them in Windows CI.", flush=True)
        hooks = False
    if not (audit or hooks):
        return

    # Keep the checkout's index and Git environment out of the test subprocesses.
    git_vars = git("rev-parse", "--local-env-vars").decode().splitlines()
    env = {key: value for key, value in os.environ.items() if key not in git_vars}
    with tempfile.TemporaryDirectory(prefix="codex-pre-commit-") as temporary:
        root = Path(temporary)
        git("checkout-index", "--all", "--ignore-skip-worktree-bits", f"--prefix={root.as_posix()}/")
        if audit:
            audit_tests(root, env)
        if hooks:
            subprocess.run(["pwsh", "-NoProfile", "-File", "hooks/test-windows-launch.ps1"],
                           cwd=root, env=env, check=True)


def main():
    """Dispatch the same checks from the Git hook, shell, or CI."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--staged", action="store_true", help="lint the index and run affected tests")
    mode.add_argument("--from", dest="base", help="lint the committed diff from this base to HEAD")
    mode.add_argument("--audit", action="store_true", help="run audit checks and tests in this checkout")
    args = parser.parse_args()

    try:
        # Tests and matching path prefixes always use the repository root.
        os.chdir(os.fsdecode(git("rev-parse", "--show-toplevel").strip()))
        if args.audit:
            audit_tests(Path.cwd())
        elif args.staged:
            staged_tests(check_diff("HEAD", staged=True))
        else:
            base = git("rev-parse", "--verify", "--end-of-options", f"{args.base}^{{commit}}").decode().strip()
            check_diff(base, staged=False)
    except (OSError, subprocess.CalledProcessError, SyntaxError) as error:
        print(f"Repository check failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
