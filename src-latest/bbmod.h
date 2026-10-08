/* bbmod.h: mod SDK for bbfix.dll (FPS Baseball Pro '98 code hooks).

   A mod is a 32-bit Windows DLL that exports   int bbmod_init(const BBModAPI *api)   (cdecl, return 0 = ok).
   bbfix.dll loads every mod named in bbfix.ini [mods] load=a.dll,b.dll (paths relative to the install dir) at startup,
   calls bbmod_init, and applies the hooks it registered every time the target module is mapped (BBShell, FastSim, ...
   are loaded and freed per screen / per sim, and may be relocated: addresses are given as VAs at the module's
   preferred ImageBase, exactly as Ghidra and objdump show them; bbfix rebases them).

   Safety contract, enforced per (mod, module) all-or-nothing: every site's current bytes must equal `expect`, the site
   must lie inside the module image and must not overlap a base-relocation entry. If any site of the group fails, none
   of that mod's sites in that module are written and the reason goes to bbtrace.log ("MOD ..." lines).

   Hook kinds
   - detour(module, va, expect, n, handler, &orig): function entry hook. The first n bytes (n >= 5, whole instructions,
     position independent, or exactly one `call/jmp rel32` with n == 5) become `jmp handler`. *orig receives a
     trampoline that runs the displaced bytes and continues the original: call it to get the stock behavior. Declare the
     handler with the target's exact calling convention (BB_THISCALL for MSVC member functions, ret N must match).
   - midhook(module, va, expect, n, handler): register-level hook at any instruction boundary. handler(BBRegs *r) runs
     with every register and flag saved; registers it writes into *r take effect. r->stk[k] == [site esp + 4*k].
     Return 0 to run the displaced bytes and continue after the site, or an address to jump there instead (the
     displaced bytes are skipped).
   - redirect_call(module, va, target_va, handler, &orig): the `call rel32` at va (which must call target_va) calls
     handler instead; *orig = the original callee's runtime address. Use it to wrap one caller of a function.
   - patch(module, va, expect, repl, n): verified byte replacement (n <= 16).
   - addr(module, va): runtime address of a VA (NULL while the module is not loaded); use it to call game functions.

   Build (32-bit, from the repo root):
     /mnt/nvme/bbpro98/zigenv/bin/python -m ziglang cc -target x86-windows-gnu -O2 -shared -Isrc-latest -o steal.dll src-latest/mods/steal.c
*/
#ifndef BBMOD_H
#define BBMOD_H
#include <stdint.h>

#define BBMOD_API_VERSION 1
#define BB_THISCALL __attribute__((thiscall))
#define BB_HANDLER __attribute__((used, force_align_arg_pointer))
#define BB_EXPORT __declspec(dllexport)

typedef struct BBRegs { uint32_t edi, esi, ebp, esp_, ebx, edx, ecx, eax, efl, resume; uint32_t stk[16]; } BBRegs;
typedef uint32_t (*bb_mid_fn)(BBRegs *r);

typedef struct BBModAPI {
    int version;                                                   /* BBMOD_API_VERSION */
    void (*log)(const char *fmt, ...);                             /* line to bbtrace.log, prefixed "MOD" */
    int (*ini_int)(const char *section, const char *key, int def); /* reads bbfix.ini */
    int (*ini_str)(const char *section, const char *key, const char *def, char *out, int n);
    int (*detour)(const char *module, uint32_t va, const uint8_t *expect, int n, void *handler, void **orig);
    int (*midhook)(const char *module, uint32_t va, const uint8_t *expect, int n, bb_mid_fn handler);
    int (*patch)(const char *module, uint32_t va, const uint8_t *expect, const uint8_t *repl, int n);
    void *(*addr)(const char *module, uint32_t va);
    int (*redirect_call)(const char *module, uint32_t va, uint32_t target_va, void *handler, void **orig);
} BBModAPI;

/* every registration returns a hook id >= 0, or -1 on a bad argument (the reason is logged) */
typedef int (*bbmod_init_fn)(const BBModAPI *api);

#endif
