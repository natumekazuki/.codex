---
name: relaygraph
description: Use RelayGraph in repositories that already contain .relaygraph.yaml or *.relaygraph.yaml to inspect resource relationships, trace design/source/test impact, validate declarations, and maintain graph rules. Bootstrap a repository only when RelayGraph adoption is explicitly requested.
---

# RelayGraph

Use the existing graph to determine which design documents, source files, and tests depend on a change. If there are no declarations, use ordinary repository tools. Read the [bootstrap guide](references/bootstrap-repo.md) only for explicit adoption; sidecars without a root config indicate incomplete setup, not authorization to initialize one.

## Follow the repository's graph

Start in the repository root containing `.relaygraph.yaml`. Before editing declarations, read the local instructions, root config and relevant sidecars. The root config, `*.relaygraph.yaml`, and `relaygraph/plugins/*.yaml` are sources of truth; `._relaygraph/` is generated. Use repository-relative locators within the repository. Local rules govern placement, exclusions, naming, vocabulary, granularity, and CI-sensitive paths.

Before editing a linked resource, trace it and read the relevant endpoints. Use `path:` for a repository-relative file or `id:` for a stable resource ID. After changing declarations, plugins, or linked resources, validate the graph:

```bash
relaygraph trace path:src/main.rs --json
relaygraph validate --json
```

Use the installed CLI or, in the RelayGraph source repository without an installed binary, `cargo run -- <command>`. See the [CLI reference](references/cli.md) for exact commands. A read-only investigation does not require new declarations or a cache.

## Change or review declarations

Prefer `link add|update|remove` for outgoing links on existing sidecars, using a source ID and a `rel:id:<target-id>` link. Resolve stored path hints from the target; include a reason when the dependency rationale belongs to the edge. For stale hints, inspect `sync --dry-run` before applying the intended updates. Sync does not acknowledge reviewed relations.

Freshness checks apply to acknowledged relations. When an endpoint or the reviewed meaning of a link changes, inspect both endpoints and the relation. Update any affected resource first, then `link acknowledge` only when the relationship is correct. An edit alone is not acknowledgement. Use `validate --strict` in CI where stale reviewed relations must fail. For changes to graph structure, plugins, cache behavior, or many linked resources, also run `export`, `cache rebuild`, and `cache diagnostics`. Report validation failures or unverified dependencies that affect the result.

Consult the reference for the declaration being changed:

- [Root config](references/config-v1.md) defines discovery; [plugins](references/plugin-v1.md) define kinds and relations.
- [Sidecar schemas](references/sidecar-v1.md) cover versions 1–3, reasons, and reviewed-link fingerprints. Do not hand-edit generated output to resolve a declaration issue.
- [Repository rules](references/repository-rules.md) guide local rule changes; [sample patterns](references/sample-patterns.md) illustrate granularity without prescribing it.
