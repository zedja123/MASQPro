1. **Major: keying `#@dm` by the alias code gives "always treated as" Deck Masters the wrong domain.**
   - **Problem:** §2 keys each `#@dm` line by "canonical code = alias if alternate artwork or always treated as". A treated-as card has its own row and its own text, so it would get the domain of the card it is treated as.
   - **Evidence:** I generated lines with the prototype's rules. In each pair below, the first is the card's own domain and the second is what the spec would use:
     - Crimson Blade Dragon `3294539` (DARK Dragon, Resonator): `a=20 r=2000 s=57` versus `a=4 r=1` from Crimson Blader. It would play as a FIRE Warrior.
     - Odd-Eyes Arcray Dragon `6218704`: `a=30 s=99,f8` versus `a=20 s=f8,20f8`. It loses LIGHT and "Odd-Eyes".
     - Fallen of the White Dragon `73819701`: loses `s=1cf` (Ecclesia).
     - Cyber Harpie Lady `80316585`: loses `0x93` (Cyber).
   - **Spec change:** "`#@dm` is keyed by the card's own code. The generator writes a line for every monster row with `alias==0`, and for every row whose alias target has a different name. It writes none for same-name alternate artworks. Lookup (client and server) tries the DM's own code first, then `alias`." Apply the same order to `#@forbid-dm`.

2. **Major: using X's canonical row for setcodes drops archetypes that treated-as cards carry themselves.**
   - **Evidence:** Cyber Harpie Lady has `0x640093`; its canonical row, Harpie Lady, has `0x64`. With Deck Master Cyber Dragon (domain `s=93`, LIGHT Machine):
     - own row: in the domain through Cyber;
     - canonical row: out, because it is WIND Winged Beast.

     Odd-Eyes Arcray Dragon (`0x9900f8`, canonical Z-ARC `0xf8`) with Deck Master Performapal Odd-Eyes Light Phoenix: own row matches, canonical row does not. On the other side, 31 same-name alternate artworks have setcode `0` while the canonical row has one. Examples: the BEWD arts `89631140-44`, Red-Eyes B. Dragon `74677423-29`, Cyber Dragon `70095155`, Summoned Skull `7078105x`, Dark Paladin `9850211x`, Cyber End Dragon `1546124`. So the canonical row is still needed.
   - **Spec change (§3.6):** "X's archetypes = setcodes of X's own row ∪ setcodes of its alias row (if any). Attribute and Type come from X's own row. Name test: `X.code ∈ n || alias(X) ∈ n`."

3. **Major: Skill and Rush cards get through the membership test, and a Skill makes the Main Deck 61 cards.**
   - **Problem with Skills:** the membership test does not require X to be a monster. `cards-skills.cdb` gives Skills `race` values, for example `0x2` (Spellcaster) on 7 Skills, and `300303016` and `301524288` have race `0x200000` (Divine-Beast) and type `TYPE_SKILL` only. Under §3.6 these pass "Divine-Beast → yes", or "race & r" for a Spellcaster Deck Master. The prototype's `in_domain` treats every non-monster as "spell/trap".
   - **Problem with the Main Deck count:** `CheckDeckSize` (deck_manager.cpp) and Multirole's `skillsCount` (Context.cpp:255-264) leave Skills out of the Main Deck count. So "Main exactly 60" still allows a 61st card that is a Skill.
   - **Problem with Rush cards:** 2,843 Rush rows alias official codes, for example Blue-Eyes White Dragon (Rush) `160001000` → `89631139`. With `ALLOWED_CARDS_ANY`, a Rush card passes on Attribute or Type, and it would use the official card's row.
   - **Spec change:**
     - Order the test as: `type & (SPELL|TRAP)` → yes; `!(type & MONSTER)` → **no**; then Divine, name, archetype, Attribute, Type.
     - A Domain list forces `forbiddentypes |= TYPE_SKILL` on client and server.
     - Any card, the Deck Master included, with `ot & (SCOPE_RUSH|SCOPE_LEGEND)` → `0x12`, whatever the allowed-cards setting.

4. **Major: reading only `cards.cdb` misses new official cards.**
   - **Evidence:** 150 official monsters live outside `cards.cdb`. `release-betb.cdb` has 86 rows with `ot=1`, already released. The `prerelease-*.cdb` files add more, for example `100460001` Pritima. As Deck Masters they get the fallback domain: no base reduction and no mentions. These newest cards are the most likely Deck Master picks.
   - **Spec change:** "The generator reads `cards.cdb`, `release-*.cdb` and `prerelease-*.cdb`, and never `cards-rush*`, `cards-skills*`, `cards-unofficial` or `goat-entries`. Prerelease codes are regenerated when they become official." Add `tools/domain_gen.py` (and any override file) to `.github/local-files.txt`. The mirror runs `git reset --hard upstream/master` (sync.yml) and keeps only the paths listed there.

5. **Major: the parsers' rules for `$domain` and `#@` lines need tightening, but old parsers are compatible.**
   - **What I verified:**
     - Old client: `if(str.empty() || str[0] == '#') continue;` (deck_manager.cpp:59) skips `#@` lines. `$domain` has no space, so it is skipped at `str.find(' ')`. The `#[Domain]` line is an ordinary comment in both parsers and does not interfere.
     - Old Multirole: `#` and `$` fall through `switch(l[0U])`. A list with only `#@` and `$domain` keeps `hash == BANLIST_HASH_MAGIC`, and `ConditionallyAdd` drops it (BanlistParser.hpp). So old servers do not offer it, which is correct.
     - The old client does register it, as an unrestricted list with hash `0x7dfcee6a`. That is harmless but visible.
   - **Mismatches to avoid:**
     - Multirole's `$genesys` branch runs before the `!` check and has no "inside a list" guard. The client's has one (`if(!lflist.hash || lflist.genesys)`).
     - If `#@` lines were folded into the hash in any list, a stray `#@...` comment in an existing list would silently change that list's hash under the new parsers. None exists today; I checked all lists.
   - **Spec change:**
     - "`$domain` counts only after a `!` line, in both parsers. `#@` lines are parsed and hashed only in a list that already has `$domain`. Elsewhere they stay comments."
     - "`$domain` and `$genesys` in the same list: the second one is ignored."
     - "In Multirole, a malformed `#@` line is skipped, never thrown." A throw aborts the whole file (BanlistProvider.cpp:51-57).

6. **Major: every regeneration changes the hash, and Multirole silently drops a hash it does not know.**
   - **Evidence:** RoomHosting.cpp:201-202: `if(info.banlist == nullptr) hi.banlistHash = 0U;`. A client with a stale `Domain.lflist.conf` hosts with flags `DUEL_MODE_DOMAIN`, and the server creates a room with no Domain validation.
   - **Spec change:** "Multirole derives the Domain mode only from the banlist: it clears `DUEL_DOMAIN` (and the rule-9 sizes) when the banlist is not a Domain list, and forces them when it is."
   - **Note:** on a modified file, Multirole's `LoadBanlists` only merges new hashes (GitRepo.cpp:169-170 gives removed plus added; old keys are never erased). Older Domain versions therefore stay valid until restart. Document this as intended.

7. **Minor: XOR hashing is acceptable, but needs a few rules and generator checks.**
   - **Why acceptable:** identical lines cancel, but they also mean the same thing, and the existing card-line hash (deck_manager.cpp:108) already has this property.
   - **Spec change:**
     - "Duplicate `#@dm` for one code: the first one wins, in both parsers. The generator asserts that codes are unique."
     - The client treats `hash==0` as "outside a list" (`if(!lflist.hash) continue;`). The generator should assert that no running hash is `0`, and that the final hash is not `0x7DFCEE6A`. Better still, give the client a separate `in_list` flag.

8. **Minor: Spell and Trap names that are also archetype names leak archetypes.**
   - **Problem:** the prototype's `archname` lookup turns the quoted card name "Polymerization" into archetype `0x46`, because `SET_POLYMERIZATION`/`SET_FUSION` is `0x46`.
   - **Evidence:** 93 Deck Masters get `s=…46`, for example Fluffal Cat, ABC-Dragon Buster and Magnum the Reliever. That admits 8 monsters such as Starving Venom Fusion Dragon and the Hex-Sealed Fusions. 21 Spell/Trap names collide with archetype names, including Ice Barrier, Salamandra, Necrovalley, Metalmorph, Rebellion and Firewall. This contradicts the spec's "Spells/Traps never contribute archetypes".
   - **Spec change:** "A quote that exactly equals a Spell or Trap card name counts as that card only. It counts as an archetype only when followed by card/cards/monster/monsters/Spell/Trap."

9. **Minor: mentions of treated-as names go unresolved.**
   - **Evidence:** `byname` keeps only rows with `alias==0`, so Elemental HERO Marine Neos leaves `unresolved=['Neo-Spacian Marine Dolphin']`. Its domain then misses Neo-Spacian `0x1f`, and Neo-Spacian Grand Mole (EARTH Rock) tests out (`in_domain` → None).
   - **Spec change:** "Name resolution includes rows whose alias has a different name. `n` stores that row's own code, and that monster's archetypes count (rule 2)." The membership test is the one from finding 2.

10. **Minor: Deck Master checks that §3 leaves out.**
    - **Checks the Deck Master must also go through:** the allowed-cards (`ot`) checks (`CheckCards`, and the Multirole loop at Context.cpp:403-418), the ordinary forbidden lines, and the unknown-code check.
    - **Token Deck Masters:** Multirole's `LoadDeck` silently drops Tokens (Context.cpp:199-200). A Token Deck Master has to be rejected explicitly with `0x11`.
    - **The "no deck check" option:** with `dontCheckDeckContent`, `CheckDeck` returns at line 269. A Spell code could then reach `OCG_DuelNewCard` as the Deck Master.
    - **Spec change:** "The Deck Master code must exist and be `TYPE_MONSTER` and not Token or Skill. Check this even with no deck check. The engine ignores a `LOCATION_DECK_MASTER` card that is not a monster."

11. **Minor: alias lookups must use the plain alias, not the artwork-range test.**
    - **Problem:** Genesys `GetPoints` (deck_manager.h:40) and Multirole `PointsOf` only follow an alias within ±10 of the card's code. Dark Magician `36996508` has alias `46986414`. If the Domain code copies that pattern, this Deck Master loses its line and Chronicle Magician's `n=46986414` would not match it.
    - **Spec change:** "Domain lookups and singleton counting use `alias != 0`, never `IsInArtworkOffsetRange`."

12. **Minor: file size and efficiency.**
    - **Size:** all 9,237 lines come to about 280 KB, which is fine. Keep a line for every Deck Master, including the 2,955 that equal the fallback, because the fallback skips base reduction.
    - **Smaller `n`:** drop Spell/Trap codes from `n`. That removes 735 entries, and Spells and Traps are always in the domain anyway.
    - **Lookup copies:** `GetLFList` takes `LFList` by value in its lambda (deck_manager.cpp:170). Every lookup would copy the Domain map. Change it to `const LFList&`.
    - **Fallback safety:** at runtime, always OR in the Deck Master's own Attribute, Type and setcodes, in case the card data was corrected after the list was generated.

13. **Verified as correct: the archetype test and the rulebook examples.**
    - **Archetype test:** the direction `(d&0xfff)==(x&0xfff) && (d&x)==d` matches the engine's `card::match_setcode` (card.h:185), and Multirole has every input the test needs:
      - setcodes (`CardDatabase.cpp:159-162`; no zero gaps in any cdb);
      - `type`, Attribute, Type (race, 64-bit) and `alias`.
    - **Rulebook examples:** these generated lines match the rulebook.

| Deck Master | Generated line |
|---|---|
| Chronicle Magician | `a=20 r=2 s=dd,10a2 n=46986414,89631139` |
| Lo | `a=10 r=2005 s=19e` |
| Incredible Ecclesia | `a=10 r=2 s=16d,1cf n=68468459` (Fallen of the White Dragon enters through its alias) |
| Destiny HERO - Malicious | `s=8` |
| Cyber-Stein | `a=20 r=20`, no `s` |

    - **One open policy question:** Dark Magician Girl gets `s=cf,10a2,20a2`. The extra "Chaos" archetype comes from its mention of Magician of Black Chaos.

Scratch scripts and the generated lines are in `/tmp/claude-0/domain-critique/` (`q1.py`–`q8.py`, `lines.txt`).