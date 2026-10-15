# Multirole server: how it handles decks, card data, duel start, core messages and core deployment, and what that means for Domain

Unless marked **[inferred]**, everything below comes from reading the code. Paths are relative to `/home/user/multirole/src/Multirole/` unless shown in full.

## 1. Deck reception (CTOS_UPDATE_DECK)

**Header checks**
- The header is 3 bytes, and the body can be at most 1021 bytes (`YGOPro/CTOSMsg.hpp:15-16`).
- `IsHeaderValid` rejects `GetLength() > MSG_MAX_LENGTH` (`CTOSMsg.hpp:96-98`).
- An invalid header raises `Event::ConnectionLost`, so the player is dropped from the room (`Room/Client.cpp:136-143`).
- Practical consequence: a deck packet over 1021 bytes disconnects the player. It is not just refused.

**Parsing** (`Room/Client.cpp:205-230`)
```cpp
constexpr auto MAX_CARD_COUNT = (MSG_MAX_LENGTH - (sizeof(uint32_t) * 2U)) / sizeof(uint32_t); // 253
const auto mainCount = incoming.Read<uint32_t>(ptr);
const auto sideCount = incoming.Read<uint32_t>(ptr);
if(mainCount + sideCount > MAX_CARD_COUNT) throw std::out_of_range(...);
... main.push_back(Read) ... side.push_back(Read) ...
catch(...) { return; }                 // malformed packet: silently ignored
room->Dispatch(Event::UpdateDeck{*this, main, side});
```
- The layout is `[u32 mainCount][u32 sideCount][main codes...][side codes...]`.
- "main" means Main and Extra mixed together. The MASQPro client sends `main.size()+extra.size()` followed by the main codes, then the extra codes, then the side codes (`/home/user/MASQPro/gframe/menu_handler.cpp:42-49`).
- **Trailing bytes are ignored.** `Read` only checks bounds against the body length (`CTOSMsg.hpp:150-156`), and nothing checks that the whole body was consumed. Extra data appended after the side codes therefore passes harmlessly through an unmodified server.

**Splitting and storage**
- In the Waiting state, the deck is only stored: `SetOriginalDeck(LoadDeck(e.main, e.side))` (`Room/State/Waiting.cpp:234-239`).
- `LoadDeck` splits the "main" list into Main and Extra by card type (`Room/Context.cpp:174-205`):
  - Fusion, Synchro and Xyz go to Extra.
  - Link Monsters go to Extra.
  - Rituals go to Extra only when `DUEL_EXTRA_DECK_RITUAL` is set.
  - Tokens are dropped (`:199`, `:214`).
  - An unknown code is stored in `Deck::error` (`:194-197`).
- Validation only runs when the player readies up: `Waiting.cpp:131-137` calls `CheckDeck` and sends the error back.

**Side-decking** (`Room/State/Sidedecking.cpp:43-118`)
- The Main and Extra sizes must equal the original's (`:103-106`).
- The full code multiset must be equal (`:107-110`).

## 2. Deck validation (`Room/Context.cpp:225-461`)

Checks run in this order:
1. Unknown card → `CARD_UNKNOWN` (`:240`).
2. Size limits. Main is checked excluding skills: `OutOfBound(limits.main, deck.Main(), skillsCount)` (`:244-266`).
3. If `dontCheckDeckContent`, validation stops here (`:269`).
4. Skill count (`:276`) and Legend count (`:281-301`).
5. Forbidden types, checked against `hostInfo.forb` before aliasing → `CARD_FORBIDDEN_TYPE` (`:314-316`).
6. **Alias merge.** Counts of aliased codes are folded into their base code (`:318-336`). `GetTotalCount` returns the aliased total (`:338-343`).
7. Per-code loop (`:406-422`):
   - more than 3 copies → `CARD_MORE_THAN_3, code`;
   - scope checks → `CARD_UNOFFICIAL` / `CARD_TCG_ONLY` / `CARD_OCG_ONLY`;
   - banlist → `CARD_BANLISTED`.
   - `CheckBanlist` follows an alias only for whitelists or alternate artworks (alias within 10 of the code) (`:385-404`).

**Genesys block** (`:425-459`), active when `banlist->IsGenesys()`:
- Link or Pendulum Monster → `CARD_FORBIDDEN_TYPE, 0`.
- Point total over Main+Extra+Side greater than the cap → `MakeDeckError(GENESYS_POINTS, total, 0, cap)`.

**Where the Genesys flag comes from**
- It is parsed from the banlist file only. A `$genesys [cap]` line sets `genesys = true` and XORs `GenesysCapSalt(cap)` into the hash (`YGOPro/BanlistParser.hpp:90-106`).
- A list whose hash is still the magic value is never registered (`BanlistParser.hpp:66-67`: `if(hash == BANLIST_HASH_MAGIC) return;`). An empty list therefore produces no banlist, and the room falls back to `banlistHash = 0` (`Endpoint/RoomHosting.cpp:201-202`).
- The server never sees a "duel rule" index: `HostInfo::duelRule` and `mode` are marked `// NOTE: UNUSED` (`YGOPro/MsgCommon.hpp:61-62`).

**Error encoding** (`STOCMsgFactory.cpp:300-338`)
- `DeckErrorMsg{msg=2, type, {got,min,max}, code}`, with the struct at `YGOPro/STOCMsg.hpp:59-71`.
- There are two overloads: one sets `code`, the other sets `got/min/max`.
- Codes in use (`STOCMsgFactory.hpp:19-38`):

| Code | Meaning |
|---|---|
| 0x1 | BANLISTED |
| 0x2 / 0x3 | OCG_ONLY / TCG_ONLY |
| 0x4 | UNKNOWN |
| 0x5 | MORE_THAN_3 |
| 0x6 / 0x7 / 0x8 | BAD_MAIN / EXTRA / SIDE count |
| 0x9 | FORBIDDEN_TYPE |
| 0xA | UNOFFICIAL |
| 0xB | INVALID_SIZE |
| 0xC / 0xD | TOO_MANY_LEGENDS / SKILLS |
| 0xE / 0xF | TCG_PRE / OCG_PRE |
| 0x10 | GENESYS_POINTS (MASQPro addition) |

**Genesys host override** (`Endpoint/RoomHosting.cpp:217-229`): it clears `DUEL_PZONE|DUEL_SEPARATE_PZONE|DUEL_EMZONE` from `duelFlagsLow` and sets `hi.forb |= TYPE_PENDULUM|TYPE_LINK`.

## 3. Card data (`YGOPro/CardDatabase.cpp`)

**What gets merged**
- The in-memory database is created with both the `datas` and `texts` schemas (`:14-52`).
- `Merge` ATTACHes each `.cdb` and runs `INSERT OR REPLACE INTO datas SELECT * ...` and the same for `texts` (`:59-67`, `:137-147`).
- No other tables are copied. `SELECT *` also requires the source tables to have exactly the same columns.

**What is actually read**
- Only `datas` is ever queried:
  - `SEARCH_STMT`: `id,alias,setcode,type,atk,def,level,race,attribute` (`:74-78`).
  - `SEARCH2_STMT`: `ot,category` (`:80-84`), exposed as `CardExtraData{scope,category}` (`CardDatabase.hpp:16-20`).
- **`texts` is loaded into memory, but nothing queries it.** The server has no name or description accessor.
- Nothing in `src` reads `strings.conf` or setnames (grep confirms).

**Setcodes and other fields**
- Setcodes are the 64-bit `setcode` column split into 4×u16, zero-terminated (`:155-164`).
- `race` is read as int64 (`:182`).
- Link markers come from `def` (`:176-177`).
- Scales are packed into `level` (`:178-181`).

**Scripts**
- `ScriptProvider` keeps raw Lua source in a map keyed by bare filename (`Service/ScriptProvider.cpp:43-66`).
- The server has no Lua interpreter of its own, so it cannot read script metadata.

**Aliases in the database**
- "A Legendary Ocean" (295517) has alias 22702055 ("Umi"), checked in `cards.cdb`. The existing alias merge therefore already counts them as one card for a singleton check.
- "Sea Stealth II" has alias 0, so it counts separately.

## 4. Duel start (`Room/State/Dueling.cpp:39-235`)

**Extra-rule cards**
- They come from `hostInfo.extraRules` bits (`:54-69`). For example, `EXTRA_RULE_DECK_MASTER` (0x800, `MsgCommon.hpp:36`) adds 153999999.
- That card is the anime "Virtual World / Deck Master" rule script (`cardscripts/unofficial/c153999999.lua`). It is not Domain.
- They are added with a default-initialised `OCG_NewCardInfo`: `loc=0, team=con=duelist=0, pos=POS_FACEDOWN_DEFENSE` (`:119-127`).

**Duel creation**
- Flags are `HostInfo::OrDuelFlags(duelFlagsHigh, duelFlagsLow)` (`:98`, `MsgCommon.hpp:80-83`). Any bit the client puts in `duelFlagsHigh` reaches the core unchanged, apart from the Genesys and relay edits in `RoomHosting.cpp:217-237`.
- Only `constant.lua` and `utility.lua` are preloaded (`:111-112`).

**Adding the player cards** (`:145-171`)
```cpp
nci.team = nci.con = GetSwappedTeam(t);
nci.duelist = (kv.first.second + !!s.currentPos[t]) % teamCount[t];
nci.loc = LOCATION_DECK;  ... AddCard ...   // shuffled/reversed main
nci.loc = LOCATION_EXTRA; ... AddCard ...
s.replay->AddDuelist(nci.team, nci.duelist, {name, finalMainDeck, deck.Extra()});
```
- Only `LOCATION_DECK` and `LOCATION_EXTRA` are used. The side deck is never sent to the core.
- In the core, cards with `duelist != 0` (relay/tag members) are accepted only for `DECK|EXTRA` (`/home/user/MASQPro/ocgcore/ocgapi.cpp:85-86`).
- `duelist == 0` cards go through `is_location_useable` and `add_card` at any single-bit location (`ocgapi.cpp:66-83`).

**Messages sent right after start**
- `MSG_START` is built by the server, not by the core. It is a fixed 18 bytes containing LP and the Deck/Extra counts only (`YGOPro/CoreUtils.cpp:436-449`, `Dueling.cpp:174-187`).
- The Extra Deck query goes to its owner only (`:206-223`).

**Relay**
- The relay flag is removed for 1v1 (`RoomHosting.cpp:230-237`).
- `MSG_TAG_SWAP` advances `currentPos` (`Dueling.cpp:338-343`).
- The team size is clamped to 1..3 (`RoomHosting.cpp:203-204`).

## 5. Core message processing (`Dueling.cpp:316-545`, `YGOPro/CoreUtils.cpp`)

**The loop**
- `Process` → `SplitToMsgs` (u32 length prefix per message, `CoreUtils.cpp:121-142`) → for each message: `PreAnalyzeMsg`, pre-query requests, `DistributeMsg`, post-query requests, `PostAnalyzeMsg` (`Dueling.cpp:518-526`).
- The loop stops when the status is not CONTINUE (`:535`).

**Who replies and who receives**
- The replier is set only when `DoesMessageRequireAnswer` lists the message type (`CoreUtils.cpp:149-183`, `Dueling.cpp:356-361`).
- `GetMessageDistributionType` (`CoreUtils.cpp:185-274`):
  - selection prompts go to the specific duelist; `SELECT_CARD`, `TRIBUTE` and `UNSELECT` are stripped;
  - `MSG_HINT` is routed by subtype `msg[1]` (1/2/3/5 → duelist, 200 → team, 4/6-9/11 → everyone except the duelist, otherwise everyone), with the receiving player at `msg[2]` (`:280-283`);
  - `MOVE`, `SET`, `DRAW`, `SHUFFLE_*`, `*SUMMONING` and `TAG_SWAP` go to everyone, stripped;
  - **any unknown type goes to everyone, unstripped** (`:269-272`).

**MSG_MOVE when a location is 0**
- Stripping (`:349-359`): the card code is zeroed for the opponent unless `current.con == team` or `IsLocInfoPublic(current)`. Public means GRAVE/OVERLAY or not face-down (`:293-301`). A move to `loc 0` whose position is face-up keeps the code visible.
- Post-query (`:558-573`): a single-card refresh is requested only if `current.loc != 0` and the card is not an overlay. Moves to `loc 0` get no update.
- `LocInfo.loc` is **uint8** (`CoreUtils.hpp:11-18`), and so is the core's `loc_info.location` (`ocgcore/card.h:26-31`).
- `MakeUpdateCardMsg` and `MakeUpdateDataMsg` also truncate `loc` and `seq` to uint8 (`CoreUtils.cpp:619-640`).
- All 8 bits are already taken (DECK 0x01 … OVERLAY 0x80, `YGOPro/Constants.hpp:4-11`), so **no new location bit fits in a message**.

**Queries**
- Fixed refresh sets cover hands, monster zones, spell/trap zones and decks (`CoreUtils.cpp:28-50`, `451-617`).
- Location queries: DECK is never sent to anyone, EXTRA goes to its owner only, and other locations are sent full to the owner and stripped to others (`Dueling.cpp:409-425`).
- An unknown `QUERY_*` flag is skipped on read (`CoreUtils.cpp:110-113`) and written back as an empty 4-byte entry (`CoreUtils.cpp:809-810`, `855-856`). Its data is lost.

**Precedent for new message types**
- MASQPro message types 200-211 were added by editing `Constants.hpp`, the distribution and strip logic, and the post-query logic (commit `cabcefe`).

**Replay** (`YGOPro/Replay.cpp`)
- `RecordMsg` drops player-specific hints (1/2/3/5) and all SELECT/ANNOUNCE messages (`:127-166`).
- YRPX stores every remaining message verbatim (`:304-311`).
- The embedded YRP stores, per duelist, **only Main and Extra code vectors**, then the extra-rule cards, then the responses (`:80-100`, `:275-291`).
- Server and core versions are encoded from `SERVER_VERSION` = client 41.0 / core 11.0 (`YGOPro/Config.hpp:10-20`).

## 6. Core deployment

- `coreProvider` in `/home/user/multirole/etc/config.json` observes the git repo `"bin"` (remote `ProjectIgnis/bin`), with `fileRegex ".*libocgcore\\.so"`, `coreType "hornet"` and `loadPerRoom true`.
- On each git update, the first matching file is copied to `tmp/` and loaded once as a test (`Service/CoreProvider.cpp:68-109`).
- If no core is found on first start, the server throws (`:74-78`). The version is only logged, never compared (`:95-96`).
- In hornet mode each room runs a separate `./hornet <core.so> <shm>` process (`Core/HornetWrapper.cpp:73`). Hornet dlopens the core (`Hornet/main.cpp:95`, `284`).
- Hornet resolves only the functions listed in `src/ocgapi_funcs.inl`. A **new exported core function would need edits to `ocgapi_funcs.inl`, `HornetCommon.hpp` Actions, `Hornet/main.cpp`, `HornetWrapper` and `DLWrapper`.**
- Shared-memory buffer: `bytes` holds `2×65535` bytes (`HornetCommon.hpp:51`), and `GET_MESSAGE` memcpys the whole batch into it with no length check (`Hornet/main.cpp:188-196`).
- The struct layouts in `src/ocgapi_types.h` match MASQPro's core, compared with whitespace ignored. Differences are the version macro (9 vs 11) and two extra enum values in the core.
- Repositories are cloned from `remote` with libgit2 (`GitRepo.cpp:46-61`, `117-126`).
- **To deploy:** push a modified `libocgcore.so` (built for Linux/Alpine and matching the `hornet` binary) to a fork of the bin repo, then point `repos[bin].remote` at it.

## Implications for Domain

**Hook points**
1. **Identifying a Domain room.** Two options:
   - A `$domain` directive in the banlist, mirroring `$genesys` (`BanlistParser.hpp:90`, `Banlist::IsGenesys`). It must salt the hash, otherwise an empty "no forbidden cards" list is never registered (`:66`).
   - A new `duelFlagsHigh` bit (bits ≥ 0x2000000000 are free; `ocgcore/ocgapi_constants.h:424-428`). This reaches the core without any server change (`Dueling.cpp:98`).
   - **[inferred]** Using both is cleanest: the banlist carries the Forbidden DM / Forbidden Cards lists, and the flag carries the core behaviour, forced on in `RoomHosting.cpp` as Genesys does.
2. **Marking which card is the DM.** The packet has no field for it. Options:
   - Append a trailing field (for example `[u32 dmCode]`) after the side codes. Older servers ignore it (§1). Parse it in `Client.cpp:205-230`, pass it through `Event::UpdateDeck` and `LoadDeck`, and add a `Deck::dm` field.
   - Or fixed-position conventions; these are fragile.
   - The DM has to be removed from Main/Extra **before** the size check (`Context.cpp:261-264`), or Main shows 61 or Extra 16.
3. **CheckDeck additions:**
   - exactly 1 DM, and it is a monster;
   - singleton: `totalCount > 1` using the existing alias merge, which covers Umi/Legendary Ocean;
   - Main exactly 60 (or set host limits 60/60, 0/15);
   - Forbidden DM list;
   - Domain membership: setcode, attribute and race come from `DataFromCode`.
   - "Mentioned in effect box" names, archetypes, attributes and types are **not** available from the server's data. Precomputed data is needed, for example a new table with a dedicated `Merge` step (the current merge copies only datas and texts), a separate file provider, or entries in the list file.
   - Add new `Error::DeckOrCard` codes (0x11 and up) and matching client strings.
4. **Putting the DM into the core.**
   - The DMZ cannot be a new `LOCATION_*` bit in any message or update (uint8 location, all bits used).
   - **[inferred]** Represent it inside an existing location: an extra SZONE or MZONE sequence, or the Extra Deck plus a status flag. Then MSG_MOVE, stripping and queries keep working.
   - Add the card in `Dueling.cpp:146-171` with a separate `AddCard` call. That needs a core-recognised location/sequence, or a flag-driven core step after `OCG_StartDuel`.
   - In relay, `duelist != 0` cards can only go to DECK/EXTRA (`ocgapi.cpp:85`).
   - `MSG_START` (18 bytes) has no DM count. Send a follow-up MSG_MOVE or query after start, and add the DMZ to the `AddRefreshAll*` sets so clients and spectators stay in sync.
5. **The "return DM to DMZ?" prompt.**
   - Reuse `MSG_SELECT_YESNO` or `MSG_SELECT_EFFECTYN`, which are already routed and timed.
   - A new select-type message must be added to `DoesMessageRequireAnswer`, the distribution logic and `Replay::RecordMsg`. Otherwise it is broadcast to everyone, the replier is stale (the previous one), there is no timer and no MSG_WAITING, and it is recorded in the replay.

**Risks**
- An oversized deck packet (more than 1021 bytes) disconnects the player.
- Side-decking compares the full code multiset and Main/Extra sizes. Any change to the DM there must stay consistent.
- The embedded YRP replay stores only Main and Extra. A DM added through another path will desync old-format replay re-simulation unless it is also recorded (for example in a new header section, which the client reader must understand) **[inferred]**.
- Domain decks without a `dontCheckDeckContent` override will hit the existing 3-copy, scope and Legend checks. These are compatible, but the order of error messages matters.
- Deployment needs a forked bin repo carrying the modified `libocgcore.so`, with the `.so` built for the server platform. The server does not check the core version.
- `ScriptLogger` classifies rooms with non-standard flags as UNOFFICIAL. This is harmless.