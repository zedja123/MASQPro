// Checks of the client side of the Deck Master Zone: the message handlers of
// DuelClient and the ClientField bookkeeping, run in catching-up replay mode
// (no animations, no rendering) on a NULL Irrlicht device.
// Linked against the objects of a ygopro build, see run_dmz_ui_test.sh.
#include <cstdio>
#include <cstdlib>
#include <cmath>
#include <vector>
#include <irrlicht.h>
#include "game.h"
#include "game_config.h"
#include "data_manager.h"
#include "client_card.h"
#include "client_field.h"
#include "duelclient.h"
#include "materials.h"
#include "common.h"

namespace {

int failures = 0;

#define CHECK(cond) do { if(!(cond)) { std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); ++failures; } } while(0)

struct Msg {
	std::vector<uint8_t> buf;
	Msg& u8(uint8_t v) { buf.push_back(v); return *this; }
	Msg& u32(uint32_t v) { for(int i = 0; i < 4; ++i) buf.push_back(static_cast<uint8_t>(v >> (8 * i))); return *this; }
	Msg& u64(uint64_t v) { u32(static_cast<uint32_t>(v)); return u32(static_cast<uint32_t>(v >> 32)); }
	Msg& loc(uint8_t con, uint8_t loc, uint32_t seq, uint32_t pos) { return u8(con).u8(loc).u32(seq).u32(pos); }
};

void Send(uint8_t type, const Msg& msg) {
	ygo::mainGame->dInfo.curMsg = type;
	ygo::DuelClient::ClientAnalyze(msg.buf.data(), static_cast<uint32_t>(msg.buf.size()));
}

void Hint(uint8_t type, uint8_t player, uint64_t data) {
	Send(MSG_HINT, Msg{}.u8(type).u8(player).u64(data));
}

void Move(uint32_t code, Msg prev, Msg cur) {
	Msg m;
	m.u32(code);
	m.buf.insert(m.buf.end(), prev.buf.begin(), prev.buf.end());
	m.buf.insert(m.buf.end(), cur.buf.begin(), cur.buf.end());
	m.u32(REASON_RULE);
	Send(MSG_MOVE, m);
}

Msg Loc(uint8_t con, uint8_t loc, uint32_t seq, uint32_t pos) {
	return Msg{}.loc(con, loc, seq, pos);
}

bool Near(float a, float b) {
	return std::fabs(a - b) < 0.001f;
}

constexpr uint32_t DM = 46986414; // any code
constexpr uint32_t DM2 = 89631139;

}

int main() {
	using namespace ygo;
	irr::SIrrlichtCreationParameters params{};
	params.DriverType = irr::video::EDT_NULL;
	params.DeviceType = irr::EIDT_CONSOLE;
	auto* device = irr::createDeviceEx(params);
	if(!device) {
		std::printf("no Irrlicht device\n");
		return 2;
	}
	gGameConfig = new GameConfig();
	gDataManager = new DataManager();
	mainGame = new Game();
	auto* env = device->getGUIEnvironment();
	mainGame->device = std::shared_ptr<irr::IrrlichtDevice>(device, [](irr::IrrlichtDevice*) {});
	mainGame->env = env;
	mainGame->driver = device->getVideoDriver();
	mainGame->camera = device->getSceneManager()->addCameraSceneNode();
	auto Button = [env] { return env->addButton({ 0, 0, 10, 10 }); };
	mainGame->wCmdMenu = env->addWindow({ 0, 0, 10, 10 });
	mainGame->wPhase = env->addStaticText(L"", { 0, 0, 10, 10 });
	mainGame->btnDP = Button();
	mainGame->btnSP = Button();
	mainGame->btnM1 = Button();
	mainGame->btnBP = Button();
	mainGame->btnM2 = Button();
	mainGame->btnEP = Button();
	mainGame->btnShuffle = Button();
	auto& dInfo = mainGame->dInfo;
	auto& field = mainGame->dField;
	dInfo.isReplay = true;
	dInfo.isCatchingUp = true;
	dInfo.isFirst = true;
	dInfo.compat_mode = false;
	dInfo.duel_params = DUEL_MODE_DOMAIN;
	matManager.SetActiveVertices(0, 1);
	field.Initial(0, 5, 1);
	field.Initial(1, 5, 0);

	// HINT_DMZ creates the zone cards
	CHECK(field.HasDeckMasterZone());
	Hint(HINT_DMZ, 0, DM);
	Hint(HINT_DMZ, 1, DM2 | (uint64_t{ 2 } << 32));
	ClientCard* dm0 = field.dmz[0];
	CHECK(dm0 && dm0->code == DM && dm0->location == LOCATION_DMZ && dm0->controler == 0 && (dm0->position & POS_FACEUP));
	CHECK(field.dmz[1] && field.dmz[1]->code == DM2 && field.dmz_returns[0] == 0 && field.dmz_returns[1] == 2);
	// a second HINT_DMZ only updates the card
	Hint(HINT_DMZ, 0, DM);
	CHECK(field.dmz[0] == dm0);

	// GetCard mapping
	CHECK(field.GetCard(0, 0, DMZ_SEQUENCE) == dm0);
	CHECK(field.GetCard(1, 0, DMZ_SEQUENCE) == field.dmz[1]);
	CHECK(field.GetCard(0, 0, 0) == nullptr);
	CHECK(field.GetCard(0, LOCATION_OVERLAY, DMZ_SEQUENCE, 0) == nullptr);

	// positions: column 0 of the Extra Monster Zone row, mirrored for the opponent
	field.RefreshAllCards();
	CHECK(Near(dm0->curPos.X, 1.75f) && Near(dm0->curPos.Y, 0.0f));
	CHECK(Near(field.dmz[1]->curPos.X, 6.15f) && Near(field.dmz[1]->curPos.Y, 0.0f));
	CHECK(Near(dm0->curRot.Y, 0.0f) && Near(field.dmz[1]->curRot.Z, irr::core::PI));
	irr::core::vector3df chain_pos;
	field.GetChainDrawCoordinates(0, 0, DMZ_SEQUENCE, &chain_pos);
	CHECK(Near(chain_pos.X, 1.75f) && Near(chain_pos.Y, 0.0f));

	// idle command lists find the zone card; unknown cards get a temporary card
	{
		Msg m;
		m.u8(0);
		m.u32(2).u32(DM).u8(0).u8(0).u32(DMZ_SEQUENCE).u32(1234).u8(0).u8(0).u32(7); // summonable
		m.u32(1).u32(DM).u8(0).u8(0).u32(DMZ_SEQUENCE); // special summonable
		m.u32(0); // repositionable
		m.u32(1).u32(DM).u8(0).u8(0).u32(DMZ_SEQUENCE); // monster set
		m.u32(0); // spell/trap set
		m.u32(2).u32(DM).u8(0).u8(0).u32(DMZ_SEQUENCE).u64(5).u8(0) // activatable
			.u32(4321).u8(0).u8(0).u32(3).u64(6).u8(0);
		m.u8(1).u8(1).u8(0);
		Send(MSG_SELECT_IDLECMD, m);
	}
	CHECK(field.summonable_cards.size() == 2 && field.summonable_cards[0] == dm0);
	CHECK(field.summonable_cards[1] && field.summonable_cards[1] != dm0 && field.summonable_cards[1]->code == 1234);
	CHECK(field.spsummonable_cards.size() == 1 && field.spsummonable_cards[0] == dm0);
	CHECK(field.msetable_cards.size() == 1 && field.msetable_cards[0] == dm0);
	CHECK(field.activatable_cards.size() == 2 && field.activatable_cards[0] == dm0 && field.activatable_cards[1]->code == 4321);
	CHECK(field.limbo_temp.size() == 2);
	CHECK((dm0->cmdFlag & (COMMAND_SUMMON | COMMAND_SPSUMMON | COMMAND_MSET | COMMAND_ACTIVATE)) == (COMMAND_SUMMON | COMMAND_SPSUMMON | COMMAND_MSET | COMMAND_ACTIVATE));
	CHECK(field.dmz_act[0] && !field.dmz_act[1]);
	field.ClearCommandFlag();
	CHECK(dm0->cmdFlag == 0 && !field.dmz_act[0]);
	for(auto& pcard : field.limbo_temp)
		delete pcard;
	field.limbo_temp.clear();

	// Xyz material attached to the card in the zone, then the card leaves with it
	ClientCard* mat = field.deck[0][2];
	Move(0, Loc(0, LOCATION_DECK, 2, POS_FACEDOWN), Loc(0, LOCATION_OVERLAY, DMZ_SEQUENCE, 0));
	CHECK(dm0->overlayed.size() == 1 && dm0->overlayed[0] == mat && mat->overlayTarget == dm0 && mat->location == LOCATION_OVERLAY);
	CHECK(field.GetCard(0, LOCATION_OVERLAY, DMZ_SEQUENCE, 0) == mat);
	CHECK(field.deck[0].size() == 4);
	field.RefreshAllCards();
	CHECK(Near(mat->curPos.X, 1.75f - 0.12f));
	Move(DM, Loc(0, 0, DMZ_SEQUENCE, POS_FACEDOWN), Loc(0, LOCATION_MZONE, 2, POS_FACEUP_ATTACK));
	CHECK(field.dmz[0] == nullptr && field.mzone[0][2] == dm0);
	CHECK(dm0->location == LOCATION_MZONE && dm0->sequence == 2 && dm0->position == POS_FACEUP_ATTACK);
	CHECK(dm0->overlayed.size() == 1 && mat->overlayTarget == dm0);
	// HINT_DMZ_REMOVE after the move: nothing left to remove
	Hint(HINT_DMZ_REMOVE, 0, DM);
	CHECK(field.mzone[0][2] == dm0 && field.dmz[0] == nullptr);
	// on the field it is an ordinary card
	CHECK(field.GetCard(0, 0, DMZ_SEQUENCE) == nullptr);
	CHECK(field.GetCard(0, LOCATION_MZONE, 2) == dm0);

	// to the GY, then back to the zone (code hidden for this player)
	Move(0, Loc(0, LOCATION_MZONE | LOCATION_OVERLAY, 2, 0), Loc(0, LOCATION_GRAVE, 0, POS_FACEUP));
	Move(DM, Loc(0, LOCATION_MZONE, 2, POS_FACEUP_ATTACK), Loc(0, LOCATION_GRAVE, 1, POS_FACEUP));
	CHECK(field.grave[0].size() == 2 && field.grave[0][1] == dm0 && dm0->overlayed.empty());
	Move(0, Loc(0, LOCATION_GRAVE, 1, POS_FACEUP), Loc(0, 0, DMZ_SEQUENCE, POS_FACEDOWN));
	CHECK(field.dmz[0] == dm0 && field.grave[0].size() == 1);
	CHECK(dm0->code == DM && dm0->location == LOCATION_DMZ && (dm0->position & POS_FACEUP));
	Hint(HINT_DMZ, 0, DM | (uint64_t{ 1 } << 32));
	CHECK(field.dmz[0] == dm0 && field.dmz_returns[0] == 1);

	// replay side swap
	ClientCard* dm1 = field.dmz[1];
	field.ReplaySwap();
	CHECK(field.dmz[1] == dm0 && field.dmz[0] == dm1 && dm0->controler == 1 && dm1->controler == 0);
	CHECK(field.dmz_returns[1] == 1 && field.dmz_returns[0] == 2);
	CHECK(Near(dm0->curPos.X, 6.15f));
	field.ReplaySwap();
	CHECK(field.dmz[0] == dm0 && dm0->controler == 0 && Near(dm0->curPos.X, 1.75f));
	dInfo.isFirst = true;

	// HINT_DMZ_REMOVE with the card still there removes it
	Hint(HINT_DMZ_REMOVE, 1, DM2);
	CHECK(field.dmz[1] == nullptr);
	// a move out of a zone the client does not know falls back to a new card
	Move(DM2, Loc(1, 0, DMZ_SEQUENCE, POS_FACEDOWN), Loc(1, LOCATION_MZONE, 0, POS_FACEUP_ATTACK));
	CHECK(field.mzone[1][0] && field.mzone[1][0]->code == DM2 && field.dmz[1] == nullptr);
	// ... and a move into the zone from an unknown card creates the zone card
	Move(DM2, Loc(1, 0, 0, POS_FACEDOWN), Loc(1, 0, DMZ_SEQUENCE, POS_FACEDOWN));
	CHECK(field.dmz[1] && field.dmz[1]->code == DM2 && field.dmz[1]->location == LOCATION_DMZ);
	// a location 0 card that is not the zone still goes away as before
	Move(DM2, Loc(1, LOCATION_MZONE, 0, POS_FACEUP_ATTACK), Loc(1, 0, 0, 0));
	CHECK(field.mzone[1][0] == nullptr && field.dmz[1] && field.dmz[1]->code == DM2);

	// MSG_RELOAD_FIELD keeps the high word of the duel flags and the zone
	{
		dInfo.duel_params = DUEL_MODE_DOMAIN;
		Msg m;
		m.u32(static_cast<uint32_t>(DUEL_MODE_DOMAIN));
		for(int p = 0; p < 2; ++p) {
			m.u32(8000);
			for(int i = 0; i < 15; ++i)
				m.u8(0);
			m.u32(3).u32(1).u32(0).u32(0).u32(0).u32(0);
		}
		m.u32(0);
		ClientCard* keep1 = field.dmz[1];
		Send(MSG_RELOAD_FIELD, m);
		CHECK(dInfo.duel_params == DUEL_MODE_DOMAIN);
		CHECK(field.dmz[0] == dm0 && field.dmz[1] == keep1 && field.dmz_returns[0] == 1);
		CHECK(field.deck[0].size() == 3 && field.hand[1].size() == 1 && field.grave[0].empty());
		CHECK(Near(dm0->curPos.X, 1.75f));
	}

	// the 3 columns field falls back to the skill zone
	matManager.SetActiveVertices(1, 1);
	CHECK(&matManager.getDmz() == &matManager.getSkill());
	matManager.SetActiveVertices(0, 1);

	field.Clear();
	CHECK(field.dmz[0] == nullptr && field.dmz[1] == nullptr && field.dmz_returns[0] == 0);
	dInfo.duel_params = DUEL_MODE_MR5;
	CHECK(!field.HasDeckMasterZone());

	std::printf("%s (%d failures)\n", failures ? "FAILED" : "OK", failures);
	std::fflush(stdout);
	std::_Exit(failures ? 1 : 0);
}
