# Codex system prompt records

This directory keeps versioned records of the Codex built-in instruction text used by a WithMate session.

## Scope

The English snapshot contains only `session_meta.payload.base_instructions.text` from a Codex rollout. It does not contain user prompts, Character context, `AGENTS.md`, runtime permissions, MCP environment values, authentication, or session state.

The Japanese file is a translation reference. It is not the file used by Codex unless it is explicitly selected in configuration.

The WithMate file is the editable integration copy. Its initial content is the captured English baseline; Character-specific wording will be adjusted in a later change.

## Layout

| Path | Purpose |
| --- | --- |
| `snapshots/YYYY-MM-DD-<model>.en.md` | Immutable English capture for a date and model |
| `snapshots/YYYY-MM-DD-<model>.ja.md` | Japanese translation of the corresponding English capture |
| `.codex/model-instructions-withmate.md` | Editable WithMate instruction file |
| `scripts/capture-codex-system-prompt.ps1` | Extracts the built-in instruction text from a rollout |
| `docs/runbooks/system-prompt-maintenance.md` | Capture, review, translation, and configuration procedure |

## Initial record

The initial record was captured on 2026-09-16 from the `gpt-5.6-luna` session running Codex CLI 0.154.0. The captured text is 17,730 characters.

Use Git history to track changes between records. Do not overwrite an existing dated snapshot; create a new dated file when the source prompt changes.
