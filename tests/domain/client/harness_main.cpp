// Driver for the client Domain checks; included at the end of the translation
// unit that check_client.py builds from the real gframe sources.
//
// Commands (one per line on stdin, results on stdout):
//   cards <tsv>                      load card data: code ot alias setcode type race attribute
//   hash <file>                      "<name>\t<hash>" for every list of the file
//   list <file>                      use the first Domain list of the file for the commands below
//   domain <dm>                      codes of every pool card in the Deck Master's domain
//   deck <dm> <m>,.. <e>,.. <s>,..   check a deck as the LAN host does; "-" is an empty pile
//   deckraw <dm> ...                 same, without content checks
#include <iostream>
#include <sstream>

namespace {
std::vector<uint32_t> ParseCodes(const std::string& text) {
	std::vector<uint32_t> res;
	if(text == "-")
		return res;
	std::stringstream ss(text);
	std::string item;
	while(std::getline(ss, item, ','))
		res.push_back(static_cast<uint32_t>(std::stoul(item)));
	return res;
}
}

int main() {
	using namespace ygo;
	DeckManager manager;
	const LFList* current = nullptr;
	std::string line;
	while(std::getline(std::cin, line)) {
		std::stringstream ss(line);
		std::string cmd;
		ss >> cmd;
		if(cmd == "cards") {
			std::string path;
			ss >> path;
			std::ifstream in(path);
			std::string row;
			while(std::getline(in, row)) {
				std::stringstream rs(row);
				CardDataC card{};
				uint64_t setcode = 0;
				rs >> card.code >> card.ot >> card.alias >> setcode >> card.type >> card.race >> card.attribute;
				for(int i = 0; i < 4; ++i) {
					const auto value = static_cast<uint16_t>((setcode >> (i * 16)) & 0xffff);
					if(value)
						card.setcodes.push_back(value);
				}
				gDataManagerStub.cards[card.code] = card;
			}
			std::cout << "cards " << gDataManagerStub.cards.size() << std::endl;
		} else if(cmd == "hash") {
			std::string path;
			ss >> path;
			DeckManager single;
			single.LoadLFListSingle(path);
			for(const auto& list : single._lfList) {
				std::string name(list.listName.begin(), list.listName.end());
				std::cout << name << "\t" << std::hex << "0x" << list.hash << std::dec
						  << "\t" << list.domain << "\t" << list.domain_data.masters.size()
						  << "\t" << list.domain_data.forbidden_masters.size() << std::endl;
			}
		} else if(cmd == "list") {
			std::string path;
			ss >> path;
			manager._lfList.clear();
			manager.LoadLFListSingle(path);
			current = nullptr;
			for(const auto& list : manager._lfList) {
				if(list.domain) {
					current = &list;
					break;
				}
			}
			std::cout << "list " << (current ? "ok" : "none") << std::endl;
		} else if(cmd == "domain") {
			uint32_t code = 0;
			ss >> code;
			const auto* dm = gDataManagerStub.GetCardData(code);
			if(!current || !dm) {
				std::cout << "error" << std::endl;
				continue;
			}
			const auto domain = DeckManager::GetDomain(*current, dm);
			std::vector<uint32_t> inside;
			for(const auto& [card_code, card] : gDataManagerStub.cards) {
				// The pool: deckable monsters that are not alternate rows.
				if(card.alias || !(card.type & TYPE_MONSTER) || (card.type & TYPE_TOKEN))
					continue;
				if(DeckManager::IsInDomain(&card, domain))
					inside.push_back(card_code);
			}
			std::sort(inside.begin(), inside.end());
			std::cout << "domain " << inside.size();
			for(auto c : inside)
				std::cout << " " << c;
			std::cout << std::endl;
		} else if(cmd == "deck" || cmd == "deckraw") {
			std::string dm, m, e, s;
			ss >> dm >> m >> e >> s;
			Deck deck;
			bool unknown = false;
			const auto fill = [&](Deck::Vector& pile, const std::string& text) {
				for(auto c : ParseCodes(text)) {
					const auto* card = gDataManagerStub.GetCardData(c);
					if(!card) {
						unknown = true;
						continue;
					}
					pile.push_back(card);
				}
			};
			fill(deck.main, m);
			fill(deck.extra, e);
			fill(deck.side, s);
			const uint32_t dm_code = dm == "-" ? 0 : static_cast<uint32_t>(std::stoul(dm));
			deck.master = dm_code ? gDataManagerStub.GetCardData(dm_code) : nullptr;
			if(!current || unknown) {
				std::cout << "error" << std::endl;
				continue;
			}
			const bool content = cmd == "deck";
			// Same order as GenericDuel::PlayerReady.
			static constexpr DeckSizes sizes{ {60,60}, {0,15}, {0,0} };
			auto err = DeckManager::CheckDeckMaster(deck, *current, content);
			if(err.type == DeckError::DOMAIN_DECK_MASTER && !deck.master)
				err.code = dm_code;
			if(err.type == DeckError::NONE)
				err = DeckManager::CheckDeckSize(deck, sizes);
			if(err.type == DeckError::NONE && content)
				err = DeckManager::CheckDeckContent(deck, current, DuelAllowedCards::ALLOWED_CARDS_ANY, 0, false);
			uint32_t code = err.code;
			if(err.type == DeckError::MAINCOUNT || err.type == DeckError::EXTRACOUNT || err.type == DeckError::SIDECOUNT)
				code = 0;
			std::cout << "deck " << static_cast<uint32_t>(err.type) << " " << (err.type ? code : 0) << std::endl;
		}
	}
	return 0;
}
