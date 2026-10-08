/* hktest_mod.c: one mod source, three builds (-DWHICH=0 good, 1 bad expect, 2 reloc overlap). Hooks hktarget.dll AND
   hkreloc.dll (the same image loaded relocated). VAs at the preferred base come from bbfix.ini [hktest] (written by
   hktest.py from the built DLL's export table). */
#include <windows.h>
#include <string.h>
#include "../bbmod.h"
static const BBModAPI *api;
typedef int (*f1)(int); typedef int (*f2)(int, int);
static void *o_add[2], *o_call[2];
static int va(const char *k) { return api->ini_int("hktest", k, 0); }
static int h_add0(int a, int b) { return ((f2)o_add[0])(a, b) * 100; }
static int h_add1(int a, int b) { return ((f2)o_add[1])(a, b) * 100; }
static int h_call0(int a) { return ((f1)o_call[0])(a) + 1; }
static int h_call1(int a) { return ((f1)o_call[1])(a) + 1; }
static BB_HANDLER uint32_t h_arg(BBRegs *r) { r->stk[0] += 1; return 0; }
static BB_HANDLER uint32_t h_mid(BBRegs *r) {
    if (r->eax == 41) return 0;
    if (r->eax == 77) return (uint32_t)(uintptr_t)api->addr("hktarget.dll", va("f_mid_alt"));
    r->eax += 1000; return 0;
}
BB_EXPORT int bbmod_init(const BBModAPI *a) {
    api = a;
    const char *mods[2] = {"hktarget.dll", "hkreloc.dll"};
    for (int i = 0; i < 2; i++) {
#if WHICH == 0
        static const uint8_t e_add[6] = {0x55,0x8b,0xec,0x83,0xec,0x08}, e_mid[5] = {0x83,0xc0,0x01,0x90,0x90};
        static const uint8_t e_pat[5] = {0xb8,3,0,0,0}, r_pat[5] = {0xb8,4,0,0,0};
        a->detour(mods[i], va("f_add"), e_add, 6, (void *)(i ? h_add1 : h_add0), &o_add[i]);
        a->redirect_call(mods[i], va("f_call") + 4, va("helper5"), (void *)(i ? h_call1 : h_call0), &o_call[i]);
        uint8_t ec[5]; int site = va("f_call2") + 4, rel = va("helper5") - (site + 5); ec[0] = 0xe8; memcpy(ec + 1, &rel, 4);
        a->midhook(mods[i], site, ec, 5, h_arg);   /* lone call displaced into the stub: retargeted */
        a->midhook(mods[i], va("f_mid_site"), e_mid, 5, h_mid);
        a->patch(mods[i], va("f_patch"), e_pat, r_pat, 5);
#elif WHICH == 1
        static const uint8_t e_bad[5] = {0x55,0x8b,0xec,0xb8,0x0c};   /* the real byte is 0x0b */
        a->detour(mods[i], va("f_bad"), e_bad, 5, (void *)h_add0, 0);
#else
        uint8_t e_rel[5]; int g = va("g_val"); e_rel[0] = 0xa1; memcpy(e_rel + 1, &g, 4);
        a->detour(mods[i], va("f_rel"), e_rel, 5, (void *)h_add0, 0);
#endif
    }
    return 0;
}
BOOL WINAPI DllMain(HINSTANCE h, DWORD w, LPVOID r) { (void)h; (void)w; (void)r; return TRUE; }
