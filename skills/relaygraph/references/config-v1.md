# Root Config Schema Version 1

Use this reference when creating or reviewing `.relaygraph.yaml`.

## Minimal Config

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

This is enough to load one plugin, discover sidecars with the standard suffix, respect Git ignore rules, and keep generated graph output out of discovery.

## Expanded Config

```yaml
schemaVersion: 1
useGitIgnore: true
sidecarSuffix: ".relaygraph.yaml"
plugins:
  - "relaygraph/plugins/feature-trace.yaml"
exclude:
  - "._relaygraph/**"
  - "relaygraph/plugins/**"
  - "**/bin/**"
  - "**/obj/**"
  - "node_modules/**"
requireSidecar:
  - "docs/**"
  - "src/**"
  - "tests/**"
```

Use the expanded shape when the repository has stable source, docs, and test roots and validation should catch resources that are missing sidecars.

## Fields

- `schemaVersion`: config schema version. Use `1`.
- `plugins`: plugin YAML files that define allowed resource kinds, relations, validation rules, and traversal behavior.
- `exclude`: resource or sidecar paths RelayGraph must ignore. Include generated output, package caches, build output, plugin files, and CI-sensitive paths when needed.
- `requireSidecar`: path globs where discovered resources are expected to have sidecars. Use after bootstrap, when coverage policy is intentional.
- `useGitIgnore`: when `true`, Git-ignored files are skipped during discovery. Keep this enabled unless the repository deliberately graphs ignored files.
- `sidecarSuffix`: suffix used to find sidecar files. The common value is `.relaygraph.yaml`.

## Review Checklist

- Paths are repo-relative and do not contain absolute paths or parent traversal.
- Generated and tool-owned directories are excluded.
- Plugin paths exist and are not themselves treated as graph resources.
- `requireSidecar` does not cover build output, vendored dependencies, or generated files.
- The config is small enough that a new contributor can predict what `validate` will check.
