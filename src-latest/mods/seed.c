/* seed.c: pin or log FastSim's random seed (roadmap #10 M12). FastSim's generator is a 32-bit Galois LFSR at
   DAT_68185a60: next = (s >> 1) ^ (s & 1 ? 0xa3000000 : 0), FUN_68082ae1; rand_mod FUN_68082999, rand_range
   FUN_680829dc, chance FUN_68082a2d. FUN_68082968 (void __thiscall (uint32_t *rng, uint32_t seed), 0 -> 0x45, ret 4)
   is the only seeder: FGAME.cpp FUN_68026a71 seeds it per game from the u16 at +1000 of the game.in GDI object (the
   deciphered GDI record's u16 at +996: the object holds the record at +4), and the savegame loaders restore it.
   The other six call sites restore a saved 32-bit LFSR state (around AI look-ahead and save/load), ~400 per sim day.
   BBShell has its own generator (56-word additive lagged Fibonacci at 0x6808c278, FUN_6805c3b0), advanced N times by
   FUN_6805c370(N). At startup FUN_6805c350 seeds it with time() unless the command line has -n<N>; it draws weather
   (GDI +980..983) and AI lineups, so a whole sim day is only reproducible with `shell` pinned too.
   bbfix.ini:  [mods] load=mods\seed.dll    [seed] mode=pass|game|all  value=12345  shell=0|N
   pass = log each seeding and keep it; game = only the per-game seeding (call at 0x68026b42) uses `value`, state
   restores untouched (two runs from the same snapshot must then produce byte-identical game.bko); all = every
   seeding, restores included, uses `value` (blunt: each restore rewinds the stream to `value`).
   shell=N (N != 0): BBShell's time() seeding uses N instead (same effect as launching with -nN). */
#include <windows.h>
#include "../bbmod.h"

static const BBModAPI *api;
static int mode; static uint32_t value;
static long calls;
static int shell;
static void (__cdecl *orig_shell)(int n);
static void (BB_THISCALL *orig)(uint32_t *rng, uint32_t seed);

static void BB_THISCALL h_seed(uint32_t *rng, uint32_t seed) {
    uint32_t use = mode ? value : seed;
    if (++calls <= 400) api->log("seed #%ld in=%u (0x%04x) use=%u", calls, seed, seed, use);
    orig(rng, use);
}

static void __cdecl h_shell(int t) {   /* replaces FUN_6805c370((short)time(0)) inside FUN_6805c350 */
    api->log("seed: shell rng time %d -> %d", (short)t, shell);
    orig_shell(shell);
}

BB_EXPORT int bbmod_init(const BBModAPI *a) {
    api = a;
    if (a->version != BBMOD_API_VERSION) return 1;
    char m[16]; a->ini_str("seed", "mode", "pass", m, sizeof m);
    mode = !lstrcmpiA(m, "game") ? 1 : !lstrcmpiA(m, "all") ? 2 : 0;
    value = (uint32_t)a->ini_int("seed", "value", 12345);
    static const uint8_t prolog[6] = {0x55, 0x8b, 0xec, 0x83, 0xec, 0x04};   /* push ebp / mov ebp,esp / sub esp,4 */
    if (mode == 1) {   /* FGAME.cpp FUN_68026a71: movzx eax,ax / push eax / mov ecx,DAT_68185a60 / call FUN_68082968 */
        if (a->redirect_call("FastSim.dll", 0x68026b42, 0x68082968, (void *)h_seed, (void **)&orig) < 0) return 2;
    } else if (a->detour("FastSim.dll", 0x68082968, prolog, 6, (void *)h_seed, (void **)&orig) < 0) return 2;
    shell = (short)a->ini_int("seed", "shell", 0);
    if (shell && a->redirect_call("BBShell.dll", 0x6805c35c, 0x6805c370, (void *)h_shell, (void **)&orig_shell) < 0)
        return 3;
    a->log("seed: mode=%s value=%u shell=%d registered", m, value, shell);
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD why, LPVOID r) {
    (void)h; (void)r;
    if (why == DLL_PROCESS_DETACH && api) api->log("seed final: calls=%ld", calls);
    return TRUE;
}
