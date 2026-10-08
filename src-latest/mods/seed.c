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
   shell=N (N != 0): the time() seeding of the shell RNG uses N instead (same effect as launching with -nN). EZShell,
   LineUp and Upstats each link their own copy of that generator, seeded the same way, and EZShell/LineUp write
   game.in (GDI, incl. the +996 FastSim seed and the cipher seed), so all four are pinned.
   trace=N (N > 0): log the first N BBShell lagged-Fibonacci draws as "rng <n> <caller> <value>" (range draws via
   FUN_6805c420 also log "rngr <n> <caller> <lo> <hi> <result>"; the -n startup advance is not logged); diff two runs
   to find where the stream diverges. */
#include <windows.h>
#include "../bbmod.h"

static const BBModAPI *api;
static int mode; static uint32_t value;
static long calls;
static int shell;
static void (__cdecl *orig_shell[4])(int n);
static const struct { const char *dll; uint32_t site, target; } shell_seeders[4] = {   /* time() -> advance(N) calls */
    {"BBShell.dll", 0x6805c35c, 0x6805c370}, {"EZShell.dll", 0x6a01f0cc, 0x6a01f0e0},
    {"LineUp.dll", 0x6b011dec, 0x6b011e00}, {"Upstats.dll", 0x6c018c0c, 0x6c018c20}};
static void (BB_THISCALL *orig)(uint32_t *rng, uint32_t seed);
static long trace, draws;
static short (__cdecl *orig_r410)(void), (__cdecl *orig_r450)(void), (__cdecl *orig_rgdi)(void);
static uint32_t (__cdecl *orig_range)(uint32_t lo, uint32_t hi);

/* FUN_6805c3b0 (one lagged-Fibonacci step, value in ax) has a relocated absolute in its prologue, so it is hooked at
   its call sites instead: in FUN_6805c410 (&0x7fff, under FUN_6805c420 range), FUN_6805c450 (1..100) and the GDI
   writer FUN_680620a0. Those wrappers have no frame, so the dummy first parameter is their caller's return address. */
static short draw(short (__cdecl *f)(void), const char *kind, uint32_t caller) {
    short v = f();
    if (++draws <= trace) api->log("rng %ld %s %08x %d", draws, kind, caller, v);
    return v;
}
static short __cdecl h_r410(uint32_t caller) { return draw(orig_r410, "u15", caller); }
static short __cdecl h_r450(uint32_t caller) { return draw(orig_r450, "pct", caller); }
static short __cdecl h_rgdi(void) { return draw(orig_rgdi, "gdi", 0x6806211a); }

static uint32_t __cdecl h_range(uint32_t lo, uint32_t hi) {   /* FUN_6805c420(ushort lo, ushort hi) */
    uint32_t ret = (uint32_t)__builtin_return_address(0);
    uint32_t r = orig_range(lo, hi);
    if (draws <= trace) api->log("rngr %ld %08x %u %u %u", draws, ret, lo & 0xffff, hi & 0xffff, r & 0xffff);
    return r;
}

static void BB_THISCALL h_seed(uint32_t *rng, uint32_t seed) {
    uint32_t use = mode ? value : seed;
    if (++calls <= 400) api->log("seed #%ld in=%u (0x%04x) use=%u", calls, seed, seed, use);
    orig(rng, use);
}

static void shell_seed(int i, int t) {
    api->log("seed: %s rng time %d -> %d", shell_seeders[i].dll, (short)t, shell);
    orig_shell[i](shell);
}
static void __cdecl h_shell0(int t) { shell_seed(0, t); }
static void __cdecl h_shell1(int t) { shell_seed(1, t); }
static void __cdecl h_shell2(int t) { shell_seed(2, t); }
static void __cdecl h_shell3(int t) { shell_seed(3, t); }
static void (__cdecl *const h_shell[4])(int) = {h_shell0, h_shell1, h_shell2, h_shell3};

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
    for (int i = 0; shell && i < 4; i++)
        if (a->redirect_call(shell_seeders[i].dll, shell_seeders[i].site, shell_seeders[i].target, (void *)h_shell[i],
                             (void **)&orig_shell[i]) < 0) return 3;
    trace = a->ini_int("seed", "trace", 0);
    if (trace > 0) {
        static const uint8_t p_rng[7] = {0x56, 0x57, 0x66, 0x8b, 0x7c, 0x24, 0x0c};   /* push esi/edi, mov di,[esp+c] */
        if (a->redirect_call("BBShell.dll", 0x6805c410, 0x6805c3b0, (void *)h_r410, (void **)&orig_r410) < 0 ||
            a->redirect_call("BBShell.dll", 0x6805c450, 0x6805c3b0, (void *)h_r450, (void **)&orig_r450) < 0 ||
            a->redirect_call("BBShell.dll", 0x68062115, 0x6805c3b0, (void *)h_rgdi, (void **)&orig_rgdi) < 0) return 4;
        if (a->detour("BBShell.dll", 0x6805c420, p_rng, 7, (void *)h_range, (void **)&orig_range) < 0) return 5;
    }
    a->log("seed: mode=%s value=%u shell=%d trace=%ld registered", m, value, shell, trace);
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD why, LPVOID r) {
    (void)h; (void)r;
    if (why == DLL_PROCESS_DETACH && api) api->log("seed final: calls=%ld shell draws=%ld", calls, draws);
    return TRUE;
}
