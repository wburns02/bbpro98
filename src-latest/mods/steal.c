/* steal.c: example mod and the roadmap #9 referee mod. Detours FastSim's steal-chance rating (FUN_68052bd5,
   uint __thiscall (void *sit, int base), base 2 = runner on 1st, 3 = runner on 2nd, returns 0..100, ret 4).
   bbfix.ini:  [mods] load=mods\steal.dll    [steal] mode=pass|zero|max|scale  pct=100 (scale only)
   pass = call the original and return its value (null arm: proves the trampoline), zero = never steal,
   max = 100 whenever the original says a steal is possible (> 0), scale = original * pct / 100 clamped to 0..100. */
#include <windows.h>
#include "../bbmod.h"

static const BBModAPI *api;
static int mode, pct;
static long calls, nonzero; static long long sum_in, sum_out;
static uint32_t (BB_THISCALL *orig)(void *sit, int base);

static void report(const char *when) {
    api->log("steal %s: mode=%d calls=%ld nonzero=%ld mean_in=%.2f mean_out=%.2f", when, mode, calls, nonzero,
             calls ? (double)sum_in / calls : 0.0, calls ? (double)sum_out / calls : 0.0);
}

static uint32_t BB_THISCALL h_steal(void *sit, int base) {
    uint32_t v = orig(sit, base), out = v;
    if (mode == 1) out = 0;
    else if (mode == 2) out = v ? 100 : 0;
    else if (mode == 3) { long s = (long)(int16_t)v * pct / 100; out = (uint32_t)(s < 0 ? 0 : s > 100 ? 100 : s); }
    calls++; sum_in += (int16_t)v; sum_out += (int16_t)out; if (v) nonzero++;
    if (calls % 5000 == 0) report("progress");
    return out;
}

BB_EXPORT int bbmod_init(const BBModAPI *a) {
    api = a;
    if (a->version != BBMOD_API_VERSION) return 1;
    char m[16]; a->ini_str("steal", "mode", "pass", m, sizeof m);
    mode = !lstrcmpiA(m, "zero") ? 1 : !lstrcmpiA(m, "max") ? 2 : !lstrcmpiA(m, "scale") ? 3 : 0;
    pct = a->ini_int("steal", "pct", 100);
    static const uint8_t prolog[6] = {0x55, 0x8b, 0xec, 0x83, 0xec, 0x2c};   /* push ebp / mov ebp,esp / sub esp,2c */
    if (a->detour("FastSim.dll", 0x68052bd5, prolog, 6, (void *)h_steal, (void **)&orig) < 0) return 2;
    a->log("steal: mode=%s pct=%d registered", m, pct);
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD why, LPVOID r) {
    (void)h; (void)r;
    if (why == DLL_PROCESS_DETACH && api) report("final");
    return TRUE;
}
