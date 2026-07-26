# Plugin Schema Version 1

Use this reference when reviewing plugin YAML or deciding whether a repository needs a repo-local plugin.

## Feature Trace Plugin

This example matches the bundled `feature-trace` plugin. Keep the rules together when copying it into a repository so `module` resources still validate their source and test reachability.

```yaml
schemaVersion: 1
name: feature-trace
resourceKinds:
  - feature-root
  - design-doc
  - module
  - source
  - test
relations:
  - decomposes-to
  - realized-by
  - verified-by
rules:
  - when: feature-root
    requireAnyOutgoing:
      - decomposes-to
      - realized-by
    requireReachableKinds:
      - design-doc
      - module
      - source
      - test
  - when: module
    requireAnyOutgoing:
      - realized-by
      - verified-by
    requireReachableKinds:
      - source
      - test
traversal:
  startKinds:
    - feature-root
  relationOrder:
    - decomposes-to
    - realized-by
    - verified-by
```

## Fields

- `schemaVersion`: plugin schema version. Use `1`.
- `name`: stable plugin name for humans and diagnostics.
- `resourceKinds`: allowed sidecar `kind` values.
- `relations`: allowed link `rel` values.
- `rules`: optional validation rules for required outgoing links and reachable resource kinds.
- `traversal`: optional defaults for graph traversal, such as start kinds and relation order.

## Choosing A Plugin Strategy

| Strategy | Use When | Tradeoff |
| --- | --- | --- |
| Use bundled `feature-trace` | The repository can model work as feature roots, docs, modules, source, and tests | Fastest path; vocabulary is intentionally generic |
| Copy `feature-trace` into the repo | The repository wants the standard vocabulary but needs versioned local control | Slight maintenance cost; safer for long-lived teams |
| Create a custom plugin | The repository needs domain-specific kinds, relation names, or validation rules | More expressive; requires clear local documentation |

## When To Create A Custom Plugin

Create a custom plugin only when one of these is true:

- The standard resource kinds force misleading names, such as treating deployments, schemas, or policies as generic modules.
- The repository needs relation names with different semantics, such as `owned-by`, `migrates-to`, or `published-as`.
- Validation must enforce domain rules that `feature-trace` cannot express clearly.
- A team has stable shared vocabulary that should appear in diagnostics and reviews.

Avoid custom plugins for one-off naming preferences. Prefer repository-local rules or metadata when the standard graph still describes the work accurately.
