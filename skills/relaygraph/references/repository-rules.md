# Repository Rules

Use this reference when a repository needs local RelayGraph conventions beyond the generic skill.

## What To Capture

Add repository-specific rules for:

- paths where sidecars must not be created
- generated or tool-owned directories
- required sidecar coverage
- allowed resource kinds and relation names
- naming conventions for `id`
- validation commands expected in this repository
- CI-sensitive paths whose file names are interpreted by other tools

## Workflow

1. Read the root `.relaygraph.yaml`.
2. Read existing `AGENTS.md`, `CLAUDE.md`, or project docs.
3. Inspect existing `*.relaygraph.yaml` examples.
4. Identify generated, tool-owned, excluded, or CI-sensitive paths.
5. Encode durable discovery rules in `.relaygraph.yaml` when possible.
6. Document agent-facing rules in `AGENTS.md` or `CLAUDE.md`.
7. Run `relaygraph validate --json`.

## CI-Sensitive Paths

Be careful with directories where filename patterns are interpreted by external tools.

Example: GitHub Actions treats workflow directory contents as workflow definitions. Do not create RelayGraph sidecars there unless the repository explicitly supports that layout. Prefer excluding such paths or documenting a repository-local rule.

## Rule Placement

Use `.relaygraph.yaml` for machine-enforced discovery policy, such as `exclude` and `requireSidecar`.

Use `AGENTS.md`, `CLAUDE.md`, or project docs for agent-facing conventions, such as when to trace, when to create sidecars, and which validation command to run.

Do not duplicate long CLI documentation in repository rules. Link back to the RelayGraph skill or project docs when possible.
