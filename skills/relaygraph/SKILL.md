---
name: relaygraph
description: Use RelayGraph in repositories with .relaygraph.yaml or *.relaygraph.yaml to inspect resource relationships, trace design/source/test impact, validate graph declarations, rebuild or query the cache, and create repository-specific graph rules for AI-assisted code navigation.
---

# RelayGraph

Use RelayGraph to understand and validate Git-backed resource graphs before and after code, documentation, or sidecar changes.

## Core Rules

- Run commands from the repository root that contains `.relaygraph.yaml`.
- Treat `.relaygraph.yaml`, `*.relaygraph.yaml`, and `relaygraph/plugins/*.yaml` as source of truth.
- Treat `._relaygraph/` as generated output. Do not edit it by hand.
- Use repo-relative paths in sidecars. Do not write absolute paths or paths outside the repository.
- Prefer `path:<repo-relative-path>` when tracing a file and `id:<resource-id>` when tracing a stable resource ID.
- Before creating or editing declarations, read repository-local instructions such as `AGENTS.md`, `CLAUDE.md`, and the root `.relaygraph.yaml`.

## Workflow

1. Detect whether the repository uses RelayGraph by checking for `.relaygraph.yaml`.
2. If the repository has no `.relaygraph.yaml`, read `references/bootstrap-repo.md` before creating initial graph files.
3. Read repository-local rules before creating sidecars, running `init`, or changing plugin vocabulary.
4. If root config, plugin vocabulary, or graph granularity is unclear, read the relevant reference before editing.
5. Trace the target file, feature root, or design document before editing.
6. Read the related resources returned by RelayGraph.
7. Make the requested change using existing repository conventions.
8. Validate the graph after changes.

## Command Selection

Use the installed binary when available:

```bash
relaygraph validate --json
relaygraph validate --strict
relaygraph trace path:src/main.rs --json
relaygraph trace id:docs.design.relaygraph
relaygraph link add id:docs.feature.example realized-by:id:src.example --path-hint --reason "implements the feature"
relaygraph link update id:docs.feature.example realized-by:id:src.old --new realized-by:id:src.example --path-hint --reason "uses the new implementation"
relaygraph link remove id:docs.feature.example realized-by:id:src.example
relaygraph link acknowledge id:docs.feature.example realized-by:id:src.example
relaygraph export
relaygraph sync --dry-run
relaygraph cache rebuild
relaygraph cache trace path:src/main.rs --json
relaygraph cache diagnostics
```

When working inside the RelayGraph source repository and the binary is not installed, use `cargo run --`:

```bash
cargo run -- validate --json
cargo run -- trace path:src/main.rs --json
cargo run -- link add id:docs.feature.example verified-by:id:tests.example --path-hint --reason "verifies the feature"
cargo run -- sync --dry-run
cargo run -- cache rebuild
```

For command details, read `references/cli.md`.

## Repository Rules

Repository-local rules override generic examples in this skill. Use them for include/exclude policy, sidecar placement, generated directories, CI-sensitive paths, allowed kinds and relations, ID naming, and validation commands.

When a repository needs new or updated local rules, read `references/repository-rules.md`.

For root config syntax and common config shapes, read `references/config-v1.md`.

For plugin YAML syntax and when to use a repo-local or custom plugin, read `references/plugin-v1.md`.

For initial graph granularity and repository pattern examples, read `references/sample-patterns.md`.

## Sidecars

Sidecars support schema versions 1–3; omitting `schemaVersion` means version 1. A baseline sidecar uses repo-relative locators:

```yaml
schemaVersion: 1
id: src.graph
kind: source
links:
  - rel: verified-by
    to: id:tests.cli
    pathHint: tests/cli.rs
```

Schema version 2 is written by `link acknowledge` when a relation review records endpoint fingerprints. Schema version 3 adds optional non-blank link reasons and a required reviewed-link fingerprint for acknowledged links. `link add --reason` and `link update --reason` upgrade only the edited sidecar to version 3; `--clear-reason` removes a reason without downgrading the sidecar. CLI-authored reasons are explicitly quoted YAML strings. Run `validate --strict` in CI when endpoint or reviewed-link changes must fail validation. `sync` does not acknowledge relations.

Use only resource kinds and relations allowed by the configured plugin. For the supported sidecar versions and schema examples, read `references/sidecar-v1.md`.

When editing existing sidecar links from the CLI, prefer `relaygraph link add|update|remove` instead of hand-editing YAML. Select the source resource with `id:<resource-id>`, use `rel:id:<target-id>` link arguments, use `--path-hint` when the sidecar should store the target path resolved from the target ID, and use `--reason <text>` when the dependency rationale belongs to the edge.

## Relation Review Workflow

Freshness checking applies only to relations that have already been acknowledged. After either endpoint or a version 3 link's reviewed `rel`, `to`, or `reason` changes, inspect both resources and decide whether the related resource must follow the change. Make any required source, documentation, or test updates first, then run `link acknowledge` only after confirming that the relation is consistent again. If no follow-up edit is needed, acknowledge only after making that review explicitly.

Editing the related resource does not clear the warning: the relation remains stale until it is reviewed and acknowledged. Use `validate --strict` in CI to prevent an unreviewed relation from being merged. For the diagnostic states and a complete example, read `references/cli.md`.

## Validation

After editing `.relaygraph.yaml`, sidecars, plugins, or linked resources, run:

```bash
relaygraph validate --json
```

If validation reports stale `pathHint` values, run `relaygraph sync --dry-run` first, then `relaygraph sync` when the planned sidecar updates are correct.

If the task changed graph structure, cache behavior, plugins, or many linked resources, also run:

```bash
relaygraph export
relaygraph cache rebuild
relaygraph cache diagnostics
```

Report validation output briefly. If validation cannot be run, state why and describe the remaining graph risk.
