# Domain format port — working state

Last saved: 2026-10-15 00:35 UTC (21:35 GMT-3).

## Request
Port the fan-made Domain format (rulebook v1.4) to MASQPro as a master rule like Genesys, with a
deck-building part in the deck editor, for 2 players and 4 players. The engine may be changed;
card scripts must not be.

## Order of work
1. Two-player Domain (engine, client, Multirole, list data) — in progress.
2. Four-player free-for-all (N-seat engine with a Lua "perspective" layer, Multirole 4-seat rooms,
   client focus view) — not started; analysis in `research/4p/`.

## Documents in this folder
- `domain_rules.md` — digest of the rulebook.
- `domain_spec.md` — implementation spec: v1 followed by "v2 AMENDMENTS" (v2 wins on conflict).
- `research/2p/`, `research/4p/` — code analyses with file:line references.
- `critique/` — adversarial review of spec v1 (the source of the v2 amendments).
- `wip/` — snapshots of unfinished work (see below).

## Status per component (two-player)

| Component | Where | State |
|---|---|---|
| Shared constants | MASQPro local branches `domain-core` and `domain-client`, commit `7fbe9527` | Done |
| Domain list data | LFListsZedja local branch `claude/clever-cori-fy407t`, commits `6c068a4`, `9b9b648`, `c5c6fb1`; client copy commit `bd305388` | Done. 9,379 `#@dm` lines, hash `0xBC3B2D7E`. Report: `wip/data-agent-report.md` |
| Engine (ocgcore) | worktree `/home/user/wt/core`, branch `domain-core` | In progress, uncommitted. Snapshot: `wip/engine-wip.patch` (includes `tests/domain/`) |
| Client deck building / host / network / replays | worktree `/home/user/wt/client`, branch `domain-client` | In progress, uncommitted. Snapshot: `wip/client-wip.patch` |
| Client duel UI (DMZ on the field) | same worktree | Not started |
| Multirole | `/home/user/multirole`, branch `claude/clever-cori-fy407t` | Not started |
| Merge, full build, review, PRs | — | Not started |

## How to resume
- If the worktrees still exist: continue the uncommitted work there (agents must be told to read the
  existing diff first and continue, not restart).
- If the container was reclaimed: recreate the branches from `origin/claude/clever-cori-fy407t`
  (this commit) and apply the patches in `wip/`:
  `git am wip/shared-constants.patch`, then `git apply wip/engine-wip.patch` (engine branch) or
  `git am wip/client-domain-list.patch && git apply wip/client-wip.patch` (client branch);
  LFListsZedja: `git am wip/lflistszedja-domain.patch` on top of `7304110`.
- Build notes: client via premake5 gmake2 + `make -Cbuild config=release_x64 ygopro` with the vcpkg
  cache bundle; engine tests via CardScripts `.claude/skills/edopro-card-scripting/tools`
  (`loadcheck.py setup` with `EDOPRO_CORE` pointing at the engine sources, then
  `tests/domain/domain_scenarios.py`); Multirole via meson.
- `wip/implement-workflow.js` is the orchestration script used for the implementation phase.

## Decisions already taken
- Deck Master Zone = card outside all zones (location 0, sequence 0xFF), let back in only by the
  rulebook's methods; proper summons by card effects through a "probe gate" on proper-summon
  predicates; LP cost paid as a rule cost; return prompt before each open game state.
- Domain card pool data shipped inside `Domain.lflist.conf` (`#@dm` lines), folded into the list hash.
- Rules as written for mentioned monsters' archetypes (Dark Magician Girl also gets "Chaos").
- Duel rule index 9 = Domain (Custom moves to 10).
- This `docs/domain/` folder is a working record; remove or trim it before the final merge if not wanted.
