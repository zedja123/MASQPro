#ifndef DOMAIN_LIST_H
#define DOMAIN_LIST_H

#include <algorithm>
#include <cstdint>
#include <string_view>
#include <unordered_map>
#include <unordered_set>
#include <vector>
#include "ocgapi_constants.h"

namespace ygo {

// Domain format. A "$domain" line turns a banlist into a Domain list; inside
// such a list, lines starting with "#@" carry the Domain data (older parsers
// read them as comments):
//   #@forbid-dm <code>
//   #@dm <code> [a=<hex>] [r=<hex>] [s=<hex>,...] [n=<code>,...]
// "a" and "r" are the attribute and race masks of the Deck Master's domain,
// "s" its archetypes and "n" the monsters named in its text. The parsing and
// the hash contributions must stay identical to Multirole's BanlistParser and
// to the reference implementation (LFListsZedja tools/domain_ref.py).
struct DomainEntry {
	uint32_t attribute{ 0 };
	uint64_t race{ 0 };
	std::vector<uint16_t> setcodes; // sorted, unique, never 0
	std::vector<uint32_t> names; // sorted
};

struct DomainList {
	static constexpr uint32_t Salt = 0x444F4D41U;
	std::unordered_map<uint32_t, DomainEntry> masters;
	std::unordered_set<uint32_t> forbidden_masters;

	void clear() {
		masters.clear();
		forbidden_masters.clear();
	}
	// Hash contribution of one "#@" line: rotl(fnv1a32(text), 1), where text
	// is the line after "#@" without trailing spaces and tabs.
	static uint32_t LineSalt(std::string_view text) {
		uint32_t hash = 0x811C9DC5U;
		for(const auto c : text) {
			hash ^= static_cast<uint8_t>(c);
			hash *= 0x01000193U;
		}
		return (hash << 1) | (hash >> 31);
	}
	static std::string_view TrimLine(std::string_view text) {
		const auto end = text.find_last_not_of(" \t");
		return end == std::string_view::npos ? std::string_view{} : text.substr(0, end + 1);
	}
	// Parses the text of a "#@" line. A malformed line or an unknown directive
	// is skipped (returns false); for a code with several "#@dm" lines the
	// first one wins.
	bool ParseLine(std::string_view text) {
		const auto tokens = Split(text, " \t\v\f\r\n");
		if(tokens.empty())
			return false;
		uint64_t code = 0;
		if(tokens[0] == "forbid-dm") {
			if(tokens.size() != 2 || !ParseUint(tokens[1], 10, UINT32_MAX, code) || code == 0)
				return false;
			forbidden_masters.insert(static_cast<uint32_t>(code));
			return true;
		}
		if(tokens[0] != "dm" || tokens.size() < 2 || !ParseUint(tokens[1], 10, UINT32_MAX, code) || code == 0)
			return false;
		DomainEntry entry;
		for(size_t i = 2; i < tokens.size(); ++i) {
			const auto eq = tokens[i].find('=');
			if(eq == std::string_view::npos)
				return false;
			const auto key = tokens[i].substr(0, eq);
			const auto items = Split(tokens[i].substr(eq + 1), ",");
			uint64_t value = 0;
			if(key == "a" || key == "r") {
				if(items.size() > 1 || (!items.empty() && !ParseUint(items[0], 16, key == "a" ? UINT32_MAX : UINT64_MAX, value)))
					return false;
				if(key == "a")
					entry.attribute = static_cast<uint32_t>(value);
				else
					entry.race = value;
			} else if(key == "s") {
				entry.setcodes.clear();
				for(const auto& item : items) {
					if(!ParseUint(item, 16, 0xffff, value))
						return false;
					if(value)
						entry.setcodes.push_back(static_cast<uint16_t>(value));
				}
			} else if(key == "n") {
				entry.names.clear();
				for(const auto& item : items) {
					if(!ParseUint(item, 10, UINT32_MAX, value))
						return false;
					entry.names.push_back(static_cast<uint32_t>(value));
				}
			}
		}
		std::sort(entry.setcodes.begin(), entry.setcodes.end());
		entry.setcodes.erase(std::unique(entry.setcodes.begin(), entry.setcodes.end()), entry.setcodes.end());
		std::sort(entry.names.begin(), entry.names.end());
		masters.emplace(static_cast<uint32_t>(code), std::move(entry));
		return true;
	}
	// Lookups use the card's own code, then its alias (any alias, not only
	// alternate artworks).
	template<typename T>
	const DomainEntry* Find(const T* dm) const {
		auto it = masters.find(dm->code);
		if(it == masters.end() && dm->alias)
			it = masters.find(dm->alias);
		return it == masters.end() ? nullptr : &it->second;
	}
	template<typename T>
	bool IsForbidden(const T* dm) const {
		return forbidden_masters.count(dm->code) || (dm->alias && forbidden_masters.count(dm->alias));
	}
	// The domain of a Deck Master: its "#@dm" line (if any) combined with its
	// own attribute, race and archetypes.
	template<typename T>
	DomainEntry Get(const T* dm) const {
		DomainEntry domain;
		if(const auto* entry = Find(dm))
			domain = *entry;
		domain.attribute |= dm->attribute;
		domain.race |= dm->race;
		for(const auto setcode : dm->setcodes) {
			if(setcode)
				domain.setcodes.push_back(setcode);
		}
		std::sort(domain.setcodes.begin(), domain.setcodes.end());
		domain.setcodes.erase(std::unique(domain.setcodes.begin(), domain.setcodes.end()), domain.setcodes.end());
		return domain;
	}
private:
	static std::vector<std::string_view> Split(std::string_view text, std::string_view separators) {
		std::vector<std::string_view> res;
		size_t pos = 0;
		while((pos = text.find_first_not_of(separators, pos)) != std::string_view::npos) {
			const auto end = text.find_first_of(separators, pos);
			res.push_back(text.substr(pos, end == std::string_view::npos ? std::string_view::npos : end - pos));
			if(end == std::string_view::npos)
				break;
			pos = end;
		}
		return res;
	}
	static bool ParseUint(std::string_view text, uint64_t base, uint64_t limit, uint64_t& out) {
		if(text.empty())
			return false;
		uint64_t value = 0;
		for(const auto c : text) {
			uint64_t digit;
			if(c >= '0' && c <= '9')
				digit = c - '0';
			else if(base == 16 && c >= 'a' && c <= 'f')
				digit = c - 'a' + 10;
			else if(base == 16 && c >= 'A' && c <= 'F')
				digit = c - 'A' + 10;
			else
				return false;
			if(value > (limit - digit) / base)
				return false;
			value = value * base + digit;
		}
		out = value;
		return true;
	}
};

// Whether a card may be in the Main or Extra Deck of a Deck Master with the
// given domain. get_card(code) returns the card data of a code or nullptr; it
// is used for the archetypes of the card's alias row.
template<typename T, typename F>
bool IsInDomain(const T* card, const DomainEntry& domain, F&& get_card) {
	if(card->type & (TYPE_SPELL | TYPE_TRAP))
		return true;
	if(!(card->type & TYPE_MONSTER))
		return false;
	if((card->attribute & ATTRIBUTE_DIVINE) || (card->race & RACE_DIVINE))
		return true;
	const auto named = [&](uint32_t code) {
		return std::binary_search(domain.names.begin(), domain.names.end(), code);
	};
	if(named(card->code) || (card->alias && named(card->alias)))
		return true;
	const auto in_archetype = [&](const std::vector<uint16_t>& setcodes) {
		for(const auto setcode : setcodes) {
			if(!setcode)
				continue;
			for(const auto archetype : domain.setcodes) {
				if((archetype & 0xfff) == (setcode & 0xfff) && (archetype & setcode) == archetype)
					return true;
			}
		}
		return false;
	};
	if(in_archetype(card->setcodes))
		return true;
	if(card->alias) {
		if(const T* alias_card = get_card(card->alias); alias_card && in_archetype(alias_card->setcodes))
			return true;
	}
	return (card->attribute & domain.attribute) || (card->race & domain.race);
}

}

#endif //DOMAIN_LIST_H
