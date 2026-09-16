# Codex system prompt maintenance

This runbook describes how to keep the Codex built-in instruction text, its Japanese translation, and the WithMate integration copy under reviewable version control.

## Sources and boundaries

The source is the first `session_meta` record in a Codex rollout JSONL. The text to capture is `payload.base_instructions.text`.

This is deliberately narrower than the complete session context. `AGENTS.md`, runtime developer instructions, permissions, MCP configuration, user prompts, and WithMate Character context remain separate inputs. Do not merge those values into a system-prompt snapshot or store session-bound environment values in Git.

`model_instructions_file` replaces the built-in instruction text; it is not an append-only Character overlay. Keep the full operational baseline in the WithMate file until a later change has reviewed any intentional differences. See the [official Codex configuration reference](https://developers.openai.com/codex/config-reference).

## Capture a new snapshot

1. Start a new Codex session after a Codex or model update. Record the active model and CLI version from the session metadata.
2. Locate the rollout JSONL. The following command prints the newest candidate without opening its contents:

   ```powershell
   $codexRoot = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
   Get-ChildItem -LiteralPath (Join-Path $codexRoot 'sessions') -Recurse -Filter 'rollout-*.jsonl' -File |
       Sort-Object LastWriteTime -Descending |
       Select-Object -First 1 -ExpandProperty FullName
   ```

3. Capture into a new dated file. Use `-Force` only when intentionally regenerating the same working file.

   ```powershell
   pwsh ./scripts/capture-codex-system-prompt.ps1 `
       -RolloutPath 'C:\path\to\rollout.jsonl' `
       -OutputPath 'docs/system-prompt/snapshots/YYYY-MM-DD-model.en.md'
   ```

4. Check the reported character count. The script fails if the rollout does not start with `session_meta` or does not contain `base_instructions.text`.
5. Do not edit the English snapshot after capture. If the source changes, create a new dated snapshot.

## Review for improvement

Perform this review at least monthly and after a Codex CLI, model, or WithMate integration update.

1. Compare the new English snapshot with the previous record.

   ```powershell
   git diff --no-index `
       docs/system-prompt/snapshots/previous.en.md `
       docs/system-prompt/snapshots/current.en.md
   ```

2. Check additions, removals, and reordered guidance in these areas:

   - response style and user-facing progress updates;
   - file editing, destructive actions, and approval boundaries;
   - tool, skill, browser, and app handling;
   - delegation, persistence, and context-compaction behavior;
   - reliability requirements for reporting failures and unconfirmed facts.

3. Decide whether a change is an upstream baseline change or an intentional WithMate customization. Keep those decisions separate in Git history.
4. Update the Japanese translation so its headings and normative requirements correspond to the new English snapshot. Preserve code, key names, paths, commands, and other machine-readable text exactly.
5. Review the WithMate file independently. It may intentionally diverge later, but every divergence should have a concrete user-facing or operational reason.
6. Record the new snapshot in `docs/system-prompt/README.md` if the model or capture convention changes, then commit the complete documentation update together.

## Prepare the WithMate file

The initial integration file is `.codex/model-instructions-withmate.md`. It currently mirrors the captured English baseline and is intentionally not Character-tuned yet.

When the WithMate wording is adjusted later:

1. Start from the current English snapshot.
2. Keep task execution, file safety, reporting, and tool-use requirements intact.
3. Keep response-style changes limited to user-visible natural-language responses. Do not put Character wording into code, configuration examples, tests, diffs, commit messages, or artifact metadata.
4. Compare the WithMate file against the snapshot and review the diff before applying it.
5. Start a new Codex session after configuration changes; do not treat an existing session as proof that the new file loaded.

## Apply through `config.toml`

Apply this only after the WithMate file has been reviewed. The real user configuration is local and must not be committed with credentials or machine-specific values.

### Project-scoped configuration

For a trusted repository, create or edit the repository-local `.codex/config.toml`:

```toml
model_instructions_file = "model-instructions-withmate.md"
```

Place that file next to `.codex/config.toml`. Relative paths in a project config resolve from the containing `.codex/` directory. Project-scoped config is loaded only when the project is trusted. See the [official advanced configuration guide](https://developers.openai.com/codex/config-advanced).

### User-scoped configuration

To apply the same file across sessions, add the top-level key to the local `~/.codex/config.toml` (on Windows, the active `CODEX_HOME` is normally under the user profile). Use an absolute path to the checked-out WithMate file when the file is outside the user config directory:

```toml
model_instructions_file = "C:\\path\\to\\repository\\.codex\\model-instructions-withmate.md"
```

This changes the built-in instruction source for every session that reads that user config, so review the scope before enabling it globally.

### Activation and verification

1. Preserve a copy of the current local `config.toml` before editing it.
2. Add only the `model_instructions_file` key; do not copy authentication, MCP runtime values, or unrelated settings into the repository.
3. Start a new session in the intended trusted repository.
4. Inspect the new rollout's `session_meta.payload.base_instructions.text` and compare its contents with the configured file.
5. Confirm that the session still receives the expected `AGENTS.md`, permissions, and WithMate MCP context as separate layers.
6. If the new session does not load the file, remove the override, keep the captured evidence, and investigate trust, path resolution, profile selection, and session restart before retrying.

## Git review checklist

Before committing a maintenance update, confirm:

- a new dated English snapshot exists;
- the source model and CLI version are recorded;
- the Japanese translation matches the English structure;
- the WithMate file's differences are intentional and visible in the diff;
- no rollout history, authentication, runtime environment value, or private session data was copied into the repository;
- the real `config.toml` was not accidentally staged.
