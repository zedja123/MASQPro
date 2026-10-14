#ifndef CONFIG_H
#define CONFIG_H

#include "compiler_features.h"
#include "ocgapi_types.h"
#include "text_types.h"

extern uint16_t PRO_VERSION;
extern bool is_from_discord;
extern bool open_file;
extern epro::path_string open_file_name;
extern bool show_changelog;

#define EDOPRO_VERSION_MAJOR 1
#define EDOPRO_VERSION_MINOR 0
#define EDOPRO_VERSION_PATCH 15
#define MASQPRO_VERSION_STRING \
    STR(EDOPRO_VERSION_MAJOR) "." \
    STR(EDOPRO_VERSION_MINOR) "." \
    STR(EDOPRO_VERSION_PATCH)
#define EDOPRO_VERSION_CODENAME "Summon-Chants"
#define EDOPRO_VERSION_STRING_DEBUG "MASQPro version " STR(EDOPRO_VERSION_MAJOR) "." STR(EDOPRO_VERSION_MINOR) "." STR(EDOPRO_VERSION_PATCH)
#define EDOPRO_VERSION_STRING L"Masquerena's Club: EDOPro | " STR(EDOPRO_VERSION_MAJOR) "." STR(EDOPRO_VERSION_MINOR) "." STR(EDOPRO_VERSION_PATCH) " \"" EDOPRO_VERSION_CODENAME "\""
// Network/replay protocol version sent in the handshake. It is deliberately
// separate from the MASQPro release version above, so a release bump does not
// break compatibility with the server (Multirole's SERVER_VERSION must match).
#define PROTOCOL_VERSION_MAJOR 41
#define PROTOCOL_VERSION_MINOR 0
#define CLIENT_VERSION ((PROTOCOL_VERSION_MAJOR & 0xff) | ((PROTOCOL_VERSION_MINOR & 0xff) << 8) | ((OCG_VERSION_MAJOR & 0xff) << 16) | ((OCG_VERSION_MINOR & 0xff) << 24))
#define GET_CLIENT_VERSION_MAJOR(ver) (ver & 0xff)
#define GET_CLIENT_VERSION_MINOR(ver) ((ver >> 8) & 0xff)
#define GET_CORE_VERSION_MAJOR(ver) ((ver >> 16) & 0xff)
#define GET_CORE_VERSION_MINOR(ver) ((ver >> 24) & 0xff)
#define EXPAND_VERSION(ver) GET_CLIENT_VERSION_MAJOR(ver), GET_CLIENT_VERSION_MINOR(ver), GET_CORE_VERSION_MAJOR(ver), GET_CORE_VERSION_MINOR(ver)

#endif



















