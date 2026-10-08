/* pitchtrace.c: roadmap #10 M9 referee mod. Records every call of FastSim's batter swing decision (FBATTR2D,
   FUN_6800e043) and timing roll (FUN_6800da34), both void __fastcall (batter *), and of the contact resolver
   (FUN_68053d2e, void __fastcall (view *), batter at view +0x6b) with the batted-ball launch it may call
   (FUN_68054d4a, thiscall, 6 stack args, ret 0x18), so re/pitch_model.py can replay them from the recorded inputs and
   check the documented formulas (work/SIM_PITCH_MODEL.md).
   bbfix.ini:  [mods] load=mods\pitchtrace.dll    [pitchtrace] mode=on  file=pitchtrace.bin  max=200000
   Each record is 760 bytes, little-endian:
     u8 kind ('E' swing decision, 'T' timing), u8[3] 0,
     u32 batter RNG state (DAT_680a2128) before, after; u32 main RNG state (DAT_68185a60) before, after,
     u8[0x50] game state object at 0x68143ee0 (+0x4a batting-side pointer, +0x4e balls, +0x4f strikes),
     u8[8] manager flag words at 0x68114948, u32 pitch object pointer (DAT_680a224c), u8[4] its +0x7d (pitcher hand),
     u8 its +0x10d, u8[3] 0, u8[0x140] batter object before the call, u8[0x140] after.
   The pitch object fields are zero when the pointer is null.
   Kind 'C' (contact resolver) uses the same 760 bytes differently: u8 'C', u8 launched (FUN_68054d4a called),
     u8[2] 0, the four RNG states, u8[0x50] pitch object +0xd0..+0x11f, u16 pitch record flags (0x680a58de +0x1f),
     u16 0, i16 launch arg 2 (spray angle), u16 0, i32 launch arg 3 (exit speed), u8[4] launch arg 1 (swing angle
     words), u8 0, u8[3] 0, batter object before / after.
   Calls past `max` are passed through unrecorded. */
#include <windows.h>
#include "../bbmod.h"

#define BB_FASTCALL __attribute__((fastcall))
#define OBJ 0x140

static const BBModAPI *api;
static HANDLE out = INVALID_HANDLE_VALUE;
static long recs, maxrecs, ncalls[3];
static void (BB_FASTCALL *orig_swing)(void *b);
static void (BB_FASTCALL *orig_timing)(void *b);
static void (BB_FASTCALL *orig_contact)(void *view);
static void (BB_THISCALL *orig_launch)(void *v, uint32_t a1, uint32_t a2, int32_t a3, void *a4, void *a5, void *a6);
static struct Rec *cur;

#pragma pack(push, 1)
typedef struct Rec {
    uint8_t kind, pad[3];
    uint32_t rb0, rb1, rm0, rm1;
    uint8_t game[0x50], mflags[8];
    uint32_t pitch; uint8_t p7d[4], p10d, pad2[3];
    uint8_t before[OBJ], after[OBJ];
} Rec;
#pragma pack(pop)
_Static_assert(sizeof(Rec) == 760, "record size");

static void *A(uint32_t va) { return api->addr("FastSim.dll", va); }

static void record(char kind, void *b, void (BB_FASTCALL *fn)(void *)) {
    Rec r; ZeroMemory(&r, sizeof r);
    uint32_t *rb = A(0x680a2128), *rm = A(0x68185a60);
    r.kind = (uint8_t)kind;
    r.rb0 = *rb; r.rm0 = *rm;
    CopyMemory(r.game, A(0x68143ee0), sizeof r.game);
    CopyMemory(r.mflags, A(0x68114948), sizeof r.mflags);
    r.pitch = *(uint32_t *)A(0x680a224c);
    if (r.pitch) { CopyMemory(r.p7d, (uint8_t *)r.pitch + 0x7d, 4); r.p10d = *((uint8_t *)r.pitch + 0x10d); }
    CopyMemory(r.before, b, OBJ);
    fn(b);
    r.rb1 = *rb; r.rm1 = *rm;
    CopyMemory(r.after, b, OBJ);
    DWORD n; WriteFile(out, &r, sizeof r, &n, NULL);
    recs++;
}

static void BB_FASTCALL h_swing(void *b) {
    ncalls[0]++;
    if (out != INVALID_HANDLE_VALUE && recs < maxrecs) record('E', b, orig_swing); else orig_swing(b);
}

static void BB_FASTCALL h_timing(void *b) {
    ncalls[1]++;
    if (out != INVALID_HANDLE_VALUE && recs < maxrecs) record('T', b, orig_timing); else orig_timing(b);
}

static void BB_THISCALL h_launch(void *v, uint32_t a1, uint32_t a2, int32_t a3, void *a4, void *a5, void *a6) {
    if (cur) {
        cur->pad[0] = 1;
        *(int16_t *)(cur->mflags + 4) = (int16_t)a2;
        cur->pitch = (uint32_t)a3;
        CopyMemory(cur->p7d, &a1, 4);
        cur = NULL;   /* only the first launch of this contact call */
    }
    orig_launch(v, a1, a2, a3, a4, a5, a6);
}

static void BB_FASTCALL h_contact(void *view) {
    ncalls[2]++;
    uint8_t *b = *(uint8_t **)((uint8_t *)view + 0x6b);
    if (out == INVALID_HANDLE_VALUE || recs >= maxrecs || !b) { orig_contact(view); return; }
    Rec r; ZeroMemory(&r, sizeof r);
    uint32_t *rb = A(0x680a2128), *rm = A(0x68185a60), p = *(uint32_t *)A(0x680a224c);
    r.kind = 'C';
    r.rb0 = *rb; r.rm0 = *rm;
    if (p) CopyMemory(r.game, (uint8_t *)p + 0xd0, sizeof r.game);
    CopyMemory(r.mflags, (uint8_t *)A(0x680a58de) + 0x1f, 2);
    CopyMemory(r.before, b, OBJ);
    cur = &r;
    orig_contact(view);
    cur = NULL;
    r.rb1 = *rb; r.rm1 = *rm;
    CopyMemory(r.after, b, OBJ);
    DWORD n; WriteFile(out, &r, sizeof r, &n, NULL);
    recs++;
}

BB_EXPORT int bbmod_init(const BBModAPI *a) {
    api = a;
    if (a->version != BBMOD_API_VERSION) return 1;
    char m[16], f[MAX_PATH];
    a->ini_str("pitchtrace", "mode", "on", m, sizeof m);
    if (lstrcmpiA(m, "on")) { a->log("pitchtrace: mode=%s, nothing registered", m); return 0; }
    a->ini_str("pitchtrace", "file", "pitchtrace.bin", f, sizeof f);
    maxrecs = a->ini_int("pitchtrace", "max", 200000);
    out = CreateFileA(f, FILE_APPEND_DATA, FILE_SHARE_READ, NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (out == INVALID_HANDLE_VALUE) { a->log("pitchtrace: cannot open %s", f); return 3; }
    static const uint8_t p_swing[6] = {0x55, 0x8b, 0xec, 0x83, 0xec, 0x3c};   /* push ebp / mov ebp,esp / sub esp,3c */
    static const uint8_t p_timing[6] = {0x55, 0x8b, 0xec, 0x83, 0xec, 0x14};  /* push ebp / mov ebp,esp / sub esp,14 */
    if (a->detour("FastSim.dll", 0x6800e043, p_swing, 6, (void *)h_swing, (void **)&orig_swing) < 0) return 2;
    if (a->detour("FastSim.dll", 0x6800da34, p_timing, 6, (void *)h_timing, (void **)&orig_timing) < 0) return 2;
    static const uint8_t p_big[9] = {0x55, 0x8b, 0xec, 0x81, 0xec, 0x88, 0x00, 0x00, 0x00};  /* sub esp,88 */
    static const uint8_t p_launch[9] = {0x55, 0x8b, 0xec, 0x81, 0xec, 0x14, 0x01, 0x00, 0x00};  /* sub esp,114 */
    if (a->detour("FastSim.dll", 0x68053d2e, p_big, 9, (void *)h_contact, (void **)&orig_contact) < 0) return 2;
    if (a->detour("FastSim.dll", 0x68054d4a, p_launch, 9, (void *)h_launch, (void **)&orig_launch) < 0) return 2;
    a->log("pitchtrace: file=%s max=%ld registered", f, maxrecs);
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD why, LPVOID r) {
    (void)h; (void)r;
    if (why == DLL_PROCESS_DETACH && api) {
        api->log("pitchtrace final: swing calls %ld, timing calls %ld, contact calls %ld, records %ld", ncalls[0],
                 ncalls[1], ncalls[2], recs);
        if (out != INVALID_HANDLE_VALUE) CloseHandle(out);
    }
    return TRUE;
}
