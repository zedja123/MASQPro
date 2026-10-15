# Domain format port — working state

Last saved: 2026-10-15 12:00 UTC (09:00 GMT-3).

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
| Engine (ocgcore) | MASQPro PR #4 | Done: 42/42 engine scenarios, 150 non-Domain duels identical to the base core, 300 random Domain duels clean |
| Client deck building / host / network / replays | MASQPro PR #4 | Done: matches the reference on all list hashes and 600 random decks; not run on a display |
| Client duel UI (Deck Master Zone) | MASQPro PR #4 | Done: message-level test passes; not run on a display |
| Domain list data + generator + reference | LFListsZedja PR #3 (copy in MASQPro `lflists/`) | Done: hash 0xBC3B2D7E |
| Multirole | Multirole PR #3 | Done: test suite passes against the reference; not run end-to-end with hornet |
| CI | MASQPro PR #4 head 0da30e2 | Green on every platform |
| Adversarial review of the whole diff | — | In progress (rerun after a session limit) |
| Four-player | — | Not started; analysis in `research/4p/` |

Implementer reports: `wip/*.md` (engine, client, multirole, data).

## Decisions already taken
- Deck Master Zone = card outside all zones (location 0, sequence 0xFF), let back in only by the
  rulebook's methods; proper summons by card effects through a "probe gate" on proper-summon
  predicates; LP cost paid as a rule cost; return prompt before each open game state.
- Domain card pool data shipped inside `Domain.lflist.conf` (`#@dm` lines), folded into the list hash.
- Rules as written for mentioned monsters' archetypes (Dark Magician Girl also gets "Chaos").
- Duel rule index 9 = Domain (Custom moves to 10).
- This `docs/domain/` folder is a working record; remove or trim it before the final merge if not wanted.
