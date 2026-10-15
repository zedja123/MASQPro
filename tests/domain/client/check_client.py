#!/usr/bin/env python3
"""Checks the client's Domain code against the reference implementation.

The functions under test are cut out of the real gframe sources
(deck_manager.cpp, deck_manager.h, network.h, data_manager.h; domain_list.h is
included as it is), compiled with small stubs and harness_main.cpp, and their
results are compared with LFListsZedja tools/domain_ref.py:

  1. list hashes of every .lflist.conf given (and the reference's corner-case
     vector file);
  2. the domain of the rulebook's example Deck Masters: the full set of pool
     monsters in the domain, client against reference, plus the rulebook's
     expectations;
  3. deck checks (Deck Master, sizes, singleton, membership) on decks built
     from the card pool, client against reference;
  4. .ydk "#master" parsing (LoadCardList) and the CTOS_UPDATE_DECK trailer.

Usage:
  check_client.py --ref <domain_ref.py> --babel <BabelCDB dir> --list <Domain.lflist.conf> [lists...]
"""
import argparse
import importlib.util
import os
import random
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, os.pardir, os.pardir, os.pardir))
GFRAME = os.path.join(ROOT, 'gframe')


def read(name):
	with open(os.path.join(GFRAME, name), encoding='utf-8') as f:
		return f.read()


def block(src, start):
	"""The text from `start` to the end of its brace block (plus a trailing ';'
	for a struct). Comments and string and character literals are skipped."""
	i = src.index(start)
	j = src.index('{', i)
	depth = 0
	k = j
	while True:
		c = src[k]
		if src.startswith('//', k):
			k = src.index('\n', k)
			continue
		if src.startswith('/*', k):
			k = src.index('*/', k) + 2
			continue
		if c in '"\'':
			q = c
			k += 1
			while src[k] != q:
				k += 2 if src[k] == '\\' else 1
		elif c == '{':
			depth += 1
		elif c == '}':
			depth -= 1
			if depth == 0:
				break
		k += 1
	end = k + 1
	if src[end:end + 1] == ';':
		end += 1
	return src[i:end]


STUBS = r'''
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <functional>
#include <map>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>
using namespace std::literals;
namespace epro {
using stringview = std::string_view;
using path_string = std::string;
}
struct FileStream : std::ifstream {
	static constexpr auto in = std::ios::in;
	FileStream(const std::string& path, std::ios::openmode mode) : std::ifstream(path, mode | std::ios::binary) {}
};
namespace BufferIO {
inline std::wstring DecodeUTF8(std::string_view s) { return std::wstring(s.begin(), s.end()); }
template<typename T>
inline T Read(const uint8_t*& p) { T v; std::memcpy(&v, p, sizeof(T)); p += sizeof(T); return v; }
}
#include "ocgapi_constants.h"
#include "domain_list.h"
#include "deck.h"
'''


def build(workdir):
	dm_cpp = read('deck_manager.cpp')
	dm_h = read('deck_manager.h')
	net_h = read('network.h')
	data_h = read('data_manager.h')
	scopes = '\n'.join(l for l in data_h.splitlines() if l.startswith(('#define SCOPE_', '#define TYPE_')))
	parts = [STUBS, scopes, 'namespace ygo {',
		re.search(r'constexpr uint32_t DECK_MASTER_TRAILER[^\n]*', net_h).group(0),
		block(data_h, 'struct CardDataC {'),
		block(net_h, 'struct DeckSizes {'),
		'bool operator!=(const DeckSizes::Sizes& l, const size_t c) { return c < l.min || c > l.max; }',
		block(net_h, 'enum ERROR_TYPE : uint8_t {'),
		block(net_h, 'struct DeckError {'),
		'using banlist_content_t = std::unordered_map<uint32_t, int>;',
		'using cardlist_type = std::vector<uint32_t>;',
		block(dm_h, 'struct LFList {'),
		block(dm_h, 'enum class DuelAllowedCards {'),
		r'''
struct DataManagerStub {
	std::map<uint32_t, CardDataC> cards;
	const CardDataC* GetCardData(uint32_t code) const {
		auto it = cards.find(code);
		return it == cards.end() ? nullptr : &it->second;
	}
} gDataManagerStub;
DataManagerStub* gDataManager = &gDataManagerStub;
struct DeckManager {
	std::vector<LFList> _lfList;
	bool LoadLFListSingle(const epro::path_string& path);
	static DeckError CheckDeckContent(const Deck& deck, LFList const* lflist, DuelAllowedCards allowedCards, uint32_t forbiddentypes, bool rituals_in_extra);
	static DeckError CheckDeckSize(const Deck& deck, const DeckSizes& sizes);
	static DeckError CheckDeckMaster(const Deck& deck, const LFList& lflist, bool check_content);
	static DomainEntry GetDomain(const LFList& lflist, const CardDataC* dm);
	static bool IsInDomain(const CardDataC* card, const DomainEntry& domain);
	static uint32_t ReadDeckMasterTrailer(const uint8_t* trailer, size_t len);
	static uint32_t GetGenesysPoints(const Deck& deck, const LFList& lflist);
	static int TypeCount(const Deck::Vector& cards, uint32_t type);
	static int CountLegends(const Deck::Vector& cards, uint32_t type);
};
''']
	for start in ('static constexpr uint32_t GenesysCapSalt(', 'static constexpr uint32_t GenesysPointsSalt(',
			'bool DeckManager::LoadLFListSingle(', 'int DeckManager::TypeCount(', 'int DeckManager::CountLegends(',
			'static DeckError::DERR_TYPE CheckAllowedCards(', 'static DeckError CheckCards(',
			'static DeckError MakeDeckError(', 'static bool IsMainDeckCardMisplaced(',
			'static bool IsExtraDeckCardMisplaced(', 'DeckError DeckManager::CheckDeckMaster(',
			'DomainEntry DeckManager::GetDomain(', 'bool DeckManager::IsInDomain(',
			'static DeckError CheckDomainDeckContent(', 'DeckError DeckManager::CheckDeckContent(',
			'uint32_t DeckManager::GetGenesysPoints(', 'DeckError DeckManager::CheckDeckSize(',
			'uint32_t DeckManager::ReadDeckMasterTrailer(', 'static bool LoadCardList('):
		parts.append(block(dm_cpp, start))
	parts.append(r'''
// .ydk parsing as the deck editor (separated) and the room READY path call it.
void DumpYdk(const std::string& path, bool separated) {
	cardlist_type mainlist, extralist, sidelist;
	uint32_t master = 1;
	LoadCardList(path, &mainlist, separated ? &extralist : nullptr, &sidelist, &master);
	const auto dump = [](const cardlist_type& l) {
		std::string s;
		for(auto c : l)
			s += (s.empty() ? "" : ",") + std::to_string(c);
		return s.empty() ? std::string("-") : s;
	};
	printf("ydk %s %s %s %u\n", dump(mainlist).c_str(), dump(extralist).c_str(), dump(sidelist).c_str(), master);
}
}''')
	harness = open(os.path.join(HERE, 'harness_main.cpp'), encoding='utf-8').read()
	harness = harness.replace('		} else if(cmd == "deck" || cmd == "deckraw") {', r'''		} else if(cmd == "ydk" || cmd == "ydkflat") {
			std::string path;
			ss >> path;
			DumpYdk(path, cmd == "ydk");
			fflush(stdout);
		} else if(cmd == "trailer") {
			std::vector<uint8_t> buf;
			std::string hex;
			while(ss >> hex)
				buf.push_back(static_cast<uint8_t>(std::stoul(hex, nullptr, 16)));
			std::cout << "trailer " << DeckManager::ReadDeckMasterTrailer(buf.data(), buf.size()) << std::endl;
		} else if(cmd == "deck" || cmd == "deckraw") {''')
	src = '\n'.join(parts) + '\n' + harness
	cpp = os.path.join(workdir, 'client_domain.cpp')
	with open(cpp, 'w', encoding='utf-8') as f:
		f.write(src)
	exe = os.path.join(workdir, 'client_domain')
	subprocess.check_call(['g++', '-std=c++17', '-O1', '-Wall', '-Wextra', '-Wno-unused-function',
		'-Wno-unused-parameter', '-I', GFRAME, cpp, '-o', exe])
	return exe


class Harness:
	def __init__(self, exe):
		self.p = subprocess.Popen([exe], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)

	def lines(self, cmd, n=1):
		self.p.stdin.write(cmd + '\n')
		self.p.stdin.flush()
		return [self.p.stdout.readline().rstrip('\n') for _ in range(n)]

	def one(self, cmd):
		return self.lines(cmd)[0]


def load_ref(path):
	spec = importlib.util.spec_from_file_location('domain_ref', path)
	mod = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(mod)
	return mod


FAILURES = []


def expect(cond, what):
	print(('ok   ' if cond else 'FAIL ') + what)
	if not cond:
		FAILURES.append(what)


def main():
	ap = argparse.ArgumentParser()
	ap.add_argument('--ref', required=True)
	ap.add_argument('--babel', required=True)
	ap.add_argument('--list', required=True)
	ap.add_argument('--decks', type=int, default=300, help='number of random decks to compare')
	ap.add_argument('lists', nargs='*')
	args = ap.parse_args()
	ref = load_ref(args.ref)
	ref.selftest()
	work = tempfile.mkdtemp(prefix='client-domain-')
	exe = build(work)
	h = Harness(exe)

	# 1. Hashes.
	vec = os.path.join(work, 'vectors.conf')
	with open(vec, 'wb') as f:
		f.write(ref.VECTOR_FILE)
	for path in [args.list, vec] + args.lists:
		lists = ref.parse_lflist(path)
		got = h.lines('hash ' + path, len(lists))
		for lst, line in zip(lists, got):
			name, hsh, dom, ndm, nforb = line.split('\t')
			expect(int(hsh, 16) == lst.hash and int(dom) == lst.domain and int(ndm) == len(lst.dm)
				and int(nforb) == len(lst.forbid_dm),
				'hash %s [%s] client %s ref 0x%x (dm %s/%d)' % (os.path.basename(path), lst.name, hsh, lst.hash, ndm, len(lst.dm)))
	expect(ref.find_domain_list(args.list).hash == 0xBC3B2D7E, 'Domain.lflist.conf hash is 0xBC3B2D7E')

	# 2. Domains of the rulebook examples.
	cards = ref.load_cards(ref.babel_cdbs(args.babel))
	tsv = os.path.join(work, 'cards.tsv')
	with open(tsv, 'w') as f:
		for c in cards.values():
			f.write('%d %d %d %d %d %d %d\n' % (c.code, c.ot, c.alias, c.setcode, c.type, c.race, c.attribute))
	print(h.one('cards ' + tsv))
	print(h.one('list ' + args.list))
	lst = ref.find_domain_list(args.list)
	pool = ref.domain_pool(cards)

	def client_domain(dm):
		out = h.one('domain %d' % dm).split()
		return set(int(x) for x in out[2:])

	def ref_domain(dm):
		dom = ref.deck_master_domain(lst, cards[dm])
		return set(x.code for x in pool if ref.in_domain(x, dom, cards))

	by_name = {}
	for c in cards.values():
		if c.alias == 0:
			by_name.setdefault(c.name, c.code)

	def code(name):
		return by_name[name]

	# Rulebook examples (domain_rules.md) and a few cards each side of the line.
	examples = {
		'Chronicle Magician': (['Dark Magician', 'Blue-Eyes White Dragon', 'Blue-Eyes Alternative White Dragon',
				'Dark Magician Girl', 'Obelisk the Tormentor', 'Summoned Skull'],
			['Elemental HERO Neos', 'Cyber Dragon']),
		'Lo, the Prayers of the Voiceless Voice': (['Skull Guardian, Protector of the Voiceless Voice',
				'Elemental HERO Neos', 'Blue-Eyes White Dragon', 'Celtic Guardian', 'Cyber Dragon'],
			['Dark Magician', 'Summoned Skull']),
		'Destiny HERO - Malicious': (['Elemental HERO Neos', 'Elemental HERO Stratos', 'Destiny HERO - Plasma',
				'Vision HERO Vyon', 'Evil HERO Malicious Edge', 'Dark Magician'],
			['Cyber Dragon', 'Blue-Eyes White Dragon']),
		'Incredible Ecclesia, the Virtuous': (['Fallen of Albaz', 'Cyber Dragon', 'Dark Magician'],
			['Summoned Skull']),
		'Cyber-Stein': (['Dark Magician', 'Machine Lord \u00dcr', 'Cyber Dragon'],
			['Elemental HERO Neos', 'Blue-Eyes White Dragon']),
		'Dark Magician Girl': (['Dark Magician', 'Apprentice Illusion Magician', 'Magician of Black Chaos'],
			['Cyber Dragon']),
	}
	for dm_name, (inside, outside) in examples.items():
		dm = code(dm_name)
		c = client_domain(dm)
		r = ref_domain(dm)
		expect(c == r, '%s: client and reference domains equal (%d monsters, %d differ)' % (dm_name, len(c), len(c ^ r)))
		for n in inside:
			expect(code(n) in c, '%s: "%s" is in the domain' % (dm_name, n))
		for n in outside:
			expect(code(n) not in c, '%s: "%s" is outside the domain' % (dm_name, n))
	# Every pool monster that has a line: compare a random sample of Deck Masters in full.
	rng = random.Random(1234)
	sample = rng.sample([x.code for x in pool], 60)
	mismatch = [dm for dm in sample if client_domain(dm) != ref_domain(dm)]
	expect(not mismatch, 'domains of 60 random Deck Masters equal (%s)' % mismatch[:5])

	# 3. Deck checks.
	def run_deck(deck, content=True):
		piles = [','.join(str(x) for x in p) or '-' for p in (deck.main, deck.extra, deck.side)]
		out = h.one('%s %s %s' % ('deck' if content else 'deckraw', deck.master or '-', ' '.join(piles))).split()
		return int(out[1]), int(out[2])

	spells = [x.code for x in cards.values() if x.type & (ref.TYPE_SPELL | ref.TYPE_TRAP) and x.alias == 0
		and not x.ot & (ref.SCOPE_RUSH | ref.SCOPE_LEGEND)]
	monsters_main = [x.code for x in pool if not x.type & ref.TYPES_EXTRA]
	monsters_extra = [x.code for x in pool if x.type & ref.TYPES_EXTRA]

	def legal(dm):
		dom = ref.deck_master_domain(lst, cards[dm])
		canon_dm = cards[dm].canonical()
		mm = [c for c in monsters_main if c != canon_dm and ref.in_domain(cards[c], dom, cards)]
		ee = [c for c in monsters_extra if c != canon_dm and ref.in_domain(cards[c], dom, cards)]
		main = rng.sample(mm, min(30, len(mm)))
		main += rng.sample(spells, 60 - len(main))
		extra = rng.sample(ee, min(15, len(ee)))
		return ref.Deck(main, extra, [], dm)

	ok = 0
	for i in range(args.decks):
		dm = rng.choice([x.code for x in pool if not x.type & ref.TYPE_TOKEN])
		deck = legal(dm)
		kind = i % 10
		if kind == 1:
			deck.main[rng.randrange(60)] = rng.choice(monsters_main)       # maybe out of domain
		elif kind == 2:
			deck.main[0] = deck.main[1]                                    # second copy
		elif kind == 3:
			deck.main.append(dm if not cards[dm].type & ref.TYPES_EXTRA else deck.main[0])
			deck.main.pop(0)
		elif kind == 4:
			deck.master = rng.choice(spells)                               # Spell as Deck Master
		elif kind == 5:
			deck.side.append(rng.choice(spells))
		elif kind == 6:
			deck.main.pop()
		elif kind == 7:
			deck.master = None
		elif kind == 8:
			deck.extra.append(rng.choice(monsters_extra))
		elif kind == 9:
			# alternate artworks / treated-as rows of cards already in the deck
			alts = [x.code for x in cards.values() if x.alias and x.alias in set(deck.main)]
			if alts:
				deck.main[-1] = rng.choice(alts)
		for content in (True, False):
			c = run_deck(deck, content)
			r = ref.check_deck(deck, lst, cards, check_content=content)
			if c == r:
				ok += 1
			else:
				expect(False, 'deck %d kind %d content=%s: client %s ref %s' % (i, kind, content, c, r))
	expect(ok == 2 * args.decks, '%d of %d deck checks equal the reference' % (ok, 2 * args.decks))
	# Rulebook singleton example: Umi and A Legendary Ocean.
	umi = code('Umi')
	ocean = [c.code for c in cards.values() if c.name == 'A Legendary Ocean'][0]
	if cards[ocean].alias == umi:
		deck = legal(code('Chronicle Magician'))
		deck.main[-2:] = [umi, ocean]
		expect(run_deck(deck) == (ref.DOMAIN_SINGLETON, ocean), 'Umi + A Legendary Ocean: only 1 copy (0x13)')
	deck = legal(code('Chronicle Magician'))
	deck.main[-1] = code('Cyber Dragon')
	expect(run_deck(deck) == (ref.DOMAIN_OUT_OF_DOMAIN, code('Cyber Dragon')), 'Chronicle Magician + Cyber Dragon: out of domain (0x12)')
	# Amendment D2: a treated-as card keeps the archetypes of its own row
	# (Cyber Harpie Lady is a "Cyber" card treated as Harpie Lady).
	harpie = [c.code for c in cards.values() if c.name == 'Cyber Harpie Lady'][0]
	deck = legal(code('Cyber Dragon'))
	deck.main[-1] = harpie
	expect(run_deck(deck) == (0, 0), 'Cyber Dragon + Cyber Harpie Lady: in the domain through its own row')
	deck = legal(code('Chronicle Magician'))
	deck.main[-1] = harpie
	expect(run_deck(deck) == (ref.DOMAIN_OUT_OF_DOMAIN, harpie), 'Chronicle Magician + Cyber Harpie Lady: out of domain')
	# The Deck Master counts for singleton: an alternate artwork of it in the
	# Main Deck is a second copy.
	dark_magician = code('Dark Magician')
	deck = legal(dark_magician)
	alt = [c.code for c in cards.values() if c.alias == dark_magician][0]
	deck.main[-1] = alt
	expect(run_deck(deck) == (ref.DOMAIN_SINGLETON, alt), 'Deck Master Dark Magician + its alternate artwork: second copy (0x13)')

	# 4. .ydk parsing and the deck trailer.
	ydk = os.path.join(work, 'a.ydk')
	with open(ydk, 'w') as f:
		f.write('#created by test\n#main\n100\n101\n#extra\n200\n!side\n300\n#master\n46986414\n')
	expect(h.one('ydk ' + ydk) == 'ydk 100,101 200 300 46986414', 'ydk with #master after the side deck')
	expect(h.one('ydkflat ' + ydk) == 'ydk 100,101,200 - 300 46986414', 'ydk #master without the extra list (READY path)')
	with open(ydk, 'w') as f:
		f.write('#main\n100\n#master \r\n46986414\n55\n#extra\n200\n!side\n300\n')
	expect(h.one('ydk ' + ydk) == 'ydk 100 200 300 46986414', 'ydk #master in the middle, first code wins')
	expect(h.one('ydkflat ' + ydk) == 'ydk 100,200 - 300 46986414', 'ydk #master in the middle, READY path keeps the Extra Deck')
	with open(ydk, 'w') as f:
		f.write('#created by x\n#master\n46986414\n#main\n100\n101\n#extra\n200\n!side\n300\n')
	expect(h.one('ydk ' + ydk) == 'ydk 100,101 200 300 46986414', 'ydk #master first, #main ends it')
	expect(h.one('ydkflat ' + ydk) == 'ydk 100,101,200 - 300 46986414', 'ydk #master first, READY path')
	with open(ydk, 'w') as f:
		f.write('#main\n100\n#extra\n200\n!side\n')
	expect(h.one('ydk ' + ydk) == 'ydk 100 200 - 0', 'ydk without #master')
	le = lambda v: ' '.join('%02x' % ((v >> (8 * i)) & 0xff) for i in range(4))
	expect(h.one('trailer %s %s' % (le(0x215A4D44), le(46986414))) == 'trailer 46986414', 'trailer read')
	expect(h.one('trailer %s %s' % (le(0x215A4D45), le(46986414))) == 'trailer 0', 'trailer with a wrong magic')
	expect(h.one('trailer %s' % le(0x215A4D44)) == 'trailer 0', 'short trailer')
	expect(h.one('trailer') == 'trailer 0', 'no trailer')

	print('\n%d failure(s)' % len(FAILURES))
	return 1 if FAILURES else 0


if __name__ == '__main__':
	sys.exit(main())
