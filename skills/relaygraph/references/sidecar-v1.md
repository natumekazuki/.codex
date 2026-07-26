# Sidecar Schema Versions 1–3

Use sidecars to give repository resources stable IDs, kinds, metadata, and outgoing links.

RelayGraph supports sidecar schema versions 1, 2, and 3. When `schemaVersion` is omitted, the sidecar is interpreted as version 1. Use version 1 for baseline declarations, version 2 for endpoint-based relation acknowledgement, and version 3 for link reasons and reviewed-link fingerprints.

## Shape

```yaml
schemaVersion: 1
id: docs.feature.example
kind: feature-root
metadata:
  owner: example
links:
  - rel: realized-by
    to: id:src.example
    pathHint: src/example.rs
    order: 10
  - rel: verified-by
    to: id:tests.example
    pathHint: tests/example.rs
    order: 20
```

## Fields

- `schemaVersion`: optional supported version (`1`, `2`, or `3`); omission means version 1.
- `id`: stable resource ID. Keep it unique in the repository.
- `kind`: resource kind allowed by the configured plugin.
- `metadata`: optional object for repository-specific data.
- `links`: optional ordered outgoing links.
- `pathHint`: optional derived repo-relative target path for an `id:` link.

## Locators

Sidecar versions 1–3 use the same locator forms:

- `id:<resource-id>`
- `path:<repo-relative-path>`

Prefer `id:` for link targets when the target has a stable sidecar ID. `path:` remains supported in the schema for compatibility and for targets without a useful ID, but CLI link editing commands intentionally accept only ID-based source and target locators.

Do not use absolute paths, parent traversal, or paths outside the repository.

## Path Hints

`to` is the canonical link target. For id-first links, `pathHint` is only a readability hint.

```yaml
links:
  - rel: realized-by
    to: id:src.example
    pathHint: src/example.rs
```

`validate` reports stale or invalid `pathHint` values without writing files. Use `relaygraph link add ... --path-hint` or `relaygraph link update ... --path-hint` to write a hint resolved from a target ID while editing a link. Use `relaygraph sync --dry-run` to preview bulk updates and `relaygraph sync` to refresh existing hints from resolved IDs. `sync` does not add missing hints or migrate all links.

## Link Reasons in Schema Version 3

Schema version 3 adds an optional non-blank `reason` to individual links:

```yaml
schemaVersion: 3
id: docs.example
kind: design-doc
links:
  - rel: realized-by
    to: id:src.example
    pathHint: src/example.rs
    reason: Implements the documented behavior
```

Use `relaygraph link add ... --reason <text>` or `relaygraph link update ... --reason <text>` to set the reason. The CLI always writes an explicitly quoted YAML string and replaces an existing block scalar as one field. Use `--clear-reason` to remove it. Changing or removing a reason clears relation acknowledgement because the reviewed edge meaning changed.

Acknowledged version 3 links include `linkRevision`, a fingerprint of `rel`, `to`, and `reason`. This makes direct sidecar edits stale even when neither endpoint file changed. Version 2 acknowledgements remain endpoint-only.

## Bundled Feature Trace Vocabulary

The bundled `feature-trace` plugin defines common resource kinds:

- `feature-root`
- `design-doc`
- `module`
- `source`
- `test`

It also defines common relations:

- `decomposes-to`
- `realized-by`
- `verified-by`

Always check the repository's configured plugin before assuming this vocabulary applies.
