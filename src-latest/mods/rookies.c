/* rookies.c: generated players drawn like real ones. The free-agent generator (FUN_68040da0 -> FUN_680719f0) rolls
   peak ratings bunched in the middle: in a stock ten-season MLBPA97 run no generated hitter passes 74 contact or 76
   power, where real 26 to 31 year olds reach 96 and 99. Once the 1997 players retire the league has no stars.

   FUN_680719f0 has the generator fill a 192-byte PYR record at gen+0x10e (plaintext, PYR layout), writes it to the
   PYR with FUN_680537e0 (void __fastcall (gen)), then reads it back into the runtime player it adds to the pool. A
   change to the runtime player is never saved (v1 hooked the add and the PYR kept the generated peaks), so this mod
   wraps the write (0x68071a34) and, before the record is written, maps each nonzero peak rating of his class from the
   generated distribution onto
   the real one (rookies_table.h, from work/lahman/rookietable.py): the rating's quantile among generated players,
   read back as the same quantile among real players. A rating inside a flat run of the generated table (many
   generated players share it) takes a random quantile within the run, so ties spread out. The result is blended,
   new = old + alpha * (mapped - old), alpha per class in percent, fractions rounded with the game's roll. Current
   ratings scale with their peak (cur * new / old, at least 1, at most the new peak).

   PYR record: +0 pid (s16), +0x46 the 23 peak ratings, +0x5d the 23 current ratings. Index: 0 contact,
   1 power, 2 speed, 3 arm, 4 hold, 5 endurance, 6 control, 7..13 pitches (a pitcher has one), 14..22 fielding P..RF.
   Hitters map contact, power, speed, arm and fielding 15..22; pitchers arm, hold, endurance, control and pitches.

   bbfix.ini:  [mods] load=mods\rookies.dll
               [rookies] map=on|off   alpha=100,100,100,100,100,100,100,100,100,100   percent per class, in the order
                         h_contact,h_power,h_speed,h_arm,h_field,p_arm,p_hold,p_endur,p_control,p_pitch
                         probe=0   log the first N players' peaks before and after */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include "../bbmod.h"
#include "rookies_table.h"

#define SHELL "BBShell.dll"
#define R_PEAK 0x46
#define R_CUR 0x5d
#define GEN_REC 0x10e

static const BBModAPI *api;
static int map_on, probe, alpha[RQ_CLASSES];
static long mapped, ratings_moved, points_up, points_down;
static void (BB_THISCALL *orig_write)(void *gen);

typedef int (__cdecl *roll_fn)(void);

static int roll(void) {
    roll_fn f = (roll_fn)api->addr(SHELL, 0x6805c450);
    return f ? (int)(signed char)f() : 50;
}

/* the class of rating k for a hitter or pitcher, or -1 when the class is not mapped */
static int class_of(int k, int pitcher) {
    if (pitcher) {
        if (k == 3) return RC_P_ARM;
        if (k == 4) return RC_P_HOLD;
        if (k == 5) return RC_P_ENDUR;
        if (k == 6) return RC_P_CONTROL;
        if (k >= 7 && k <= 13) return RC_P_PITCH;
        return -1;
    }
    if (k == 0) return RC_H_CONTACT;
    if (k == 1) return RC_H_POWER;
    if (k == 2) return RC_H_SPEED;
    if (k == 3) return RC_H_ARM;
    if (k >= 15) return RC_H_FIELD;
    return -1;
}

/* v's quantile among generated players, in 1/1000 of the table span (0 .. 1000*(RQ_POINTS-1)) */
static long quantile_of(const unsigned char *gen, int v) {
    const long span = 1000L * (RQ_POINTS - 1);
    if (v < gen[0]) return 0;
    if (v > gen[RQ_POINTS - 1]) return span;
    int lo = -1, hi = -1, i;
    for (i = 0; i < RQ_POINTS; i++)
        if (gen[i] == v) { if (lo < 0) lo = i; hi = i; }
    if (lo >= 0) {
        if (lo == hi) return 1000L * lo;
        return 1000L * lo + (long)(roll() - 1) * 1000L * (hi - lo) / 99;   /* a flat run: spread over it */
    }
    for (i = 0; i < RQ_POINTS - 1; i++)
        if (gen[i] < v && v < gen[i + 1]) return 1000L * i + 1000L * (v - gen[i]) / (gen[i + 1] - gen[i]);
    return span;
}

/* the target rating at a quantile, in 1/1000 of a point */
static long target_at(const unsigned char *tgt, long q) {
    int i = (int)(q / 1000);
    if (i >= RQ_POINTS - 1) return 1000L * tgt[RQ_POINTS - 1];
    long f = q % 1000;
    return 1000L * tgt[i] + f * (tgt[i + 1] - tgt[i]);
}

static void remap(uint8_t *rec) {
    int pitcher = 0, k;
    for (k = 7; k < 14; k++) if (rec[R_PEAK + k]) pitcher = 1;
    char before[80], after[80];
    int nb = 0, na = 0;
    if (probe > 0)
        for (k = 0; k < 23; k++) nb += _snprintf(before + nb, sizeof before - nb, "%d ", rec[R_PEAK + k]);
    for (k = 0; k < 23; k++) {
        uint8_t *peak = rec + R_PEAK + k, *cur = rec + R_CUR + k;
        int c = class_of(k, pitcher), old = *peak;
        if (c < 0 || !old || !alpha[c]) continue;
        long goal = target_at(RQ_TGT[c], quantile_of(RQ_GEN[c], old));          /* 1/1000 point */
        long want = 1000L * old + (goal - 1000L * old) * alpha[c] / 100;
        int nv = (int)(want / 1000);
        if ((roll() - 1) * 10L < want % 1000) nv++;
        if (nv < 1) nv = 1;
        if (nv > 99) nv = 99;
        if (nv == old) continue;
        *peak = (uint8_t)nv;
        if (*cur) {
            int nc = (int)((long)*cur * nv / old);
            if (nc < 1) nc = 1;
            if (nc > nv) nc = nv;
            *cur = (uint8_t)nc;
        }
        ratings_moved++;
        if (nv > old) points_up += nv - old; else points_down += old - nv;
    }
    mapped++;
    if (probe > 0) {
        probe--;
        for (k = 0; k < 23; k++) na += _snprintf(after + na, sizeof after - na, "%d ", rec[R_PEAK + k]);
        api->log("rookies probe pid=%d pitcher=%d peak before: %s after: %s", *(int16_t *)rec, pitcher, before, after);
    }
    if (mapped % 100 == 0)
        api->log("rookies: mapped=%ld ratings moved=%ld points up=%ld down=%ld", mapped, ratings_moved, points_up,
                 points_down);
}

/* FUN_680537e0 writes only ids above 99; a generator that failed leaves the id at 0 */
static void BB_THISCALL h_write(void *gen) {
    uint8_t *rec = gen ? (uint8_t *)gen + GEN_REC : NULL;
    if (map_on && rec && *(int16_t *)rec > 99) remap(rec);
    orig_write(gen);
}

BB_EXPORT int bbmod_init(const BBModAPI *a) {
    api = a;
    if (a->version != BBMOD_API_VERSION) return 1;
    char m[16], buf[200];
    a->ini_str("rookies", "map", "on", m, sizeof m);
    map_on = !lstrcmpiA(m, "on");
    probe = a->ini_int("rookies", "probe", 0);
    a->ini_str("rookies", "alpha", "100,100,100,100,100,100,100,100,100,100", buf, sizeof buf);
    char *s = buf, *e;
    for (int c = 0; c < RQ_CLASSES; c++) {
        long v = strtol(s, &e, 10);
        if (e == s || v < 0 || v > 100) return 3;
        alpha[c] = (int)v;
        s = *e == ',' ? e + 1 : e;
    }
    if (a->redirect_call(SHELL, 0x68071a34, 0x680537e0, (void *)h_write, (void **)&orig_write) < 0) return 2;
    a->log("rookies: map=%s probe=%d alpha=%d,%d,%d,%d,%d,%d,%d,%d,%d,%d registered", m, probe, alpha[0], alpha[1],
           alpha[2], alpha[3], alpha[4], alpha[5], alpha[6], alpha[7], alpha[8], alpha[9]);
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD why, LPVOID r) {
    (void)h; (void)r;
    if (why == DLL_PROCESS_DETACH && api && mapped)
        api->log("rookies final: mapped=%ld ratings moved=%ld points up=%ld down=%ld", mapped, ratings_moved,
                 points_up, points_down);
    return TRUE;
}
