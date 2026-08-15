# How to start Cline on PetroLab v0.15.7

Open the repository/workspace on branch `hotfix/v0157-ux-workflow` in VS Code with Cline enabled.

Cline automatically loads the rules from `.clinerules/`.

## Recommended first command

In Cline chat run:

`/v0157-ux-consolidation.md`

If the custom workflow is not shown immediately, reload the VS Code window and verify that `.clinerules/workflows/v0157-ux-consolidation.md` exists in the opened workspace.

## Alternative first prompt

Paste this exactly:

> Work autonomously on PetroLab v0.15.7 UX consolidation. Read all `.clinerules/*.md`, then read `docs/UX_AUDIT_V0157_30_PROBLEMS.md` completely. Follow `.clinerules/workflows/v0157-ux-consolidation.md` in dependency order. Start with Preflight and Phase A. Do not add new user-facing modules. Do not add another wrapper/bridge/monkey-patch layer. Prefer consolidation into canonical components and state models. After every coherent block run focused tests, integration tests and real browser E2E for the affected workflow, then make a small local git commit. Continue autonomously while the next action is safe and clearly implied by the specification. Do not push or merge. Stop and ask only if a decision would risk user data, require a destructive migration, materially change scientific semantics, or contradict the written UX specification. Never claim an audit item fixed until the actual user scenario has been demonstrated.

## Permissions / autonomy

Safe to auto-approve during this refactor:
- read/search files;
- edit files in this repository;
- run Python/pytest/Streamlit/browser tests;
- create local test fixtures/temp files;
- run non-destructive git status/diff/log/add/commit commands.

Do NOT auto-approve:
- `git push`, merge/rebase onto `main`, force operations;
- deleting the PetroLab user data directory/database;
- destructive database migrations;
- modifying files outside the repository;
- uploading user scientific data to third-party services.

## Context management

This refactor is intentionally larger than one chat context.
- Stay within one task while a coherent phase is being debugged.
- When context becomes crowded during a phase, use `/smol` (or `/compact`) to compress history while keeping the same task.
- At a clean phase boundary, use `/newtask` so the next phase starts with a distilled handoff rather than a huge transcript.
- The repository files, tests, commits, audit and rules are the source of truth; do not rely on chat memory alone.

## Review checkpoint after each phase

Before moving to the next phase, Cline must report:
1. audit numbers closed;
2. architecture changed;
3. exact tests executed and their result;
4. browser scenario demonstrated;
5. remaining risks/gaps;
6. local commit(s) created.

If any test is red, the phase is not complete.
