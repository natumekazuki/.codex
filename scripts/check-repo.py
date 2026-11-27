"""Verify this repository's changes and run its existing local test suites."""

import argparse
import ast
from collections import Counter
from difflib import SequenceMatcher
from io import BytesIO
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tokenize


AUDIT = "skills/audit-codex-work-quality/scripts/"
CHECKER = "scripts/check-repo.py"
SHARED = {CHECKER, ".github/workflows/ci.yml", ".githooks/pre-commit"}
DECLARATIONS = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def git(*args):
    """Read Git data without shell interpretation of paths."""
    return subprocess.check_output(["git", *args])


def declaration_starts(source):
    """Map declaration headers and locate a recoverable line-local lexer error."""
    starts = {}
    first_decorator = None
    at_statement_start = True

    # Use logical statement boundaries so text inside strings or expressions
    # does not count as a declaration in a syntactically broken baseline.
    try:
        # Scan as far as the lexer can identify statement boundaries.
        for token in tokenize.tokenize(BytesIO(source).readline):
            # Trivia does not interrupt a declaration's decorator list.
            if token.type in (tokenize.ENCODING, tokenize.INDENT, tokenize.DEDENT,
                              tokenize.NL, tokenize.COMMENT):
                continue
            if at_statement_start:
                # Include the first decorator even when its expression starts on a later line.
                if token.type == tokenize.OP and token.string == "@":
                    first_decorator = first_decorator or token.start[0]
                else:
                    # Any non-decorator statement ends the pending decorator list.
                    if token.type == tokenize.NAME and token.string in ("class", "def", "async"):
                        starts[token.start] = first_decorator or token.start[0]
                    first_decorator = None
            at_statement_start = token.type == tokenize.NEWLINE
    except IndentationError as error:
        # A bad indent can stop the lexer before unrelated declarations.
        return starts, error.lineno
    except tokenize.TokenError as error:
        # These failures are confined to a single line. Do not restart at an
        # open multi-line string or expression, which may contain apparent code.
        message, (line, _) = error.args
        if message.startswith("unterminated string literal") or message == "source code cannot contain null bytes":
            return starts, line
    except (SyntaxError, UnicodeError):
        # Preserve headers already identified; do not infer any beyond the lexer error.
        pass
    return starts, None


def unchanged_declarations(previous, current, declarations):
    """Find verbatim declarations when the baseline cannot be parsed as a module."""
    old_lines = previous.splitlines()
    new_starts, _ = declaration_starts(current)
    matches = SequenceMatcher(None, old_lines, current.splitlines(), autojunk=False)
    unchanged = set()
    blocks = matches.get_matching_blocks()
    old_starts, error_line = declaration_starts(previous)
    if error_line and not any(start < error_line <= start + size for start, _, size in blocks):
        # If the edit fixes the lexer-stopping line, mask just that old line
        # to identify later headers without changing their source positions.
        old_lines[error_line - 1] = b""
        recovered, _ = declaration_starts(b"\n".join(old_lines))
        old_starts = recovered | old_starts

    # Require one uninterrupted match for the entire declaration, including
    # decorators, and a real header at the corresponding old position.
    for node in declarations:
        header = (node.lineno, node.col_offset)
        first_line = new_starts[header]
        if any(
            new_line < first_line and node.end_lineno <= new_line + size
            and old_starts.get((old_line + node.lineno - new_line, node.col_offset))
            == old_line + first_line - new_line
            for old_line, new_line, size in blocks
        ):
            # A proven unchanged declaration does not need a docstring added for the repair.
            unchanged.add(node)
    return unchanged


def check_python(path, previous, current):
    """Lint Python syntax and require docstrings on new or changed declarations."""
    # The candidate must compile even when the old version cannot be parsed.
    compile(current, path, "exec")
    declarations = [
        node for node in ast.walk(ast.parse(current, path))
        if isinstance(node, DECLARATIONS)
    ]
    try:
        # An intact baseline allows syntax comparison independent of layout.
        before = Counter(
            ast.dump(node) for node in ast.walk(ast.parse(previous, path))
            if isinstance(node, DECLARATIONS)
        )
        unchanged = set()
    except SyntaxError:
        # A broken baseline must not block a fix or excuse changed declarations.
        before = Counter()
        unchanged = unchanged_declarations(previous, current, declarations)

    ok = True
    # Account for each declaration once and report every missing docstring.
    for node in declarations:
        if node in unchanged:
            # The text match already accounts for this declaration in a broken baseline.
            continue
        declaration = ast.dump(node)
        if before[declaration]:
            # Consume one matching old declaration so added duplicates do not pass.
            before[declaration] -= 1
        elif not (ast.get_docstring(node) or "").strip():
            # Point to the new or edited declaration rather than the containing diff hunk.
            print(f"{path}:{node.lineno}: {node.name} needs a docstring", file=sys.stderr)
            ok = False
    return ok


def check_diff(base, staged):
    """Check the selected Git diff and return the paths used to route tests."""
    # Compare the index for a commit, or the immutable candidate in CI.
    comparison = ["--cached"] if staged else [base, "HEAD"]
    subprocess.run(["git", "diff", "--check", *comparison, "--"], check=True)
    changes = git("diff", "--name-status", "-z", "--no-renames", *comparison, "--")
    entries = os.fsdecode(changes).split("\0")[:-1]
    ok = True
    paths = set()
    # Route suites from every changed path, but lint only maintained Python source.
    for change, path in zip(entries[::2], entries[1::2], strict=True):
        paths.add(path)
        if change == "D" or not (path == CHECKER or (path.startswith(AUDIT) and path.endswith(".py"))):
            # Deleted or out-of-scope paths have no candidate Python to inspect.
            continue
        # Read both blobs from Git so unstaged edits cannot affect a commit check.
        previous = b"" if change == "A" else git("show", f"{base}:{path}")
        current = git("show", f"{'' if staged else 'HEAD'}:{path}")
        ok = check_python(path, previous, current) and ok
    if not ok:
        # Stop before test execution if any declaration failed lint.
        raise SystemExit(1)
    return paths


def audit_tests(root, env=None):
    """Run the public audit entry-point syntax checks and regression suites."""
    # Compile audit entry points in memory before running their suites.
    for name in ("collect_session_evidence.py", "audit_history.py"):
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
        # Leave the platform-specific suite to the Windows runner.
        print("Windows hook tests require Windows; run them in Windows CI.", flush=True)
        hooks = False
    if not (audit or hooks):
        # Avoid exporting the index when no runnable suite is affected.
        return

    # Keep the checkout's index and Git environment out of the test subprocesses.
    git_vars = git("rev-parse", "--local-env-vars").decode().splitlines()
    env = {key: value for key, value in os.environ.items() if key not in git_vars}
    with tempfile.TemporaryDirectory(prefix="codex-pre-commit-") as temporary:
        root = Path(temporary)
        git("checkout-index", "--all", "--ignore-skip-worktree-bits", f"--prefix={root.as_posix()}/")
        if audit:
            # Exercise audit code and fixtures from the staged snapshot.
            audit_tests(root, env)
        if hooks:
            # Exercise the staged hook commands on their supported platform.
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

    # Use the repository root for every mode, and report tool or syntax failures
    # to the caller rather than allowing a commit with incomplete verification.
    try:
        os.chdir(os.fsdecode(git("rev-parse", "--show-toplevel").strip()))
        if args.audit:
            # Run only the audit suite against the checked-out candidate.
            audit_tests(Path.cwd())
        elif args.staged:
            # Verify the index and select suites from the files being committed.
            staged_tests(check_diff("HEAD", staged=True))
        else:
            # Pin the base for CI's comparison with the checked-out commit.
            base = git("rev-parse", "--verify", "--end-of-options", f"{args.base}^{{commit}}").decode().strip()
            check_diff(base, staged=False)
    except (OSError, subprocess.CalledProcessError, SyntaxError) as error:
        # Turn Git, compiler, or test failures into a nonzero hook/CI exit.
        print(f"Repository check failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    # Importing the checker for isolated verification must not run repository commands.
    raise SystemExit(main())
