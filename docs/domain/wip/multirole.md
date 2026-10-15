I've implemented the Multirole server part of Domain in `/home/user/multirole` on branch `claude/clever-cori-fy407t`, in five commits; nothing is pushed. It builds with no warnings (`meson compile -C /tmp/claude-0/mr-build -j2`). The new test suite passes, and the parser and deck check agree with `domain_ref.py` on every case I ran.

## What I implemented

**List parsing (D5)**
- `YGOPro/Banlist.hpp/.cpp`: new `DomainEntry` (attribute, race, sorted setcodes, sorted names). `Banlist` gains `IsDomain()`, `FindDomain(code, alias)` and `IsForbiddenMaster(code, alias)`; both lookups try the card's own code, then its plain alias (D1, D10).
- `YGOPro/BanlistParser.hpp`:
  - An `inList` flag, set on `!`. `$domain` counts only inside a list and XORs in `0x444F4D41`.
  - `$genesys` and `$domain`: only the first of the two in a list counts.
  - Inside a Domain list, every `#@` line is hashed as `rotl32(fnv1a32(text),1)`. The text is cut at the first CR and trailing spaces/tabs are removed.
  - `#@dm` / `#@forbid-dm` lines are parsed by `Detail::ParseDomainLine`, which never throws: malformed lines are skipped but still hashed, and the first line for a code wins.

**Deck reception**
- `Room/Client.cpp`: after the side codes, it reads the optional trailer `[u32 0x215A4D44][u32 dm]`. If the trailer is missing, wrong or cut short, the DM is 0.
- The DM is passed through `Event::UpdateDeck::master` → `LoadDeck(main, side, master)` → `Deck::Master()`. It is stored as received, so a Token DM still reaches the check.
- `STOCMsgFactory.hpp`: new error codes `DOMAIN_DECK_MASTER` 0x11, `DOMAIN_OUT_OF_DOMAIN` 0x12, `DOMAIN_SINGLETON` 0x13, `DOMAIN_FORBIDDEN_DM` 0x14.

**Deck check**
- New file `Room/DeckCheck.hpp/.cpp` with `CheckDeckMaster`, `CheckContent`, `GetDomain`, `IsInDomain` and `ScopeError`.
- `ScopeError` is the existing allowed-cards logic moved out of `Context::CheckDeck` unchanged, so the normal check now calls it too.
- `Context::CheckDeck`, when `IsDomain()` is true (banlist is a Domain list), runs in this order:
  1. 0x11, even when content checks are off.
  2. 0x14, only when content is checked.
  3. The existing unknown-card check, then the sizes.
  4. If content checks are off, it stops here.
  5. Domain content instead of the usual checks:
     - forbidden types, with Skill always forbidden (D3), then Rush/Legend cards, DM included → 0x12;
     - card by card over DM, Main, Extra, Side: unknown, allowed-cards scope, singleton by `alias ? alias : code` → 0x13, then the list's card lines;
     - membership of every Main/Extra card (D2) → 0x12. The DM's own attribute, race and setcodes are always added to its domain.
- `Sidedecking.cpp`: in Domain rooms the sided deck's DM must equal the original's, otherwise side error (P6).

**Room creation (D6, P5)** — `Endpoint/RoomHosting.cpp`
- Domain list: flags are forced to `DUEL_MODE_DOMAIN` (only `DUEL_TCG_SEGOC_NONPUBLIC` is kept, as in the LAN host). Also forced: forbidden types 0, 1v1, extra rules 0, and sizes Main 60-60, Extra 0-15, Side 0-0. Relay is gone because the low flags are replaced.
- Any other list, or no list: `DUEL_DOMAIN` is cleared.

**Duel start** — `Room/State/Dueling.cpp`
- Each DM is added with `loc=LOCATION_DECK_MASTER`, duelist 0, seq 0, `POS_FACEDOWN`, right after that duelist's Extra Deck cards. `LOCATION_DECK_MASTER` is now defined in `YGOPro/Constants.hpp`.

**Replay (P3)** — `YGOPro/Replay.hpp/.cpp`
- `Replay::Duelist::master`; `REPLAY_DOMAIN = 0x400`, matching the client.
- The YRP header gets `HEADER_FLAGS | REPLAY_DOMAIN` when the duel flags contain `DUEL_DOMAIN`; the YRPX header stays as before.
- Each duelist's block is followed by `[u32 n][n codes]`, and `YRPPastHeaderSize` adds `4+4n` per duelist.

**Hints and listing (checked, no logic change)**
- Hints 204/205 fall into the default `MSG_HINT` branch in `CoreUtils.cpp`, so they go to everyone, into the spectator cache and into the replay. I only updated the comment there.
- The room listing still exposes the full u64 `duel_flag`, including bit 37, plus the forced sizes.

## Tests
Command: `test/domain/run.sh /home/user/lflistszedja /tmp/claude-0/genesys/BabelCDB <workdir>` → exit 0, "ALL OK". It compiles a driver, `test/domain/DomainTest.cpp`, from the real `BanlistParser`, `Banlist`, `Deck`, `CardDatabase` and `DeckCheck` sources.

- **Hashes:** all 10 lists in LFListsZedja match `domain_ref.py hash`, including `Domain.lflist.conf` = **0xBC3B2D7E** and the reference vectors (0x2D18ED69, 0xE63170A0, 0x926D8EE8). Existing lists keep their hashes.
- **Parsed entries:** all 9,379 `#@dm` entries are identical to `domain_ref.py show` (one-off scratch comparison).
- **Fuzzing:** 600 random files with 8,825 `#@`/directive lines give 0 hash mismatches against the reference (scratch run, not in the suite).
- **Decks:** `make_decks.py` writes 317 decks (188 legal) using the real `cards.cdb`, `release-*` and `prerelease-*` databases. Every verdict, error type and card code, matches `domain_ref.check_deck`. Named cases:
  - legal Chronicle Magician deck: OK; legal Lo deck: OK; Extra Deck of 0: OK;
  - out-of-domain card → 0x12;
  - duplicate → 0x13; DM copy in Main → 0x13; Dark Magician plus its alternate artwork → 0x13;
  - BEWD alternate artwork alone passes through its alias: OK;
  - no DM → `0x11 0`; Token, Spell or unknown DM → 0x11;
  - Main 59 / Extra 16 / Side 1 → 0x6 / 0x7 / 0x8.
- **Skill and Rush cards** (the reference does not load them): a Skill in Main → 0x9; a Rush Spell → 0x12; a Skill DM → 0x11.
- **Replay** (`ReplayTest.cpp` + `parse_replay.py`, size asserts active): the Domain YRP has flags 0x730, the DM block appears after the Extra Deck, and the size equals the header's 172; the non-Domain one has 0x330. An extra run under AddressSanitizer was clean.

## Deviations from the spec
1. **Unknown cards before sizes.** In Domain rooms the unknown-card check runs after 0x11/0x14 but before the size check, as Multirole already did; the reference checks sizes first. This only matters for a deck that has both an unknown Main/Side card and a size error. Tokens in Main/Side are still dropped silently by `LoadDeck`, as before; the reference counts them.
2. **Non-Domain lists** only clear `DUEL_DOMAIN`; the sizes are not reset, because 60-60 can be a legitimate custom choice. This matches the LAN host.
3. **Forbidden types are set to 0** in Domain rooms, like the LAN host. Skill is forbidden at check time instead (D3).
4. **`$genesys` outside any list** is now ignored, to match the client and the reference. No existing list hash changes.
5. **0x9 (forbidden type) in Domain rooms carries the card code**; the normal check sends 0.
6. **0x14 is skipped when content checks are off**, following the reference and the client.

## Known gaps
- Not tested end to end with hornet, the MASQPro core and a real client. The trailer parsing in `Client.cpp` has no unit test.
- Deployment: the server must load the MASQPro core. An unmodified core treats the DM as an inert card.
- A regenerated Domain list gets a new hash; the old one stays registered until the server restarts, because the banlist loader only adds new hashes.

## Commits
- `f24eb87` Domain lists: $domain directive and #@ data lines
- `ecc006b` Domain decks: Deck Master transport and deck check
- `be5b4dc` Domain rooms: rule from the banlist, Deck Masters in the duel and replays
- `15b0ec2` Domain: test driver for the list parser and the deck check
- `33e9a8c` Domain: replay test

Key files: `/home/user/multirole/src/Multirole/Room/DeckCheck.cpp`, `/home/user/multirole/src/Multirole/YGOPro/BanlistParser.hpp`, `/home/user/multirole/test/domain/run.sh`