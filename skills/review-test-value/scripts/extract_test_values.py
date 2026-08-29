from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import subprocess
import sys
import tomllib
import tokenize
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Sequence


SCHEMA_VERSION = 1
START_MARKER = "@test-value v1"
END_MARKER = "@end-test-value"


@dataclass(frozen=True)
class AdapterProfile:
    language: str
    extensions: frozenset[str]
    adapter: str
    coverage: str


PYTHON_PROFILE = AdapterProfile(
    language="python",
    extensions=frozenset({".py"}),
    adapter="python-source-v1",
    coverage="python-source-declarations-v1",
)
TYPESCRIPT_PROFILE = AdapterProfile(
    language="typescript",
    extensions=frozenset({".ts", ".tsx"}),
    adapter="typescript-source-v1",
    coverage="typescript-source-declarations-v1",
)
CSHARP_PROFILE = AdapterProfile(
    language="csharp",
    extensions=frozenset({".cs"}),
    adapter="csharp-source-v1",
    coverage="csharp-source-declarations-v1",
)
ADAPTER_PROFILES = (PYTHON_PROFILE, TYPESCRIPT_PROFILE, CSHARP_PROFILE)

KINDS = {
    "contract",
    "invariant",
    "regression",
    "security",
    "reference",
    "compatibility",
}
LIFECYCLES = {"permanent", "characterization", "ephemeral"}
ORACLE_TYPES = {
    "contract",
    "schema",
    "adr",
    "issue",
    "incident",
    "reference-model",
    "characterization",
}
REQUIRED_FIELDS = {"kind", "claim", "oracle", "failure_mode", "scope", "lifecycle"}
OPTIONAL_FIELDS = {"distinction", "expires_on", "review_when"}
ALLOWED_FIELDS = REQUIRED_FIELDS | OPTIONAL_FIELDS


@dataclass(frozen=True)
class CommentBlock:
    start_line: int
    end_line: int | None
    indent: str
    payload: tuple[str, ...]


@dataclass(frozen=True)
class Declaration:
    symbol: str
    start_line: int
    end_line: int
    indent: str


@dataclass(frozen=True)
class SourceAnalysis:
    declarations: tuple[Declaration, ...]
    comments: dict[int, tuple[str, str]]
    diagnostics: tuple[dict[str, Any], ...]


class AdapterError(RuntimeError):
    pass


def diagnostic(
    code: str,
    path: str,
    line: int,
    message: str,
    *,
    selection_start_line: int | None = None,
    selection_end_line: int | None = None,
) -> dict[str, Any]:
    result = {"code": code, "path": path, "line": line, "message": message}
    if selection_start_line is not None:
        result["_selection_start_line"] = selection_start_line
    if selection_end_line is not None:
        result["_selection_end_line"] = selection_end_line
    return result


def public_diagnostic(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item[key]
        for key in ("code", "path", "line", "message")
    }


def sha256_text(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def render_result(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def normalized_lines(source: str) -> tuple[str, list[str]]:
    normalized = source.replace("\r\n", "\n").replace("\r", "\n")
    return normalized, normalized.splitlines(keepends=True)


def python_comment_lines(source: str) -> dict[int, tuple[str, str]]:
    comments: dict[int, tuple[str, str]] = {}
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.COMMENT:
            continue
        line_number, column = token.start
        indent = token.line[:column]
        if indent.strip():
            continue
        value = token.string[1:]
        if value.startswith(" "):
            value = value[1:]
        comments[line_number] = (indent, value)
    return comments


def comment_content(
    comments: dict[int, tuple[str, str]], line_number: int, indent: str
) -> str | None:
    comment = comments.get(line_number)
    if comment is None or comment[0] != indent:
        return None
    return comment[1]


def scan_comment_blocks(
    comments: dict[int, tuple[str, str]], lines: Sequence[str]
) -> list[CommentBlock]:
    blocks: list[CommentBlock] = []
    index = 1
    while index <= len(lines):
        comment = comments.get(index)
        if comment is None or comment[1] != START_MARKER:
            index += 1
            continue
        indent = comment[0]
        payload: list[str] = []
        cursor = index + 1
        end_line: int | None = None
        while cursor <= len(lines):
            value = comment_content(comments, cursor, indent)
            if value is None:
                break
            if value == END_MARKER:
                end_line = cursor
                cursor += 1
                break
            payload.append(value)
            cursor += 1
        blocks.append(
            CommentBlock(
                start_line=index,
                end_line=end_line,
                indent=indent,
                payload=tuple(payload),
            )
        )
        index = max(cursor, index + 1)
    return blocks


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_metadata(value: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["metadata root must be a TOML table"]

    keys = set(value)
    missing = sorted(REQUIRED_FIELDS - keys)
    unknown = sorted(keys - ALLOWED_FIELDS)
    if missing:
        errors.append(f"missing fields: {', '.join(missing)}")
    if unknown:
        errors.append(f"unknown fields: {', '.join(unknown)}")

    kind = value.get("kind")
    if kind is not None and (not isinstance(kind, str) or kind not in KINDS):
        errors.append("kind is not supported")

    lifecycle = value.get("lifecycle")
    if lifecycle is not None and (
        not isinstance(lifecycle, str) or lifecycle not in LIFECYCLES
    ):
        errors.append("lifecycle is not supported")

    for field in ("claim", "failure_mode", "scope"):
        if field in value and not nonempty_string(value[field]):
            errors.append(f"{field} must be a non-blank string")
    for field in ("distinction", "review_when"):
        if field in value and not nonempty_string(value[field]):
            errors.append(f"{field} must be a non-blank string")

    oracle = value.get("oracle")
    if oracle is not None:
        if not isinstance(oracle, dict):
            errors.append("oracle must be an inline table")
        else:
            oracle_keys = set(oracle)
            if oracle_keys != {"type", "ref"}:
                errors.append("oracle must contain only type and ref")
            oracle_type = oracle.get("type")
            if not isinstance(oracle_type, str) or oracle_type not in ORACLE_TYPES:
                errors.append("oracle.type is not supported")
            if not nonempty_string(oracle.get("ref")):
                errors.append("oracle.ref must be a non-blank string")

    expires_on = value.get("expires_on")
    review_when = value.get("review_when")
    if lifecycle == "characterization":
        if expires_on is None and review_when is None:
            errors.append("characterization requires expires_on or review_when")
    elif expires_on is not None or review_when is not None:
        errors.append("expires_on and review_when require characterization lifecycle")

    if expires_on is not None:
        if not isinstance(expires_on, str):
            errors.append("expires_on must be a YYYY-MM-DD string")
        else:
            try:
                parsed = date.fromisoformat(expires_on)
            except ValueError:
                errors.append("expires_on must be a valid YYYY-MM-DD date")
            else:
                if parsed.isoformat() != expires_on:
                    errors.append("expires_on must use canonical YYYY-MM-DD format")

    return errors


def has_inline_oracle_source(payload: Sequence[str], oracle: Any) -> bool:
    for end_line, line in enumerate(payload, start=1):
        if not any(
            suffix.lstrip().startswith("{")
            for suffix in line.split("=")[1:]
        ):
            continue
        try:
            before = tomllib.loads("\n".join(payload[: end_line - 1]))
            prefix = tomllib.loads("\n".join(payload[:end_line]))
        except tomllib.TOMLDecodeError:
            continue
        if "oracle" not in before and prefix.get("oracle") == oracle:
            return True
    return False


def parse_metadata(block: CommentBlock) -> tuple[dict[str, Any] | None, str | None, str | None]:
    try:
        value = tomllib.loads("\n".join(block.payload))
    except tomllib.TOMLDecodeError as error:
        return None, "TEST_VALUE_PARSE_ERROR", str(error)
    if isinstance(value, dict) and "oracle" in value and not has_inline_oracle_source(
        block.payload, value["oracle"]
    ):
        return (
            None,
            "TEST_VALUE_SCHEMA_ERROR",
            "oracle must use inline table syntax",
        )
    errors = validate_metadata(value)
    if errors:
        return None, "TEST_VALUE_SCHEMA_ERROR", "; ".join(errors)
    return value, None, None


def parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }


def declaration_info(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    parents: dict[ast.AST, ast.AST],
) -> tuple[bool, str]:
    names = [node.name]
    current: ast.AST = parents[node]
    while not isinstance(current, ast.Module):
        if not isinstance(current, ast.ClassDef):
            return False, node.name
        names.append(current.name)
        current = parents[current]
    names.reverse()
    return True, ".".join(names)


def declaration_start(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    if node.decorator_list:
        return min(decorator.lineno for decorator in node.decorator_list)
    return node.lineno


def declaration_indent(lines: Sequence[str], start_line: int) -> str:
    line = lines[start_line - 1]
    return line[: len(line) - len(line.lstrip(" \t"))]


def source_slice(lines: Sequence[str], start_line: int, end_line: int) -> str:
    return "".join(lines[start_line - 1 : end_line])


def analyze_python_source(
    source: str, lines: Sequence[str], relative_path: str
) -> SourceAnalysis:
    try:
        tree = ast.parse(source, filename=relative_path)
    except SyntaxError as error:
        return SourceAnalysis(
            declarations=(),
            comments={},
            diagnostics=(
                diagnostic(
                    "SOURCE_SYNTAX_ERROR",
                    relative_path,
                    error.lineno or 0,
                    error.msg,
                ),
            ),
        )

    declarations: list[Declaration] = []
    diagnostics: list[dict[str, Any]] = []
    parents = parent_map(tree)
    functions = sorted(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test")
        ),
        key=lambda item: (item.lineno, item.col_offset, item.name),
    )
    for node in functions:
        supported, symbol = declaration_info(node, parents)
        if not supported:
            start_line = declaration_start(node)
            diagnostics.append(
                diagnostic(
                    "TEST_DECLARATION_UNSUPPORTED",
                    relative_path,
                    node.lineno,
                    "test declaration is nested in an unsupported scope",
                    selection_start_line=start_line,
                    selection_end_line=node.end_lineno or node.lineno,
                )
            )
            continue
        start_line = declaration_start(node)
        declarations.append(
            Declaration(
                symbol=symbol,
                start_line=start_line,
                end_line=node.end_lineno or node.lineno,
                indent=declaration_indent(lines, start_line),
            )
        )
    return SourceAnalysis(
        declarations=tuple(declarations),
        comments=python_comment_lines(source),
        diagnostics=tuple(diagnostics),
    )


def parse_native_analysis(
    payload: str, relative_path: str
) -> SourceAnalysis:
    try:
        value = json.loads(payload)
        raw_declarations = value["declarations"]
        raw_comments = value["comments"]
        raw_diagnostics = value["diagnostics"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise AdapterError(f"adapter returned invalid JSON: {error}") from error

    try:
        declarations = tuple(
            Declaration(
                symbol=item["symbol"],
                start_line=item["start_line"],
                end_line=item["end_line"],
                indent=item["indent"],
            )
            for item in raw_declarations
        )
        comments = {
            item["line"]: (item["indent"], item["text"])
            for item in raw_comments
        }
        diagnostics = tuple(
            diagnostic(
                item["code"],
                relative_path,
                item["line"],
                item["message"],
                selection_start_line=item.get("start_line"),
                selection_end_line=item.get("end_line"),
            )
            for item in raw_diagnostics
        )
    except (KeyError, TypeError) as error:
        raise AdapterError(f"adapter returned an invalid analysis shape: {error}") from error
    return SourceAnalysis(declarations, comments, diagnostics)


def run_process(command: Sequence[str], source: str, adapter_name: str) -> str:
    try:
        completed = subprocess.run(
            command,
            input=source,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError as error:
        raise AdapterError(f"{adapter_name} adapter is unavailable: {error}") from error
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise AdapterError(
            f"{adapter_name} adapter failed with exit {completed.returncode}: {detail}"
        )
    return completed.stdout


def analyze_typescript_source(
    source: str, suffix: str, relative_path: str
) -> SourceAnalysis:
    adapter_dir = Path(__file__).parent / "adapters" / "typescript"
    if not (adapter_dir / "node_modules" / "typescript" / "package.json").is_file():
        raise AdapterError(
            "TypeScript adapter dependency is missing; run "
            "npm ci --prefix <skill-dir>/scripts/adapters/typescript"
        )
    payload = run_process(
        ["node", str(adapter_dir / "extract.mjs"), suffix],
        source,
        "TypeScript",
    )
    return parse_native_analysis(payload, relative_path)


def csharp_helper_dll(adapter_dir: Path) -> Path:
    project = adapter_dir / "TestValue.CSharpExtractor.csproj"
    helper = adapter_dir / "bin" / "Release" / "net8.0" / "TestValue.CSharpExtractor.dll"
    source_inputs = (
        project,
        adapter_dir / "Program.cs",
        adapter_dir / "DiagnosticProjection.cs",
        adapter_dir / "packages.lock.json",
    )
    rebuild = not helper.is_file() or any(
        item.stat().st_mtime_ns > helper.stat().st_mtime_ns for item in source_inputs
    )
    if rebuild:
        run_process(
            [
                "dotnet",
                "build",
                str(project),
                "--configuration",
                "Release",
                "--nologo",
                "--verbosity",
                "quiet",
            ],
            "",
            "C# build",
        )
    if not helper.is_file():
        raise AdapterError("C# adapter build did not produce the expected helper")
    return helper


def analyze_csharp_source(source: str, relative_path: str) -> SourceAnalysis:
    adapter_dir = Path(__file__).parent / "adapters" / "csharp"
    helper = csharp_helper_dll(adapter_dir)
    payload = run_process(["dotnet", str(helper)], source, "C#")
    return parse_native_analysis(payload, relative_path)


def bind_analysis(
    source: str,
    lines: Sequence[str],
    relative_path: str,
    analysis: SourceAnalysis,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if any(item["code"] == "SOURCE_SYNTAX_ERROR" for item in analysis.diagnostics):
        return [], list(analysis.diagnostics)

    blocks = scan_comment_blocks(analysis.comments, lines)
    complete_blocks = [block for block in blocks if block.end_line is not None]
    consumed: set[CommentBlock] = set()
    duplicate_blocks: set[CommentBlock] = set()
    records: list[dict[str, Any]] = []
    diagnostics = list(analysis.diagnostics)

    declaration_counts: dict[tuple[int, str], int] = {}
    for declaration in analysis.declarations:
        key = (declaration.start_line, declaration.indent)
        declaration_counts[key] = declaration_counts.get(key, 0) + 1
    ambiguous_declarations = {
        key for key, count in declaration_counts.items() if count > 1
    }
    for start_line, _indent in sorted(ambiguous_declarations):
        diagnostics.append(
            diagnostic(
                "TEST_DECLARATION_UNSUPPORTED",
                relative_path,
                start_line,
                "multiple test declarations on one line cannot be bound unambiguously",
            )
        )

    for declaration in sorted(
        analysis.declarations,
        key=lambda item: (item.start_line, item.symbol),
    ):
        start_line = declaration.start_line
        indent = declaration.indent
        if (start_line, indent) in ambiguous_declarations:
            continue
        immediate = [
            block
            for block in complete_blocks
            if block not in consumed
            and block.end_line == start_line - 1
            and block.indent == indent
        ]
        chain: list[CommentBlock] = immediate[:]
        if chain:
            cursor = chain[0]
            while True:
                previous = [
                    block
                    for block in complete_blocks
                    if block not in consumed
                    and block.end_line == cursor.start_line - 1
                    and block.indent == indent
                ]
                if not previous:
                    break
                cursor = previous[0]
                chain.insert(0, cursor)

        metadata: dict[str, Any] | None = None
        metadata_hash: str | None = None
        metadata_start: int | None = None
        metadata_end: int | None = None
        if len(chain) > 1:
            consumed.update(chain)
            duplicate_blocks.update(chain)
            diagnostics.append(
                diagnostic(
                    "TEST_VALUE_DUPLICATE",
                    relative_path,
                    chain[0].start_line,
                    "multiple adjacent test-value blocks target one declaration",
                )
            )
        elif len(chain) == 1:
            block = chain[0]
            consumed.add(block)
            metadata_start = block.start_line
            metadata_end = block.end_line
            metadata, error_code, error_message = parse_metadata(block)
            if error_code:
                diagnostics.append(
                    diagnostic(
                        error_code,
                        relative_path,
                        block.start_line,
                        error_message or "invalid test-value metadata",
                    )
                )
            else:
                metadata_hash = sha256_text(canonical_json(metadata))
        else:
            diagnostics.append(
                diagnostic(
                    "TEST_VALUE_MISSING",
                    relative_path,
                    start_line,
                    "test declaration has no adjacent test-value block",
                )
            )

        end_line = declaration.end_line
        extracted_source = source_slice(lines, start_line, end_line)
        records.append(
            {
                "source": {
                    "path": relative_path,
                    "symbol": declaration.symbol,
                    "metadata_start_line": metadata_start,
                    "metadata_end_line": metadata_end,
                    "declaration_start_line": start_line,
                    "declaration_end_line": end_line,
                },
                "metadata": metadata,
                "source_text": extracted_source,
                "source_hash": sha256_text(extracted_source),
                "metadata_hash": metadata_hash,
            }
        )

    for block in blocks:
        if block not in consumed and block not in duplicate_blocks:
            diagnostics.append(
                diagnostic(
                    "TEST_VALUE_UNBOUND",
                    relative_path,
                    block.start_line,
                    "test-value block is not adjacent to a supported declaration",
                )
            )

    return records, diagnostics


def extract_source(
    path: Path,
    relative_path: str,
    profile: AdapterProfile,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        raw = path.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError as error:
        return [], [
            diagnostic(
                "SOURCE_DECODE_ERROR",
                relative_path,
                0,
                f"source is not valid UTF-8: {error}",
            )
        ]

    return extract_source_text(raw, relative_path, profile, path.suffix.lower())


def extract_source_text(
    raw: str, relative_path: str, profile: AdapterProfile, suffix: str | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source, lines = normalized_lines(raw)
    suffix = suffix or Path(relative_path).suffix.lower()
    if profile == PYTHON_PROFILE:
        analysis = analyze_python_source(source, lines, relative_path)
    elif profile == TYPESCRIPT_PROFILE:
        analysis = analyze_typescript_source(source, suffix, relative_path)
    elif profile == CSHARP_PROFILE:
        analysis = analyze_csharp_source(source, relative_path)
    else:
        raise AdapterError(f"unsupported adapter profile: {profile.language}")
    return bind_analysis(source, lines, relative_path, analysis)


def extract_repository(
    repository_root: Path,
    source_paths: Sequence[str],
) -> tuple[dict[str, Any], int]:
    root = repository_root.resolve(strict=True)
    resolved_paths: dict[str, Path] = {}
    diagnostics: list[dict[str, Any]] = []

    supplied_paths = [Path(raw_path) for raw_path in source_paths]
    profiles = {
        profile
        for path in supplied_paths
        for profile in ADAPTER_PROFILES
        if path.suffix.lower() in profile.extensions
    }
    unsupported_extensions = sorted(
        {
            path.suffix.lower() or "<none>"
            for path in supplied_paths
            if not any(
                path.suffix.lower() in profile.extensions
                for profile in ADAPTER_PROFILES
            )
        }
    )
    if unsupported_extensions:
        raise ValueError(
            f"unsupported source extension: {', '.join(unsupported_extensions)}"
        )
    if len(profiles) > 1:
        raise ValueError("source paths must use one language per invocation")
    profile = next(iter(profiles), PYTHON_PROFILE)

    for supplied in supplied_paths:
        candidate = supplied if supplied.is_absolute() else root / supplied
        resolved = candidate.resolve(strict=False)
        if not resolved.is_relative_to(root):
            diagnostics.append(
                diagnostic(
                    "SOURCE_OUTSIDE_ROOT",
                    supplied.name or ".",
                    0,
                    "source path resolves outside repository root",
                )
            )
            continue
        relative = resolved.relative_to(root).as_posix()
        resolved_paths[relative] = resolved

    records: list[dict[str, Any]] = []
    for relative, path in sorted(resolved_paths.items()):
        source_records, source_diagnostics = extract_source(path, relative, profile)
        records.extend(source_records)
        diagnostics.extend(source_diagnostics)

    records.sort(
        key=lambda item: (
            item["source"]["path"],
            item["source"]["declaration_start_line"],
            item["source"]["symbol"],
        )
    )
    diagnostics.sort(key=lambda item: (item["path"], item["line"], item["code"]))
    result = {
        "schema_version": SCHEMA_VERSION,
        "adapter": profile.adapter,
        "coverage": profile.coverage,
        "repository_root": ".",
        "tests": records,
        "diagnostics": [public_diagnostic(item) for item in diagnostics],
    }
    return result, 1 if diagnostics else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Extract Python, TypeScript, or C# test declarations and adjacent "
            "test-value comments."
        )
    )
    parser.add_argument("--root", required=True, type=Path, help="Repository root")
    parser.add_argument("paths", nargs="*", help="Source paths from one supported language to extract")
    parser.add_argument("--changed-from", metavar="BASE", help="Git diff base revision")
    parser.add_argument("--language", choices=[p.language for p in ADAPTER_PROFILES])
    head = parser.add_mutually_exclusive_group()
    head.add_argument("--head", metavar="COMMIT")
    head.add_argument("--staged", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.changed_from is not None:
            if not args.language or args.paths:
                raise ValueError("Git mode requires --language and forbids positional paths")
            from git_diff_selection import select_git

            profile = next(
                profile
                for profile in ADAPTER_PROFILES
                if profile.language == args.language
            )
            mode = "staged" if args.staged else "head" if args.head else "working"
            result = select_git(
                args.root,
                args.changed_from,
                profile,
                extract_source_text,
                diagnostic,
                public_diagnostic,
                mode,
                args.head,
            )
            rendered = render_result(result)
            if hasattr(sys.stdout, "buffer"):
                sys.stdout.buffer.write(rendered.encode("utf-8"))
            else:
                sys.stdout.write(rendered)
            return 1 if result["diagnostics"] else 0
        if args.language or args.head or args.staged:
            raise ValueError("--language, --head, and --staged require --changed-from")
        if not args.paths:
            raise ValueError("source paths are required")
        result, exit_status = extract_repository(args.root, args.paths)
    except (AdapterError, OSError, ValueError) as error:
        print(f"extract_test_values: {error}", file=sys.stderr)
        return 2
    rendered = render_result(result)
    if hasattr(sys.stdout, "buffer"):
        sys.stdout.buffer.write(rendered.encode("utf-8"))
    else:
        sys.stdout.write(rendered)
    return exit_status


if __name__ == "__main__":
    raise SystemExit(main())
