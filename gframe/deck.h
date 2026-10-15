#ifndef DECK_H
#define DECK_H
#include <vector>

namespace ygo {

struct CardDataC;
struct Deck {
	using Vector = std::vector<const CardDataC*>;
	Vector main;
	Vector extra;
	Vector side;
	// Domain format: the Deck Master, kept apart from the other piles.
	const CardDataC* master{ nullptr };
	void clear() {
		main.clear();
		extra.clear();
		side.clear();
		master = nullptr;
	}
};
enum class RITUAL_LOCATION : uint8_t {
	DEFAULT,
	MAIN,
	EXTRA,
};
}

#endif //DECK_H
