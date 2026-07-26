# Bootstrap A Repository

Use this reference when a repository does not yet have `.relaygraph.yaml`.

## Flow

1. Detect the repository root and confirm it is Git-backed.
2. Read local instructions such as `AGENTS.md`, `CLAUDE.md`, README files, and design docs.
3. Create a minimal `.relaygraph.yaml` with the plugin, sidecar suffix, generated-output exclude, and any obvious generated directories.
4. Add `._relaygraph/` to `.gitignore` unless the repository intentionally commits generated graph output.
5. Add a small complete sidecar set for durable resources that already exist, such as a feature README, design doc, source module, source file, and focused test.
6. Run `relaygraph validate --json`.
7. Run at least one `relaygraph trace ... --json` from the new root or module and confirm the expected connection is visible.

## Minimal Root Config

```yaml
schemaVersion: 1
useGitIgnore: true
sidecarSuffix: ".relaygraph.yaml"
plugins:
  - "relaygraph/plugins/feature-trace.yaml"
exclude:
  - "._relaygraph/**"
  - "relaygraph/plugins/**"
```

Keep the first config small. Add `requireSidecar` only when the repository has a stable path policy and missing sidecars should fail validation.

## Minimal Sidecar Set

The bundled `feature-trace` plugin requires each `feature-root` to reach `design-doc`, `module`, `source`, and `test` resources. A bootstrap example should therefore be a complete set, not only a single feature sidecar.

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
# docs/design/example.md.relaygraph.yaml
schemaVersion: 1
id: docs.design.example
kind: design-doc
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

```yaml
# src/example/lib.rs.relaygraph.yaml
schemaVersion: 1
id: src.example.lib
kind: source
```

```yaml
# tests/example.rs.relaygraph.yaml
schemaVersion: 1
id: tests.example
kind: test
```

Use stable IDs for sidecar links and keep `pathHint` values repo-relative. Adapt path hints to files that actually exist in the repository. Do not point at generated files, package caches, build output, or files outside the repository.

## Generated Output

`._relaygraph/` is rebuildable output from commands such as `relaygraph export` and `relaygraph cache rebuild`. Do not edit it by hand. Prefer excluding it in `.relaygraph.yaml` and ignoring it in Git unless a repository has a documented reason to commit generated graph artifacts.

## Done Criteria

A bootstrap is usable when:

- `relaygraph validate --json` succeeds.
- At least one `trace` from a new sidecar shows the expected linked resource.
- Generated output is either ignored or explicitly documented as committed.
- The initial graph explains one real workflow instead of only demonstrating syntax.
