/* seed.c: pin or log FastSim's random seed (roadmap #10 M12). FastSim's generator is a 32-bit Galois LFSR at
   DAT_68185a60: next = (s >> 1) ^ (s & 1 ? 0xa3000000 : 0), FUN_68082ae1; rand_mod FUN_68082999, rand_range
   FUN_680829dc, chance FUN_68082a2d. FUN_68082968 (void __thiscall (uint32_t *rng, uint32_t seed), 0 -> 0x45, ret 4)
   is the only seeder: FGAME.cpp FUN_68026a71 seeds it per game from the u16 at +1000 of the game.in GDI object (the
   deciphered GDI record's u16 at +996: the object holds the record at +4), and the savegame loaders restore it.
   bbfix.ini:  [mods] load=mods\seed.dll    [seed] mode=pass|fixed  value=12345 (fixed only)
   pass = log each seed and keep it, fixed = every seeding uses `value` (two runs from the same snapshot must then
   produce byte-identical game.bko). */
#include <windows.h>
#include "../bbmod.h"

static const BBModAPI *api;
static int mode; static uint32_t value;
static long calls;
static void (BB_THISCALL *orig)(uint32_t *rng, uint32_t seed);

static void BB_THISCALL h_seed(uint32_t *rng, uint32_t seed) {
    uint32_t use = mode == 1 ? value : seed;
    if (++calls <= 400) api->log("seed #%ld in=%u (0x%04x) use=%u", calls, seed, seed, use);
    orig(rng, use);
}

BB_EXPORT int bbmod_init(const BBModAPI *a) {
    api = a;
    if (a->version != BBMOD_API_VERSION) return 1;
    char m[16]; a->ini_str("seed", "mode", "pass", m, sizeof m);
    mode = !lstrcmpiA(m, "fixed") ? 1 : 0;
    value = (uint32_t)a->ini_int("seed", "value", 12345);
    static const uint8_t prolog[6] = {0x55, 0x8b, 0xec, 0x83, 0xec, 0x04};   /* push ebp / mov ebp,esp / sub esp,4 */
    if (a->detour("FastSim.dll", 0x68082968, prolog, 6, (void *)h_seed, (void **)&orig) < 0) return 2;
    a->log("seed: mode=%s value=%u registered", m, value);
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD why, LPVOID r) {
    (void)h; (void)r;
    if (why == DLL_PROCESS_DETACH && api) api->log("seed final: calls=%ld", calls);
    return TRUE;
}
