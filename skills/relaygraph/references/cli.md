# RelayGraph CLI

Use this reference when the task needs command details beyond the quick workflow in `SKILL.md`.

## Validate

Use after editing `.relaygraph.yaml`, sidecars, plugins, or related resources.

```bash
relaygraph validate --json
relaygraph validate --strict
```

Validation reports graph integrity issues such as missing sidecars, orphan sidecars, duplicate IDs, unresolved locators, unknown kinds, unknown relations, missing required relations, plugin load errors, and schema errors. Changed acknowledged relations are review warnings in the default mode; `--strict` makes those warnings fail validation for CI.

## Help

Use when checking the installed command surface or a subcommand's arguments.

```bash
relaygraph --help
relaygraph help generate
relaygraph help link add
relaygraph generate --help
```

The top-level help lists available subcommands. Subcommand help shows accepted arguments, flags, and repeatable options.

## Trace

Use before editing a file, feature root, or design document to discover related design docs, source files, and tests.

```bash
relaygraph trace path:src/main.rs
relaygraph trace id:docs.design.relaygraph
relaygraph trace path:src/main.rs --direction incoming
relaygraph trace path:src/main.rs --json
relaygraph trace path:src/main.rs --format paths
```

Use `path:` for repository-relative files. Use `id:` for stable resource IDs defined by sidecars.

Prefer `--json` when another AI agent or tool will consume the result. The JSON output includes the requested start locator, resolved start path, direction, ordered nodes, depth, and each node's incoming or outgoing relation context. Use `--format paths` only when a path-only list is required for compatibility.

## Export

Use when another tool needs deterministic graph JSON.

```bash
relaygraph export
```

The default graph JSON output is generated under `._relaygraph/generated/`. Treat it as rebuildable output.

## Sync

Use after validating sidecars when existing derived readability hints need to be refreshed.

```bash
relaygraph sync --dry-run
relaygraph sync
```

`sync` updates existing `pathHint` values from resolved link targets. It does not add missing hints, migrate all links, or update acknowledged revisions. `validate` stays read-only and reports stale hints as diagnostics; run `--dry-run` before writing sidecars.

## Link

Use when adding, removing, or updating outgoing links on an existing sidecar-backed resource. Select the source resource by stable ID and use target IDs for link arguments; do not pass sidecar file paths or `path:` link targets.

```bash
relaygraph link add id:docs.feature.example realized-by:id:src.example --path-hint --reason "implements the feature"
relaygraph link update id:docs.feature.example realized-by:id:src.old --new realized-by:id:src.example --path-hint --reason "uses the replacement"
relaygraph link update id:docs.feature.example realized-by:id:src.example --clear-reason
relaygraph link remove id:docs.feature.example realized-by:id:src.example
relaygraph link acknowledge id:docs.feature.example realized-by:id:src.example
```

`--path-hint` writes or refreshes `pathHint` from the resolved target ID. `--clear-path-hint` removes an existing hint. `--reason <text>` sets a non-blank, explicitly quoted YAML string and upgrades the edited sidecar to schema version 3; existing sibling acknowledgements keep their endpoint revisions and gain `linkRevision`. `--clear-reason` removes the field without downgrading the sidecar. Existing multiline reason fields are replaced or removed as a whole. Changing or removing a reason clears existing acknowledgement for that link. Use `--order <N>` or `--clear-order` when traversal order must be explicit. `link acknowledge` records SHA-256 fingerprints for both endpoint files; version 3 also records a fingerprint of `rel`, `to`, and `reason`. It upgrades version 1 to version 2 while preserving version 3.

`link acknowledge` may repair only version-specific `linkRevision` shape errors on the selected source sidecar: a missing version 3 value or an extra version 2 value. Invalid revisions and unrelated schema errors remain blocking.

### Acknowledged Relation Review Workflow

Freshness checking is opt-in per relation. Run `link acknowledge` once after reviewing a relation to establish its baseline. Relations without acknowledged revisions do not produce freshness diagnostics.

For example, suppose source A links to documentation B and a change to A may require B to follow it:

1. A changes after the relation has been acknowledged.
2. `relaygraph validate` reports `relation-review-required` with state `sourceChanged`. The default command succeeds with a warning; `relaygraph validate --strict` fails for CI.
3. Review A and B together. If B must follow the change, update B. If B remains correct, no edit is required.
4. When B is updated, validation reports `bothChanged` because both endpoints now differ from the last reviewed baseline. An edit alone never marks the relation as reviewed.
5. After confirming that A and B are consistent, acknowledge the relation and validate again:

```bash
relaygraph link acknowledge id:source.a documented-by:id:docs.b
relaygraph validate --strict
```

Use the relation configured by the repository in place of `documented-by`. If only the target changes, the diagnostic state is `targetChanged`; if both endpoints change, it is `bothChanged`. A direct version 3 edit to `rel`, `to`, or `reason` produces `linkChanged`, combined with endpoint states when applicable. Do not acknowledge merely to make CI pass: acknowledgement records that a person or trusted workflow reviewed the current endpoints and link meaning together. `sync` never performs this review or updates acknowledged revisions.

## Cache

Use cache commands for repeated AI-agent queries or external tooling.

```bash
relaygraph cache rebuild
relaygraph cache resources
relaygraph cache resources --json
relaygraph cache links --from path:src/main.rs
relaygraph cache trace path:src/main.rs
relaygraph cache trace path:src/main.rs --json
relaygraph cache diagnostics
```

Rebuild the cache before relying on cache-backed reads if declarations may have changed.

## Init

Use cautiously. Confirm repository rules first, because `init` may create sidecars.

```bash
relaygraph init --dry-run
relaygraph init
```

Prefer `--dry-run` before writing files. Do not create sidecars in generated, tool-owned, excluded, or CI-sensitive paths unless the repository explicitly allows them.

## Generate

Use when creating one sidecar for an existing Git-backed resource path.

```bash
relaygraph generate path:action.yml --dry-run
relaygraph generate path:action.yml --kind source --link verified-by:path:tests/cli.rs
```

The command writes only explicitly supplied `kind` and `--link rel:locator` values. It rejects excluded resources, excluded sidecar paths, generated paths, plugin/config paths, undiscovered resources, symlink boundaries, Git-ignored sidecars, existing sidecars, unknown vocabulary, and unresolved link targets.

## Skill Install

Use after installing the RelayGraph CLI when the user wants to install or refresh the bundled RelayGraph Skill.

```bash
relaygraph skill install --to .codex/skills
```

The command recreates `<skills-dir>/relaygraph`, so an older saved RelayGraph Skill is removed before the bundled Skill is written again. Do not pass a directory that should be preserved as the Skill itself; pass the parent skills directory.

## Source Repository Fallback

When working inside the RelayGraph source repository and no installed binary is available, use:

```bash
cargo run -- validate --json
cargo run -- validate --strict
cargo run -- help generate
cargo run -- sync --dry-run
cargo run -- trace path:src/main.rs
cargo run -- cache rebuild
```
