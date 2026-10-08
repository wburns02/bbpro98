/* simtrace.c: roadmap #10 M10/M11 referee mod. Wraps a set of FastSim decision functions (steal, pickoff, pitchout,
   catch, fatigue, injury) and records, for every call, what happened inside it: each PlayBalance read
   (FUN_68003170), each RNG call (FUN_68082999 mod, FUN_680829dc range, FUN_68082a2d chance, with which generator),
   each runner-speed read (FUN_68038e10) and each player stat read or write (FUN_6803e1b2 / FUN_6803da2b /
   FUN_6803e2e1 getters returning int *, FUN_6803df0d fatigue state, FUN_6803deec fatigue state set), in order, plus the call's this pointer, stack argument, return value,
   the main and injury RNG states before and after, the game state object and the first 0x100 bytes of *this.
   re/sim_model.py replays the documented formulas (work/SIM_LOGIC_MODEL.md) against these records.
   bbfix.ini:  [mods] load=mods\simtrace.dll    [simtrace] mode=on  file=simtrace.bin  max=400000  cap=20000
   (cap = records per target function, cap<N> overrides it for target N)
   Record, 4492 bytes little-endian:
     u8 fn (index into T below), u8 depth (nesting, 0 = outermost), u8 nev, u8 overflow (events dropped),
     u32 this, u32 arg (0 for one-register functions), u32 eax on return,
     u32 main RNG (DAT_68185a60) before, after; u32 injury RNG (DAT_68113af0) before, after,
     u8[0x50] game state object 0x68143ee0 before, u8[8] manager flags 0x68114948, u8[0x100] *this before (zero when
     this is not readable), u8[4] the target's extra field (T[].xoff) or 0, u8[0x20] *this after the call, Ev[255] events:
       u8 type ('P' PB read, 'M' mod, 'R' range, 'C' chance, 'S' runner speed, 'G' FUN_6803e1b2, 'H' FUN_6803da2b,
       'K' FUN_6803e2e1, 'F' fatigue state read, 'W' fatigue state set, 'X' getter return, 'Y' getter entry, 'Z' call of another target, gen = its index),
       u8 generator (1 main, 2 injury, 3 batter, 0 other; X/Y: the probe id, re/simtrace_probes.py), u16 PB / stat
       index (W: the new state; X: second stack argument), i32 a (mod n / range lo / chance p / object; X: ecx),
       i32 b (range hi; the generator object for M and C; X: first stack argument), i32 result (G/H/K: the int the
       returned pointer points at; X: eax).
   The getters probed with X are generated from the targets' direct callees by re/simtrace_gen.py
   (simtrace_probes.h); the ones that make calls also log a Y marker on entry, so their own nested events are delimited, and
   for getters returning a pointer the int it points at is logged. A getter read identical to the event before it
   (polling loops) is not logged again.
   Records are written when the call returns, so a nested target's record comes before its caller's. */
#include <windows.h>
#include "../bbmod.h"
#include "simtrace_probes.h"

#define NEV 255
#pragma pack(push, 1)
typedef struct Ev { uint8_t t, gen; uint16_t idx; int32_t a, b, r; } Ev;
typedef struct Rec {
    uint8_t fn, depth, nev, over;
    uint32_t self, arg, ret, rm0, rm1, ri0, ri1;
    uint8_t game[0x50], mflags[8], obj[0x100], pad[4], post[0x20];
    Ev ev[NEV];
} Rec;
#pragma pack(pop)
_Static_assert(sizeof(Ev) == 16, "event size");
_Static_assert(sizeof(Rec) == 4492, "record size");

static const BBModAPI *api;
static HANDLE out = INVALID_HANDLE_VALUE;
static long recs, maxrecs, per[16], cap[16];
static uint32_t xoff[16];   /* T[].xoff, copied at init */
static Rec *stack[16];
static int depth;

static void *A(uint32_t va) { return api->addr("FastSim.dll", va); }

static int gen_of(void *rng) {
    return rng == A(0x68185a60) ? 1 : rng == A(0x68113af0) ? 2 : rng == A(0x680a2128) ? 3 : 0;
}

static void ev(uint8_t t, uint8_t gen, uint16_t idx, int32_t a, int32_t b, int32_t r) {
    if (!depth) return;
    Rec *c = stack[depth - 1];
    if (c->nev >= NEV) { if (c->over < 255) c->over++; return; }
    if (t == 'X' && c->nev) {
        Ev *l = &c->ev[c->nev - 1];
        if (l->t == t && l->gen == gen && l->idx == idx && l->a == a && l->b == b && l->r == r) return;
    }
    Ev *e = &c->ev[c->nev++];
    e->t = t; e->gen = gen; e->idx = idx; e->a = a; e->b = b; e->r = r;
}

static Rec *enter(int fn, void *self, uint32_t arg) {
    ev('Z', (uint8_t)fn, 0, (int32_t)self, (int32_t)arg, 0);   /* in the caller's record, if any, even when capped */
    if (out == INVALID_HANDLE_VALUE || recs >= maxrecs || depth >= 16 || per[fn] >= cap[fn]) return NULL;
    per[fn]++;
    Rec *r = HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof(Rec));
    if (!r) return NULL;
    r->fn = (uint8_t)fn; r->depth = (uint8_t)depth;
    r->self = (uint32_t)self; r->arg = arg;
    r->rm0 = *(uint32_t *)A(0x68185a60); r->ri0 = *(uint32_t *)A(0x68113af0);
    CopyMemory(r->game, A(0x68143ee0), sizeof r->game);
    CopyMemory(r->mflags, A(0x68114948), sizeof r->mflags);
    if (self && !IsBadReadPtr(self, sizeof r->obj)) CopyMemory(r->obj, self, sizeof r->obj);
    if (xoff[fn] && self && !IsBadReadPtr((uint8_t *)self + xoff[fn], 4)) CopyMemory(r->pad, (uint8_t *)self + xoff[fn], 4);
    stack[depth++] = r;
    return r;
}

static void leave(Rec *r, uint32_t ret) {
    if (!r) return;
    depth--;
    r->ret = ret;
    r->rm1 = *(uint32_t *)A(0x68185a60); r->ri1 = *(uint32_t *)A(0x68113af0);
    if (r->self && !IsBadReadPtr((void *)r->self, sizeof r->post)) CopyMemory(r->post, (void *)r->self, sizeof r->post);
    DWORD n;
    if (recs < maxrecs) { WriteFile(out, r, sizeof *r, &n, NULL); recs++; }
    HeapFree(GetProcessHeap(), 0, r);
}

/* targets: index, VA, number of stack args (0 or 1), prologue length; all thiscall (fastcall with one register arg
   is the same thing) */
#define T0(N) static uint32_t (BB_THISCALL *o##N)(void *); \
    static uint32_t BB_THISCALL h##N(void *t) { Rec *r = enter(N, t, 0); uint32_t v = o##N(t); leave(r, v); return v; }
#define T1(N) static uint32_t (BB_THISCALL *o##N)(void *, uint32_t); \
    static uint32_t BB_THISCALL h##N(void *t, uint32_t a) { Rec *r = enter(N, t, a); uint32_t v = o##N(t, a); \
                                                            leave(r, v); return v; }
T1(0) T0(1) T0(2) T0(3) T0(4) T0(5) T1(6) T1(7) T1(8) T1(9) T0(10) T0(11) T0(12) T0(13)
/* xoff: a field of *this outside the 0x100-byte snapshot that the function reads directly, copied to Rec.pad */
static const struct { uint32_t va; int args, n; uint32_t xoff; void *h; void **o; const char *what; } T[] = {
    {0x68052bd5, 1, 6, 0, (void *)h0, (void **)&o0, "steal chance (this runner object, base 2/3)"},
    {0x68036d52, 0, 6, 0x34ce, (void *)h1, (void **)&o1, "pickoff chance"},
    {0x68036e91, 0, 6, 0x348e, (void *)h2, (void **)&o2, "pitchout chance"},
    {0x68054b0a, 0, 6, 0, (void *)h3, (void **)&o3, "offensive manager steal / hit and run / bunt / squeeze"},
    {0x68014f7b, 0, 6, 0, (void *)h4, (void **)&o4, "catch attempt"},
    {0x68023dd3, 0, 5, 0, (void *)h5, (void **)&o5, "catch chance position adjust"},
    {0x68049d61, 1, 6, 0, (void *)h6, (void **)&o6, "pitcher fatigue level"},
    {0x680491d4, 1, 6, 0, (void *)h7, (void **)&o7, "pitcher stamina left"},
    {0x6802bde7, 1, 6, 0, (void *)h8, (void **)&o8, "injury check"},
    {0x6802be53, 1, 5, 0, (void *)h9, (void **)&o9, "injury type"},
    {0x6803122b, 0, 9, 0, (void *)h10, (void **)&o10, "pitch execution (location, speed, movement)"},
    {0x68053248, 0, 6, 0, (void *)h11, (void **)&o11, "hit and run chance"},
    {0x680537ad, 0, 6, 0, (void *)h12, (void **)&o12, "sacrifice bunt chance"},
    {0x68053b36, 0, 6, 0, (void *)h13, (void **)&o13, "squeeze chance"},
};

/* probes, recorded only inside a target */
static uint32_t (BB_THISCALL *o_pb)(void *, uint32_t);
static uint32_t BB_THISCALL h_pb(void *t, uint32_t i) { uint32_t v = o_pb(t, i); ev('P', 0, (uint16_t)i, 0, 0, (int32_t)v); return v; }
static uint32_t (BB_THISCALL *o_mod)(void *, uint32_t);
static uint32_t BB_THISCALL h_mod(void *t, uint32_t n) { uint32_t v = o_mod(t, n); ev('M', (uint8_t)gen_of(t), 0, (int32_t)n, (int32_t)t, (int32_t)v); return v; }
static int32_t (BB_THISCALL *o_range)(void *, int32_t, int32_t);
static int32_t BB_THISCALL h_range(void *t, int32_t lo, int32_t hi) { int32_t v = o_range(t, lo, hi); ev('R', (uint8_t)gen_of(t), 0, lo, hi, v); return v; }
static uint32_t (BB_THISCALL *o_chance)(void *, int32_t);
static uint32_t BB_THISCALL h_chance(void *t, int32_t p) { uint32_t v = o_chance(t, p); ev('C', (uint8_t)gen_of(t), 0, p, (int32_t)t, (int32_t)(v & 0xff)); return v; }
static uint32_t (BB_THISCALL *o_speed)(void *);
static uint32_t BB_THISCALL h_speed(void *t) { uint32_t v = o_speed(t); ev('S', 0, 0, (int32_t)t, 0, (int32_t)(v & 0xff)); return v; }
#define GET(N, C) static int32_t *(BB_THISCALL *o_##N)(void *, uint32_t); \
    static int32_t *BB_THISCALL h_##N(void *t, uint32_t i) { int32_t *v = o_##N(t, i); \
        ev(C, 0, (uint16_t)i, (int32_t)t, 0, v && !IsBadReadPtr(v, 4) ? *v : 0x7fffffff); return v; }
GET(g1, 'G') GET(g2, 'H') GET(g3, 'K')
static uint32_t (BB_THISCALL *o_fs)(void *);
static uint32_t BB_THISCALL h_fs(void *t) { uint32_t v = o_fs(t); ev('F', 0, 0, (int32_t)t, 0, (int32_t)v); return v; }
static uint32_t (BB_THISCALL *o_fset)(void *, uint32_t);
static uint32_t BB_THISCALL h_fset(void *t, uint32_t l) { ev('W', 0, (uint16_t)l, (int32_t)t, 0, 0); return o_fset(t, l); }

/* X probes: getters called by the targets (simtrace_probes.h) */
static void *xo[sizeof XP / sizeof *XP];
static void evx(uint8_t t, int id, uint32_t self, uint32_t a1, uint32_t a2, uint32_t r) {
    if (t == 'X' && XP[id].flags & 2) r = r && !IsBadReadPtr((void *)r, 4) ? *(uint32_t *)r : 0x7fffffff;
    ev(t, (uint8_t)id, (uint16_t)a2, (int32_t)self, (int32_t)a1, (int32_t)r);
}
#define XH0(N) static uint32_t BB_THISCALL x##N(void *t) { \
    if (XP[N].flags & 1) evx('Y', N, (uint32_t)t, 0, 0, 0); \
    uint32_t v = ((uint32_t (BB_THISCALL *)(void *))xo[N])(t); evx('X', N, (uint32_t)t, 0, 0, v); return v; }
#define XH1(N) static uint32_t BB_THISCALL x##N(void *t, uint32_t a) { \
    if (XP[N].flags & 1) evx('Y', N, (uint32_t)t, a, 0, 0); \
    uint32_t v = ((uint32_t (BB_THISCALL *)(void *, uint32_t))xo[N])(t, a); evx('X', N, (uint32_t)t, a, 0, v); return v; }
#define XH2(N) static uint32_t BB_THISCALL x##N(void *t, uint32_t a, uint32_t b) { \
    if (XP[N].flags & 1) evx('Y', N, (uint32_t)t, a, b, 0); \
    uint32_t v = ((uint32_t (BB_THISCALL *)(void *, uint32_t, uint32_t))xo[N])(t, a, b); \
    evx('X', N, (uint32_t)t, a, b, v); return v; }
SIMTRACE_PROBES(XH0, XH1, XH2)
#define XADDR(N) (void *)x##N,
static void *const xh[] = {SIMTRACE_PROBES(XADDR, XADDR, XADDR)};

static const uint8_t P6[][6] = {{0x55, 0x8b, 0xec, 0x83, 0xec, 0x04}, {0x55, 0x8b, 0xec, 0x83, 0xec, 0x08},
                                {0x55, 0x8b, 0xec, 0x83, 0xec, 0x0c}};

BB_EXPORT int bbmod_init(const BBModAPI *a) {
    api = a;
    if (a->version != BBMOD_API_VERSION) return 1;
    char m[16], f[MAX_PATH];
    a->ini_str("simtrace", "mode", "on", m, sizeof m);
    if (lstrcmpiA(m, "on")) { a->log("simtrace: mode=%s, nothing registered", m); return 0; }
    a->ini_str("simtrace", "file", "simtrace.bin", f, sizeof f);
    maxrecs = a->ini_int("simtrace", "max", 400000);
    int c0 = a->ini_int("simtrace", "cap", 20000);
    for (int i = 0; i < 16; i++) { char k[8]; wsprintfA(k, "cap%d", i); cap[i] = a->ini_int("simtrace", k, c0); }
    out = CreateFileA(f, FILE_APPEND_DATA, FILE_SHARE_READ, NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (out == INVALID_HANDLE_VALUE) { a->log("simtrace: cannot open %s", f); return 3; }
    /* each target's prologue is checked against the work copy's bytes before patching */
    static const uint8_t pro[][9] = {
        {0x55, 0x8b, 0xec, 0x83, 0xec, 0x2c}, {0x55, 0x8b, 0xec, 0x83, 0xec, 0x18}, {0x55, 0x8b, 0xec, 0x83, 0xec, 0x34},
        {0x55, 0x8b, 0xec, 0x83, 0xec, 0x10}, {0x55, 0x8b, 0xec, 0x83, 0xec, 0x24}, {0x55, 0x8b, 0xec, 0x53, 0x56},
        {0x55, 0x8b, 0xec, 0x83, 0xec, 0x18}, {0x55, 0x8b, 0xec, 0x83, 0xec, 0x20}, {0x55, 0x8b, 0xec, 0x83, 0xec, 0x0c},
        {0x55, 0x8b, 0xec, 0x6a, 0xff}, {0x55, 0x8b, 0xec, 0x81, 0xec, 0xa0, 0x00, 0x00, 0x00},
        {0x55, 0x8b, 0xec, 0x83, 0xec, 0x2c}, {0x55, 0x8b, 0xec, 0x83, 0xec, 0x18}, {0x55, 0x8b, 0xec, 0x83, 0xec, 0x14}};
    for (unsigned i = 0; i < sizeof T / sizeof *T; i++) xoff[i] = T[i].xoff;
    for (unsigned i = 0; i < sizeof T / sizeof *T; i++)
        if (a->detour("FastSim.dll", T[i].va, pro[i], T[i].n, T[i].h, T[i].o) < 0) {
            a->log("simtrace: detour %08x (%s) failed", T[i].va, T[i].what);
            return 2;
        }
    if (a->detour("FastSim.dll", 0x68003170, P6[0], 6, (void *)h_pb, (void **)&o_pb) < 0 ||
        a->detour("FastSim.dll", 0x68082999, P6[1], 6, (void *)h_mod, (void **)&o_mod) < 0 ||
        a->detour("FastSim.dll", 0x680829dc, P6[2], 6, (void *)h_range, (void **)&o_range) < 0 ||
        a->detour("FastSim.dll", 0x68082a2d, P6[1], 6, (void *)h_chance, (void **)&o_chance) < 0 ||
        a->detour("FastSim.dll", 0x68038e10, P6[0], 6, (void *)h_speed, (void **)&o_speed) < 0 ||
        a->detour("FastSim.dll", 0x6803e1b2, P6[0], 6, (void *)h_g1, (void **)&o_g1) < 0 ||
        a->detour("FastSim.dll", 0x6803da2b, P6[0], 6, (void *)h_g2, (void **)&o_g2) < 0 ||
        a->detour("FastSim.dll", 0x6803e2e1, P6[0], 6, (void *)h_g3, (void **)&o_g3) < 0 ||
        a->detour("FastSim.dll", 0x6803df0d, P6[0], 6, (void *)h_fs, (void **)&o_fs) < 0 ||
        a->detour("FastSim.dll", 0x6803deec, P6[0], 6, (void *)h_fset, (void **)&o_fset) < 0) {
        a->log("simtrace: probe detour failed");
        return 2;
    }
    for (unsigned i = 0; i < sizeof XP / sizeof *XP; i++)
        if (a->detour("FastSim.dll", XP[i].va, XP[i].pro, XP[i].len, xh[i], &xo[i]) < 0) {
            a->log("simtrace: getter probe %u (%08x) failed", i, XP[i].va);
            return 2;
        }
    a->log("simtrace: file=%s max=%ld, %u targets registered", f, maxrecs, (unsigned)(sizeof T / sizeof *T));
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD why, LPVOID r) {
    (void)h; (void)r;
    if (why == DLL_PROCESS_DETACH && api) {
        api->log("simtrace final: records %ld", recs);
        if (out != INVALID_HANDLE_VALUE) CloseHandle(out);
    }
    return TRUE;
}
