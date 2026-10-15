#!/bin/bash
# Builds and runs dmz_ui_test.cpp against the objects of a release_x64 ygopro
# build (premake gmake2, see the build instructions). Usage:
#   run_dmz_ui_test.sh <build root, the folder with build/ obj/ bin/ vcpkg/>
set -e
ROOT=${1:?build root}
HERE=$(cd "$(dirname "$0")" && pwd)
OBJ=$ROOT/obj/x64/Release/ygopro
# KEEP=<dir> keeps the test binary there
if [ -n "$KEEP" ]; then
	OUT=$KEEP
	mkdir -p "$OUT"
else
	OUT=$(mktemp -d)
	trap 'rm -rf "$OUT"' EXIT
fi
VCPKG=$ROOT/vcpkg/installed/x64-linux
FLAGS="-m64 -flto -Os -std=c++17 -fno-rtti -fno-strict-aliasing -DNDEBUG -DCURL_STATICLIB -DYGOPRO_USE_SFML"
INCLUDES="-I$ROOT/gframe -I$VCPKG/include -I$ROOT/ocgcore -I$ROOT/sfAudio/include -I$VCPKG/include/irrlicht"
# every object of the client but its entry point, which the test replaces
cat > "$OUT/entry.cpp" <<'EOF'
#include "cli_args.h"
#include "utils.h"
namespace ygo {
epro::thread::id main_thread_id;
}
args_t cli_args;
EOF
g++ $FLAGS $INCLUDES -c "$OUT/entry.cpp" -o "$OUT/entry.o"
g++ $FLAGS $INCLUDES -Wall -Wextra -Wno-unused-parameter -c "$HERE/dmz_ui_test.cpp" -o "$OUT/dmz_ui_test.o"
OBJECTS=$(ls "$OBJ"/*.o | grep -v '/edopro_main\.o$')
g++ -o "$OUT/dmz_ui_test" "$OUT/dmz_ui_test.o" "$OUT/entry.o" $OBJECTS -flto=2 -m64 -static-libgcc -static-libstdc++ \
	-L"$VCPKG/lib" -L/usr/lib64 \
	"$ROOT/bin/x64/release/libocgcore.a" "$ROOT/bin/x64/release/libclzma.a" "$ROOT/bin/x64/release/libsfAudio.a" "$ROOT/bin/x64/release/liblua.a" \
	-lIrrlicht -lFLAC -lvorbisfile -lvorbis -logg -lopenal -lsqlite3 -levent -levent_pthreads -ldl -lgit2 -lssh2 -lpng -lbz2 -lfmt -lcurl -lfreetype \
	-lssl -lcrypto -lz -ljpeg -lpthread
cd "$OUT"
./dmz_ui_test
