/* trtest_mod.c: logs bbfix.ini [trtest] lines= lines of about 400 characters through api->log, numbered TRL00000..., then
   returns 0. trtest.py looks for the numbers in bbtrace.log / bbtrace.1.log. */
#include <windows.h>
#include <string.h>
#include "../bbmod.h"
BB_EXPORT int bbmod_init(const BBModAPI *api) {
    char pad[365]; memset(pad, 'x', sizeof pad - 1); pad[sizeof pad - 1] = 0;
    int n = api->ini_int("trtest", "lines", 0);
    for (int i = 0; i < n; i++) api->log("TRL%05d %s", i, pad);
    return 0;
}
