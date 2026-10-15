# Domain format (2-player) — implementation spec v1

Rules: see domain_rules.md (same folder). Research reports: reports2p/*.md (same folder) — read the one for your area.
Card scripts (c*.lua) and the shared Lua procedure libraries are NOT changed. Everything is done in the engine
(ocgcore), the client (gframe), the server (Multirole) and the list data (LFListsZedja).

## 0. Shared constants (must be byte-identical everywhere they appear)

| Name | Value | Where |
|---|---|---|
| `DUEL_DOMAIN` | `0x2000000000ULL` (bit 37) | ocgcore/ocgapi_constants.h, gframe/ocgapi_constants.h (keep both files identical), Multirole if needed |
| `DUEL_MODE_DOMAIN` | `(DUEL_MODE_MR5 \| DUEL_DOMAIN)` | same |
| `DUEL_MODE_DOMAIN_FORB` | `0` | same |
| `LOCATION_DECK_MASTER` (API only) | `0x40000000` | ocgapi_constants.h. Only valid as `OCG_NewCardInfo.loc`. Never appears in messages. |
| `HINT_DMZ` | `204` | MSG_HINT subtype. player = DM owner; data = `code \| ((uint64_t)return_count << 32)`. "Player's DM is (now) in the DMZ". |
| `HINT_DMZ_REMOVE` | `205` | MSG_HINT subtype. player = DM owner; data = code. "Player's DM left the DMZ". |
| System strings | 7110 "Deck Master", 7111 "Domain", 7112 "Return your Deck Master to the Deck Master Zone?", 7113 "Summoning it from the Deck Master Zone costs %d LP.", 7114 "In Domain" (deck-editor filter), 7115 "Domain: your deck needs exactly 1 Deck Master, a Main or Extra Deck monster.", 7116 "Domain: \"%ls\" is outside your Deck Master's domain.", 7117 "Domain: only 1 copy of \"%ls\" is allowed.", 7118 "Domain: \"%ls\" cannot be your Deck Master.", 7119 "Deck Master Zone" | client; every use has a built-in English fallback (pattern of Genesys strings 7100-7104). |
| `DeckError` / Multirole `DeckOrCard` | `0x11` DOMAIN_DECK_MASTER (missing/invalid DM; code = DM code or 0), `0x12` DOMAIN_OUT_OF_DOMAIN (code), `0x13` DOMAIN_SINGLETON (code), `0x14` DOMAIN_FORBIDDEN_DM (code) | client network.h + duelclient.cpp texts; Multirole STOCMsgFactory.hpp |
| Deck trailer magic | `0x215A4D44` ("DMZ!" little-endian bytes 'D','M','Z','!') | CTOS_UPDATE_DECK trailer, see §3 |
| Replay flag | next free bit in replay.h REPLAY_* flags, named `REPLAY_DOMAIN` | client + Multirole replay writers/readers |

## 1. Engine (ocgcore) — the Deck Master Zone

### 1.1 State
- `player_info` gains `card* deck_master{nullptr}; uint32_t dm_returns{0}; bool dm_moved{false};`
- `card` gains `bool in_dmz{false};` (or equivalent) and a helper `uint32_t card::dmz_virtual_location() const`:
  `LOCATION_EXTRA` if the card is an Extra Deck monster type (Fusion/Synchro/Xyz/Link, and Ritual when DUEL_EXTRA_DECK_RITUAL),
  else `LOCATION_HAND`. Helper `uint32_t card::effective_location() const` = in_dmz ? virtual : current.location.
- A DM in the DMZ: `current.location == 0`, `current.controler == owner`, `current.sequence == 0`, position POS_FACEDOWN
  (like a card in hand/Extra Deck in core terms; the client shows it face-up), in no `player[].list_*`.

### 1.2 Loading
- `OCG_DuelNewCard` with `loc == LOCATION_DECK_MASTER` (duelist 0 only; only when the duel has DUEL_DOMAIN; at most one
  per team, a later one is ignored): create the card, place it at location 0 for `con == team`, set
  `player[team].deck_master`, `in_dmz = true`; register its effects so that §1.3 works.
- At duel start (Startup processing, before the opening hands are drawn) emit `HINT_DMZ` (return_count 0) for each player
  that has a DM.

### 1.3 Leaving the DMZ — only the rulebook's methods
Treat the DM "as if" at its virtual location ONLY in these paths (use `effective_location()` / virtual checks there):
1. Normal/Tribute Summon and Set: idle-command summonable and msetable lists include the DM (processor.cpp IdleCommand
   case 0); `card::is_can_be_summoned` (must take the HAND branch for a DMZ card, never the default TRUE branch),
   `card::is_setable_mzone`, `Processors::MonsterSet` step 0 location check, `summon.location` assignments (use the virtual
   location). Field effects of other cards that grant summon procedures must reach the DM: in `effect::is_target` (or
   wherever s/o ranges are matched against a card) use the virtual location for a DMZ card ONLY for the effect codes
   EFFECT_SUMMON_PROC, EFFECT_SET_PROC, EFFECT_LIMIT_SUMMON_PROC, EFFECT_LIMIT_SET_PROC, EFFECT_DECREASE_TRIBUTE,
   EFFECT_DECREASE_TRIBUTE_SET (Mausoleum of the Emperor). Not for costs (Chain Energy's EFFECT_SUMMON_COST etc. apply to
   cards "from the hand" and must NOT apply).
2. Its own summon procedures (EFFECT_SPSUMMON_PROC: Synchro/Xyz/Link/Contact Fusion procedures with range EXTRA, Jester
   Confit / Blue-Eyes Alternative / Red-Eyes Darkness Metal style procedures with range HAND): `effect::in_range(card*)`
   returns true for a DMZ card iff the virtual location is in the effect's range AND the effect is a FIELD
   EFFECT_SPSUMMON_PROC (also EFFECT_SPSUMMON_PROC_G is irrelevant on the DM itself), or an EFFECT_TYPE_ACTIVATE effect of
   a TYPE_PENDULUM Main Deck monster (Pendulum Spell activation, rule 4). `card::enable_field_effect` /
   `apply_field_effect` / `cancel_field_effect` must work for the DMZ card so those effects get registered and enabled
   (they currently bail out at location 0). Every other effect of the DM (ignition, quick, trigger incl. hand
   TRIGGER_O, continuous field effects) stays inactive in the DMZ (Bystial Magnamhut cannot summon itself).
   SINGLE effects without range (summon conditions, EFFECT_SPSUMMON_CONDITION, EFFECT_CANNOT_SPECIAL_SUMMON, revive
   limit, EFFECT_UNSUMMONABLE_CARD) keep applying — they are conditions, required for Tyrant Neptune etc.
   Idle-command spsummonable list includes the DM through the normal aura_effect route once registered.
   `Processors::SpSummonRule` uses the virtual location for `summon.location`.
3. Proper summons by card effects (Fusion/Ritual/Synchro/Xyz/Link/Pendulum by effects, effects that make you Normal
   Summon/Set): the "probe gate" in `field::filter_matching_card` (backs GetMatchingGroup(Count), IsExistingMatchingCard,
   SelectMatchingCard, GetFirstMatchingCard): when the query's self side (p==0) location mask contains the DM's virtual
   location, the filter is non-nil, and the query is not a target query, evaluate the filter on the DM inside a probe frame
   (a stack, because filters nest, e.g. Rank-Up-Magic Quick Chaos). The DM is included only if the filter returns true AND,
   during that evaluation, one of these predicates was evaluated ON THE DM and returned true:
   `Card.IsCanBeSpecialSummoned` with summon type (masked with 0xff000000 after OR-ing SUMMON_TYPE_SPECIAL) in
   {RITUAL 0x45, FUSION 0x43, SYNCHRO 0x46, XYZ 0x49, LINK 0x4c, PENDULUM 0x4a}<<24; `IsSynchroSummonable`,
   `IsXyzSummonable`, `IsLinkSummonable`, `IsProcedureSummonable`, `IsSpecialSummonable`; `IsSummonable`, `IsMSetable`.
   Frames are popped on every exit path (RAII; Lua errors included). `filter_field_card` (GetFieldGroup/Count, plain
   counts) never includes the DM, except in 3a.
   3a. Pendulum Summon (EFFECT_SPSUMMON_PROC_G of a Pendulum Scale; proc_pendulum.lua gathers with
   Duel.GetFieldGroup(tp,LOCATION_HAND|LOCATION_EXTRA,0) and filters with IsLocation(LOCATION_HAND) and
   IsCanBeSpecialSummoned(e,SUMMON_TYPE_PENDULUM,...)): while the core is running the condition/target/operation of an
   EFFECT_SPSUMMON_PROC_G effect, `filter_field_card` also includes the player's Main-Deck DM for LOCATION_HAND on the
   self side. Extra Deck DMs are never Pendulum Summoned from the DMZ.
4. `Card.IsLocation` / `Card.GetLocation` (libcard.cpp) report the virtual location for a DM in the DMZ, so library
   branches (`IsLocation(LOCATION_EXTRA) and GetLocationCountFromEx or GetMZoneCount`, Pendulum.Filter, "cannot Special
   Summon from the Extra Deck" player locks) behave as for a card in hand/Extra Deck.
5. Zones: `field::get_useable_count`, `get_spsummonable_count`, the Extra Monster Zone splits in SpSummonStep /
   SpSummonRule group, `get_rule_zone_fromex`: use `effective_location()` so an Extra Deck DM follows the Extra Deck
   placement rules (Link: EMZ or a zone a Link arrow points to; others: MMZ or EMZ).
6. Revive limit (card.cpp is_can_be_special_summoned, operations.cpp SpSummonStep masks): use the virtual location.
7. Pendulum Spell activation: AddChain step 1 places a card whose effective location is HAND into the Pendulum Zone.
8. NOT allowed: S/T Set from the DMZ (is_setable_szone keeps requiring the real hand), any effect that is not a proper
   summon (filters with IsCanBeSpecialSummoned(e,0,...) never set the probe hit), the DM's own activated effects,
   discarding, tributing, targeting, being affected (the DM is in no list, so all of this holds by default).

### 1.4 Cost
- `cost = 500 * dm_returns`. A DMZ path is legal only if `player.lp >= cost` (same convention as check_lp_cost): apply this
  in every predicate/list above for a DMZ card.
- Paid at the moment the DM is moved out of location 0 into the duel (central place: where a card leaves location 0 in
  field::move_card/add_card, or in MoveToField before the move), as a rule cost: subtract directly, emit
  `MSG_PAY_LPCOST` (if cost > 0); no EFFECT_LPCOST_CHANGE, no replacement, no event (Spell Economics must not reduce it).
- At the same moment: `in_dmz = false`, emit `HINT_DMZ_REMOVE` BEFORE the MSG_MOVE that brings the card in, and fix
  `previous.*` (location = virtual location, controler = owner) since remove_card is skipped for location 0.
- If the cost brings LP to 0 the player loses through the normal LP check.

### 1.5 Returning to the DMZ
- Tracking: whenever the DM moves (field::move_card/add_card/remove_card paths), set `dm_moved = true` if the move changes
  zone TYPE and is not a move within/onto the field: i.e. set it when the new location is not in
  (LOCATION_ONFIELD|LOCATION_OVERLAY), or the old location was on the field and the new is not. Column moves, MZONE<->SZONE,
  attaching as material, control changes, swaps: do not set it. Leaving the DMZ itself does not set it.
- New processor `Processors::DomainReturn`, run at the start of IdleCommand case 0, BattleCommand case 0 and PhaseEvent
  case 0 (with a guard so it runs once per entry, not once per priority pass) when DUEL_DOMAIN and any player has
  `dm_moved`: for the turn player, then the opponent: if `dm_moved` and the DM is not in the DMZ and its current location
  is not on the field / overlay: `SelectEffectYesNo(owner, 7112, dm)` (desc = system string 7112, code 0 → sysstring);
  on yes: move it to location 0 with `send_to(dm, nullptr, REASON_RULE, owner, PLAYER_NONE, 0, 0, POS_FACEDOWN)`-equivalent
  (raises EVENT_LEAVE_GRAVE / EVENT_MOVE with reason player = owner, so Exosister Elis can trigger), then set
  `in_dmz = true`, `++dm_returns`, re-register its DMZ effects (§1.3.2), emit `HINT_DMZ` with the new count.
  Clear `dm_moved` whatever the answer (also when no prompt was possible because it is on the field).
  After the step, queue a PointEvent so triggers caused by the return form a new chain, then restart the caller's step 0.
- The prompt cannot be responded to; returning does not start a chain.

### 1.6 Messages
- Idle command / select messages list a DMZ card as `(con = owner, location = 0, sequence = 0)`; the client maps it.
- Tests: write engine scenario tests with the CardScripts tooling (duelsim.py / scenario.py in
  /home/user/zedja123/cardscripts/.claude/skills/edopro-card-scripting/tools) — without committing to CardScripts; put the
  test files in the MASQPro worktree under `tests/domain/` (Python, runnable with the tools on PYTHONPATH).

## 2. Card pool data (LFListsZedja) — `Domain.lflist.conf`

Format (lines starting with `#@` are comments for older parsers, so old clients/servers still load the list):
```
#[Domain]
!Domain 1.4
$domain
#@forbid-dm <code>                       (Forbidden Deck Masters; none today)
#@dm <code> a=<hex> r=<hex> s=<hex16>,<hex16>... n=<code>,<code>...
<code> <limit> --<name>                  (ordinary banlist lines = Forbidden Cards; none today)
```
- `$domain` marks a Domain list (first one only), salt `DomainSalt = 0x444F4D41` XOR-ed into the list hash.
- Each `#@...` data line is folded into the hash: `hash ^= Rotl32(Fnv1a32(text), 1)` where `text` is the line content after
  the leading `#@`, with trailing spaces/tabs/CR removed, `Fnv1a32` = standard 32-bit FNV-1a (offset 0x811C9DC5, prime
  0x01000193) over the bytes, `Rotl32(x,1) = (x<<1)|(x>>31)`. Identical in client and Multirole.
- `#@dm` gives the COMPLETE domain of that Deck Master (canonical code = alias if the card is an alternate artwork or
  "always treated as" card, else its code): `a` attribute mask (own + mentioned), `r` race mask (own + mentioned), `s`
  archetype codes (own after base reduction + mentioned, reduced), `n` mentioned monster codes (canonical). Fields may be
  empty/omitted. A Deck Master with no `#@dm` line has the fallback domain: own attribute, own race, own setcodes as-is.
- Generator: a Python 3 tool committed in LFListsZedja (`tools/domain_gen.py`), based on the prototype
  /tmp/claude-0/domain-proto/domain.py, reading BabelCDB `cards.cdb` (+ other official cdbs if appropriate), the CardScripts
  `archetype_setcode_constants.lua`, and optionally the scripts' `s.listed_names` / `s.listed_series`. Deterministic output
  sorted by code. Rules as written in the rulebook: names quoted in the effect text (excluding the DM's own name), their
  monsters' archetypes, archetype names, Attributes and Types (token definitions included), "This card is not treated as"
  reminders removed, Normal monster flavor text ignored, base archetype used (base only if it is a known SET_ constant;
  split multi-bit sub-archetype codes), Spells/Traps never contribute archetypes through "mentioned monster".
- Add `Domain.lflist.conf` to `.github/local-files.txt` so the hourly mirror keeps it. Copy it to MASQPro `lflists/` too.

## 3. Deck format and transport (client + server)
- Deck gains one Deck Master slot (`Deck::master`, at most one card).
- .ydk: after the side section write `#master` then the DM code. Parser: `#master` switches to the DM section regardless of
  `separated`; the first code there is the DM. (Older parsers treat `#master` as a comment and read the DM into side.)
- ydke:// : a 4th base64 segment with the DM code (older importers ignore it).
- CTOS_UPDATE_DECK: unchanged layout `[u32 mainc][u32 sidec][codes]` plus, when the deck has a DM, a trailer
  `[u32 0x215A4D44][u32 dm_code]` after the side codes. Servers that do not know it ignore trailing bytes. Applies to the
  ready path and siding.
- Validation (client `DeckManager::CheckDeckContent`, server `Context::CheckDeck`), active when the selected banlist is a
  Domain list:
  1. DM present, is a monster (not Token, not Skill) → else 0x11.
  2. DM not in `#@forbid-dm` → else 0x14.
  3. Sizes: Main exactly 60, Extra 0-15, Side 0 (DM not counted) → existing size errors.
  4. Singleton by canonical code (alias if any, else code) across DM + Main + Extra → else 0x13 with the code.
  5. Ordinary banlist lines apply as usual (forbidden = 0).
  6. Every Main/Extra card in the domain → else 0x12 with the code. Membership of card X (use X's canonical row for
     setcodes): Spell/Trap → yes; DIVINE attribute or Divine-Beast race → yes; canonical(X) in `n` → yes; any X setcode
     matches any domain archetype `s` with the engine test `(d & 0xfff) == (x & 0xfff) && (d & x) == d` → yes;
     X attribute & `a` → yes; X race & `r` → yes; else no.
- Host: duel rule "Domain" = rule index 9 (Custom moves to 10) with `DUEL_MODE_DOMAIN`, deck sizes Main 60-60, Extra 0-15,
  Side 0-0, start hand 5, LP 8000, draw 1. Selecting a Domain banlist selects and locks the Domain rule (like Genesys). LAN
  host and Multirole force `DUEL_MODE_DOMAIN` flags and these sizes when the banlist is a Domain list. Bots: none.
- Duel start (LAN host generic_duel, hand test single_mode, old-replay re-simulation, Multirole Dueling): add each player's
  DM with `OCG_DuelNewCard{team, duelist 0, code, con=team, loc=LOCATION_DECK_MASTER, seq 0, pos POS_FACEDOWN}` after their
  Deck/Extra, when DUEL_DOMAIN.
- Replay (YRP deck block): when `REPLAY_DOMAIN` is set, each duelist's block is followed by `u32 n` (0 or 1) and `n` DM
  codes. Writers: client LAN host and Multirole; reader: client replay parser and old-replay mode.

## 4. Client duel UI
- `ClientField` gains `ClientCard* dmz[2]` and a client-only location `LOCATION_DMZ` (pick an unused client-only value, e.g.
  0x800, not colliding with LOCATION_SKILL 0x400).
- `HINT_DMZ`: create/update `dmz[p]` (face-up, code, store the return count for the tooltip/info text 7113 with
  500*returns); `HINT_DMZ_REMOVE`: fade out and delete it. Hints ≥200 are already processed while catching up.
- Position: in the Extra Monster Zone row, the empty column 0 slot for the local player (X 1.2-2.3, Y -0.6..0.6) and the
  mirrored column 4 slot for the opponent (5.6-6.7); draw a zone outline/label there when DUEL_DOMAIN; hover/click via
  `GetHoverField` (EMZ row sequence 0/4) and the `hovered_location & 0xe` checks.
- `GetCard(con, 0, seq)`: if `dmz[con]` exists, return it (so idle/battle command lists, MSG_SELECT_CARD and friends find
  it); add null guards where a missing card would crash.
- The command menu works for the DMZ card (Summon / Set / Special Summon / Activate) like a hand card.
- `MSG_SELECT_EFFECTYN` with desc 7112 shows the fallback text if the string is missing.
- Card info for the DMZ card shows "Deck Master" and the current cost.

---------------------------------------------------------------------------------------------------
# v2 AMENDMENTS (from the adversarial review in critique/*.md). Where they conflict with v1, v2 wins.
Read critique/engine-rules.md, critique/protocol-compat.md, critique/data-deckbuilding.md for the evidence.

## Engine
- E0 DMZ marker: while in the DMZ the DM has `current.location = 0`, `current.sequence = DMZ_SEQUENCE (0xFF)`,
  `current.controler = owner`, position ALWAYS `POS_FACEDOWN`. Every message that carries the DM's location while it is in
  the DMZ therefore reads `(owner, 0, 0xFF)` (also overlay targets `(owner, 0x80, 0xFF)` when Xyz materials are attached
  to it before it is moved). Constant `DMZ_SEQUENCE 0xFF` is shared with the client.
- E1 Explicit transitions (do not rely on add_card/remove_card at location 0):
  * Leave (in `MoveToField` step 2, keyed on `target->in_dmz`, BEFORE `new_message(MSG_MOVE)`): pay the cost
    (`lp = max(0, lp - cost)`, MSG_PAY_LPCOST with the actual amount if > 0), `target->cancel_field_effect()` while in_dmz
    is still true, `in_dmz = false`, fix `previous.*` (location = virtual location, controler = owner, sequence 0,
    position, pzone false), then continue the normal move. Emit `HINT_DMZ_REMOVE` AFTER the MSG_MOVE (the client also
    infers the leave from the MSG_MOVE, see C-UI). Leaving the DMZ never sets dm_moved.
  * Enter (the DomainReturn move and the initial load): `remove_card` from the real location (cancels field effects with the
    real location), clear `STATUS_PROC_COMPLETE`, `reset(RESET_TODECK, RESET_EVENT)`-equivalent resets, set
    `in_dmz = true`, sequence 0xFF, POS_FACEDOWN, `add_card(owner, 0)`, `apply_field_effect`, `enable_field_effect(true)`.
    Raise EVENT_LEAVE_GRAVE / EVENT_MOVE (single + group) with reason REASON_RULE, reason player = owner; emit the MSG_MOVE
    (current = (owner,0,0xFF)) then `HINT_DMZ` with the new return count. (Reusing SendTo with a post-fixup is fine if the
    result is identical; `send_to` forces POS_FACEUP unless `ignore` — fix the position.)
  * `add_effect` / `apply_field_effect` / `cancel_field_effect` skip the hand TRIGGER_O exception for in_dmz cards.
    `enable_field_effect`'s location-0 bail-out is relaxed ONLY for in_dmz cards (skills/tokens unchanged).
  * `OCG_DuelNewCard(LOCATION_DECK_MASTER)`: ignore the card unless DUEL_DOMAIN and the card is a monster (not Token/Skill);
    set in_dmz before add_card; no separate registration step.
- E2 `dm_moved`: computed in `add_card` from `previous.location` vs the new location (covers draw, mill, Xyz detach — all of
  which pass through location 0 internally); never set when the destination is location 0; also handle
  `swap_deck_and_grave` (field.cpp ~1032-1090) which bypasses add_card. Rule: set when NOT (both previous and new location
  are in LOCATION_ONFIELD|LOCATION_OVERLAY), and the new location is not 0, and the move is not the DMZ leave.
- E3 `summon.location` for summons by effects: operations.cpp special_summon / special_summon_step / group step
  (~185, 224, 3404) use `effective_location()` too.
- E4 Cost-type effects must NOT see the virtual location: while the core evaluates the target/value/condition/operation of
  EFFECT_ACTIVATE_COST, EFFECT_SUMMON_COST, EFFECT_SPSUMMON_COST, EFFECT_MSET_COST, EFFECT_SSET_COST,
  EFFECT_FLIPSUMMON_COST effects, `Card.IsLocation/GetLocation` report the real location (0) for a DMZ card (Chain Energy
  must not apply). Use a counter in core.
- E5 Add EFFECT_EXTRA_SUMMON_COUNT to the codes for which field effects of other cards see the DMZ card at its virtual
  location (Fire Formation - Tensu etc.). Mausoleum of the Emperor works through the HAND branch of summon checks (it passes
  a SINGLE 80921533 effect), not through DECREASE_TRIBUTE.
- E6 DomainReturn hook: no "once per entry" guard; it runs at IdleCommand/BattleCommand/PhaseEvent case 0 whenever any
  player has dm_moved, and dm_moved is cleared for every player examined (prompted or not). After a return that raised
  events, queue `PointEvent(false, true, false)` (no extra free-chain window); if nothing was returned, queue nothing.
  The Damage Step never reaches these hooks.
- E7 Pendulum Summon scope: a counter incremented around every evaluation of an EFFECT_SPSUMMON_PROC_G condition/target/
  operation (IdleCommand list building ~processor.cpp:1549-1565, `filter_spsummon_procedure_g` card.cpp ~2779,
  SpSummonRule PROC_G steps via ExecuteOperation — careful with yields: increment when entering, decrement when the step
  finishes). Only proc_pendulum.lua registers PROC_G.
- E8 Probe gate additionally requires `core.reason_player == DM owner`.

## Data & validation
- D1 `#@dm` lines are keyed by the card's OWN code. The generator writes one for every monster row with `alias == 0` and for
  every row whose alias target has a different name ("always treated as"); none for same-name alternate artworks.
  Lookup (client and server): the DM's own code, then its `alias`. Same for `#@forbid-dm`. Duplicate code: first wins.
- D2 Membership of card X: `type & (SPELL|TRAP)` → yes; `!(type & MONSTER)` → NO; DIVINE attribute or Divine-Beast → yes;
  `X.code ∈ n || alias(X) ∈ n` → yes; archetypes(X) = setcodes of X's own row ∪ setcodes of its alias row (if alias != 0)
  match any `s` with the engine test → yes; X.attribute & a → yes; X.race & r → yes; else no. At runtime always OR the DM's
  own attribute, race and setcodes into the domain (data may be older than the cdb).
- D3 Domain lists force `forbiddentypes |= TYPE_SKILL`. Any card (DM included) whose `ot` has the Rush or Legend scope bits
  → 0x12 (out of domain), whatever the allowed-cards setting. The DM goes through the same unknown/ot/forbidden checks as any
  card; a Token or Skill DM → 0x11. Check 0x11 runs BEFORE the size check and even when deck content checks are disabled.
- D4 Generator inputs: BabelCDB `cards.cdb`, `release-*.cdb`, `prerelease-*.cdb` (never cards-rush*, cards-skills*,
  cards-unofficial, goat-entries). `tools/domain_gen.py` and any override file are added to `.github/local-files.txt`.
- D5 Parsing: `$domain` counts only after a `!` line (both parsers); `#@` lines are parsed and hashed only inside a list that
  has `$domain`; elsewhere they stay comments. A list with both `$domain` and `$genesys`: the second directive is ignored.
  Multirole skips malformed `#@` lines (never throws). Client: track "inside a list" with a flag, not `hash != 0`.
  `GetLFList` must not copy LFList by value (take `const LFList&`).
- D6 Multirole derives Domain mode ONLY from the banlist: clears DUEL_DOMAIN (and the Domain sizes) when the banlist is not a
  Domain list, forces DUEL_MODE_DOMAIN, Main 60-60 / Extra 0-15 / Side 0-0, team sizes 1v1, no DUEL_RELAY, no extraRules
  when it is. The LAN host (netserver.cpp / generic_duel) does the same.
- D7 Generator: assert unique codes, final hash != 0 and != 0x7DFCEE6A. Drop Spell/Trap codes from `n`.
- D8 A quoted string that exactly equals a Spell/Trap card name counts as that card only (no archetype), unless followed by
  card/cards/monster/monsters/Spell/Trap.
- D9 Name resolution includes rows whose alias has a different name (n stores that row's own code; its archetypes count).
- D10 Alias lookups for Domain/singleton use plain `alias != 0` (never the ±10 artwork-range test).
- Policy (rules as written): a mentioned monster's archetypes are in the domain even when that is broad (Dark Magician Girl →
  "Chaos" through Magician of Black Chaos; LV through LV5). Material lines and negated mentions ("non-WATER") count.

## Protocol / client / server
- P1 LAN host `generic_duel.cpp` MSG_HINT switch and hand test `single_mode.cpp`: add 204/205 next to 10/201-203; generic_duel
  also pushes them into `packets_cache` (spectator catch-up).
- P2 Host UI: `UpdateDuelParam` preserves `duel_param & DUEL_DOMAIN` and has `case DUEL_MODE_DOMAIN: setSelected(9)`; every
  hard-coded Custom index 9 becomes 10 (game.cpp ~3132,3140,3148,3159,3171,3178; menu_handler.cpp ~1027); add case 9 to
  the host-tab handler (menu_handler ~917-943), COMBOBOX_DUEL_RULE (sizes {60,60},{0,15},{0,0}, hand 5) and hand test
  (deck_con ~185-206); `BotRuleFilter` returns a value no bot lists for Domain; ONE lock function handles Genesys and
  Domain lists so one does not unlock the other; the language-change path (game.cpp ~3657) keeps Domain.
- P3 Replay: `REPLAY_DOMAIN` set on the YRP1 header (Multirole: HEADER_FLAGS | REPLAY_DOMAIN for the YRP header when the
  room is Domain); Multirole `YRPPastHeaderSize` adds 4+4n per duelist; writers: client LAN host, hand test single_mode
  (also its handTestNoOpponent branch writes count 0), Multirole; reader: replay.cpp ParseDecks + old_replay_mode;
  `ReplayDeck` gains `master` and "save decks from replay" keeps it. Call order: each duelist's DM `OCG_DuelNewCard`
  immediately follows that duelist's Extra Deck cards, identically in generic_duel, single_mode, Multirole and
  old_replay_mode.
- P4 Client mapping: an entry with location 0 and sequence 0xFF (DMZ_SEQUENCE) in idle/battle/chain command lists and in
  GetCard means `dmz[con]` (overlay targets with location 0x80 and sequence 0xFF too). MSG_SELECT_CARD /
  SELECT_UNSELECT_CARD / CONFIRM_CARDS keep their existing location-0 panel paths. MSG_MOVE: previous (0, 0xFF) → move the
  existing `dmz[con]` ClientCard (keeping overlays) into the destination and clear the slot; current (0, 0xFF) → move the
  card into `dmz[con]` instead of deleting it. HINT_DMZ creates/updates the slot (code, return count); HINT_DMZ_REMOVE
  removes the slot card only if it is still there.
- P5 Servers clear DUEL_DOMAIN unless the banlist is a Domain list (see D6). No core version bump; deployment note: the
  server must run the MASQPro core.
- P6 Siding: Domain rooms require the trailer and DM == original DM (LAN host LoadSide, client BUTTON_SIDE_OK, Multirole
  Sidedecking), else side error. Deck / Event::UpdateDeck / LoadDeck carry the DM.
- P7 Client MSG_RELOAD_FIELD keeps the high word of duel_params; `dmz[]` handled in Clear, ReplaySwap, RefreshAllCards.
- P8 MSG_SELECT_EFFECTYN for a card in LOCATION_DECK: do not SetCode on the deck card.
- P9 Room listing / room info / LAN list: check DUEL_DOMAIN first and show "Domain" (7111).
- P10 ydk: match `#master` before the generic `#` comment skip, also when extralist is null. ydke: 4th segment only when a DM
  exists. Omega export cannot carry a DM: warn or omit.
