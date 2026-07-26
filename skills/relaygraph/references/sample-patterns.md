# Sample Graph Patterns

Use this reference when syntax is clear but the initial graph granularity is not.

## Expansion Phases

- Phase 1: connect one durable entry point to one implementation or verification target. Prove that `validate` and `trace` are useful.
- Phase 2: add the nearest design doc, module, source, and focused test for the same workflow.
- Phase 3: widen coverage across stable feature roots and modules. Add `requireSidecar` only after the expected coverage is clear.

## Representative Chain

```text
feature-root -> design-doc -> module -> source/test
```

Example sidecar links:

```yaml
# docs/features/example.md.relaygraph.yaml
schemaVersion: 1
id: docs.feature.example
kind: feature-root
links:
  - rel: decomposes-to
    to: id:docs.design.example
    pathHint: docs/design/example.md
  - rel: decomposes-to
    to: id:src.example.module
    pathHint: src/example/Cargo.toml
```

```yaml
# src/example/Cargo.toml.relaygraph.yaml
schemaVersion: 1
id: src.example.module
kind: module
links:
  - rel: realized-by
    to: id:src.example.lib
    pathHint: src/example/lib.rs
  - rel: verified-by
    to: id:tests.example
    pathHint: tests/example.rs
```

Add sidecars for the linked `design-doc`, `source`, and `test` resources too. The exact module path should match the repository's stable module boundary.

## Doc-Heavy Repository

Start with:

- one product or feature overview as `feature-root`
- one ADR, design note, or runbook as `design-doc`
- one script, generated artifact, or validation file as `source` or `test` if it exists

Reason: documentation repositories often have few stable modules. The useful first graph is usually the connection between a decision, its implementation artifact, and its verification command.

## .NET Solution Repository

Start with:

- solution or feature README as `feature-root`
- project file such as `src/App/App.csproj` as `module`
- primary service or entry point as `source`
- focused test project or test file as `test`

Reason: `.sln` and `.csproj` files are stable module boundaries. Avoid sidecars under `bin/` and `obj/`, and exclude those directories in root config.

## Library + App + Tests Repository

Start with:

- top-level library feature doc as `feature-root`
- package, crate, or module manifest as `module`
- public API file as `source`
- integration or CLI test as `test`

Reason: this pattern benefits from making the library/app boundary visible. Keep Phase 1 focused on one user-facing workflow before adding broad package coverage.

## Granularity Rules

- Prefer stable boundaries over every file.
- Add tests that prove the behavior, not only compile coverage.
- Do not graph generated outputs, dependency directories, or files whose names are controlled by external tools unless the repository explicitly supports that.
- When two resources always change together, start with the higher-level resource and split later if trace output becomes noisy.
