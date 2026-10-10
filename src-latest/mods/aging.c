/* aging.c: veterans decline and retire. Two stock rules make a career league old (MLBPA97: mean roster age 28.5 in
   1997, 31.1 by 2007, nobody under 36 ever retired, a 30-year-old lost about 2 rating points by 38):
   - Aging (FUN_68055630 -> FUN_68056210, AGEPLYR.DAT) moves only the CURRENT ratings, capped at the PEAK ratings, and
     spring training (FUN_68056320, SPRPLYR.DAT) pulls current back toward peak every March. Peak never falls, so a
     decline is undone each spring.
   - Retirement (FUN_68055670, bool __thiscall (Player **self, Date *today, char team), ret 8) happens only past 35
     (roll 1..100 below 10*age - 350) and ignores ability.

   This mod wraps the callers (redirect_call), for rostered players and the free-agent list alike:
   - aging, 6806cb9a (rosters) and 6807184e (free agents) call FUN_68055630 (void __thiscall (self, Date*), ret 4):
     after the stock aging, a player of age >= the first [aging] decline age loses decline[age] tenths of a percent of
     each nonzero peak rating, scaled by the rating class weight; current is capped at the new peak. Fractions are
     rounded up with the game's own roll so small peaks still decline on average.
   - retirement, 6806cc15 (rosters) and 680718a5 (free agents) call FUN_68055670: chance in percent = base[age] *
     ability factor (* fa_mult for free agents), capped at 99, rolled with the game's 1..100 roll (FUN_6805c450) so the
     seed mod still governs it. A player marked 9999 at +0x80 (the game's forced retirement) goes to the stock code. A
     retirement writes exactly what the stock code writes.

   Runtime player record (not the PYR layout): +0x1c birth date (FUN_680490b0(birth, today) gives the age), +0x20
   service years (negated on retirement), +0x35 the 23 peak ratings, +0x4c the 23 current ratings, +0x80 s16, +0x8b
   dirty, +0x8c retiring team. Rating index: 0 contact, 1 power, 2 speed, 3 arm, 4 hold runners, 5 endurance,
   6 control, 7..13 pitches (all zero for position players), 14..22 fielding P..RF.
   Ability: pitchers (best pitch + second pitch + control) / 3, hitters (2 contact + 2 power + speed + best non-P
   fielding) / 6.

   bbfix.ini:  [mods] load=mods\aging.dll
               [aging] decline=on|off   retire=curve|pass   fa_mult=180 (percent)   probe=0 (log N records' bytes)
                       drop=31:10,32:15,...        age:tenths of a percent of peak lost per season
                       weight=100,90,120,80,20,90,50,90   percent per class: contact, power, speed, arm, hold,
                                                          endurance, control, pitches and fielding
                       base=29:2,30:4,...          retirement age:percent, ages past the last entry use the last value
                       q=70:35,62:60,52:100,44:160,0:220   ability floor:percent factor, highest floor first */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include "../bbmod.h"

#define MAXAGE 60
#define SHELL "BBShell.dll"

static const BBModAPI *api;
static int decline_on, retire_curve, fa_mult, probe;
static int drop_t[MAXAGE + 1], base_pct[MAXAGE + 1], weight[8];
static int q_floor[8], q_factor[8], nq;
static long seen[2], retired[2], by_age[2][MAXAGE + 1], kept_age[2][MAXAGE + 1];
static long aged[2], declined[2], peak_lost[2];
static void (BB_THISCALL *orig_age_roster)(void *self, uint32_t *today);
static void (BB_THISCALL *orig_age_fa)(void *self, uint32_t *today);
static uint32_t (BB_THISCALL *orig_ret_roster)(void *self, uint32_t *today, uint32_t team);
static uint32_t (BB_THISCALL *orig_ret_fa)(void *self, uint32_t *today, uint32_t team);

typedef int (__cdecl *age_fn)(uint32_t *birth, uint32_t *today);
typedef int (__cdecl *roll_fn)(void);

static int age_of(uint8_t *rec, uint32_t *today) {
    age_fn f = (age_fn)api->addr(SHELL, 0x680490b0);
    return f ? (int16_t)f((uint32_t *)(rec + 0x1c), today) : -1;
}

static int roll(void) {
    roll_fn f = (roll_fn)api->addr(SHELL, 0x6805c450);
    return f ? (int)(signed char)f() : 100;
}

static int clamp_age(int a) { return a < 0 ? 0 : a > MAXAGE ? MAXAGE : a; }

static int ability(const uint8_t *cur) {
    int a = 0, b = 0, k;
    for (k = 7; k < 14; k++) {
        if (cur[k] > a) { b = a; a = cur[k]; }
        else if (cur[k] > b) b = cur[k];
    }
    if (a) return (a + b + cur[6]) / 3;
    int f = 0;
    for (k = 15; k < 23; k++) if (cur[k] > f) f = cur[k];
    return (2 * cur[0] + 2 * cur[1] + cur[2] + f) / 6;
}

static void report(const char *when) {
    char line[900];
    for (int w = 0; w < 2; w++) {
        api->log("aging %s %s: aged=%ld declined=%ld peak points lost=%ld", when, w ? "fa" : "roster", aged[w],
                 declined[w], peak_lost[w]);
        int n = _snprintf(line, sizeof line, "retire %s %s: seen=%ld retired=%ld by age (retired/seen)", when,
                          w ? "fa" : "roster", seen[w], retired[w]);
        for (int a = 18; a <= MAXAGE && n < (int)sizeof line - 24; a++)
            if (by_age[w][a] || kept_age[w][a])
                n += _snprintf(line + n, sizeof line - n, " %d:%ld/%ld", a, by_age[w][a], by_age[w][a] + kept_age[w][a]);
        api->log("%s", line);
    }
}

static void decline(void *self, uint32_t *today, int fa) {
    uint8_t *rec = *(uint8_t **)self;
    aged[fa]++;
    if (!decline_on || !rec) return;
    int t = drop_t[clamp_age(age_of(rec, today))];
    if (t <= 0) return;
    declined[fa]++;
    for (int k = 0; k < 23; k++) {
        uint8_t *peak = rec + 0x35 + k, *cur = rec + 0x4c + k;
        if (!*peak) continue;
        long num = (long)*peak * t * weight[k < 7 ? k : 7];        /* peak * tenths * percent, in 1/100000 */
        int dec = (int)(num / 100000);
        if ((roll() - 1) * 1000L < num % 100000) dec++;
        if (dec >= *peak) dec = *peak - 1;
        *peak = (uint8_t)(*peak - dec);
        if (*cur > *peak) *cur = *peak;
        peak_lost[fa] += dec;
    }
    rec[0x8b] = 1;
}

static void BB_THISCALL h_age_roster(void *self, uint32_t *today) { orig_age_roster(self, today); decline(self, today, 0); }
static void BB_THISCALL h_age_fa(void *self, uint32_t *today) { orig_age_fa(self, today); decline(self, today, 1); }

static uint32_t retire(void *self, uint32_t *today, uint32_t team, int fa) {
    uint32_t (BB_THISCALL *orig)(void *, uint32_t *, uint32_t) = fa ? orig_ret_fa : orig_ret_roster;
    uint8_t *rec = *(uint8_t **)self;
    if (!retire_curve || !rec || *(int16_t *)(rec + 0x80) == 9999) return orig(self, today, team);
    int age = age_of(rec, today), a = clamp_age(age), q = ability(rec + 0x4c), f = 100, i;
    for (i = 0; i < nq; i++) if (q >= q_floor[i]) { f = q_factor[i]; break; }
    long c = (long)base_pct[a] * f / 100;
    if (fa) c = c * fa_mult / 100;
    if (c > 99) c = 99;
    int out = age >= 0 && c > 0 && roll() <= c;
    if (probe > 0) {
        probe--;
        char hex[3 * 0x90 + 1];
        for (int k = 0; k < 0x90; k++) _snprintf(hex + 3 * k, 4, "%02x ", rec[k]);
        api->log("retire probe fa=%d age=%d q=%d chance=%ld out=%d rec=%s", fa, age, q, c, out, hex);
    }
    seen[fa]++;
    if (out) {
        rec[0x20] = (uint8_t)-(signed char)rec[0x20];
        rec[0x8b] = 1;
        rec[0x8c] = (uint8_t)team;
        retired[fa]++; by_age[fa][a]++;
    } else kept_age[fa][a]++;
    if ((seen[0] + seen[1]) % 500 == 0) report("progress");
    return (uint32_t)out;
}

static uint32_t BB_THISCALL h_ret_roster(void *self, uint32_t *today, uint32_t team) { return retire(self, today, team, 0); }
static uint32_t BB_THISCALL h_ret_fa(void *self, uint32_t *today, uint32_t team) { return retire(self, today, team, 1); }

/* "29:2,30:4" style pairs into keys[]/vals[]; returns the count */
static int pairs(const char *s, int *keys, int *vals, int max) {
    int n = 0;
    while (*s && n < max) {
        char *e;
        long k = strtol(s, &e, 10);
        if (e == s || *e != ':') break;
        s = e + 1;
        long v = strtol(s, &e, 10);
        if (e == s) break;
        keys[n] = (int)k; vals[n] = (int)v; n++;
        s = *e == ',' ? e + 1 : e;
    }
    return n;
}

/* an age:value list into table[0..MAXAGE]: 0 below the first age, the last value past the last age */
static int by_age_table(const char *key, const char *def, int *table) {
    char buf[400];
    int ka[MAXAGE + 1], va[MAXAGE + 1];
    api->ini_str("aging", key, def, buf, sizeof buf);
    int n = pairs(buf, ka, va, MAXAGE + 1), last = 0, j = 0;
    if (!n) return 0;
    for (int age = 0; age <= MAXAGE; age++) {
        while (j < n && ka[j] <= age) last = va[j++];
        table[age] = age < ka[0] ? 0 : last;
    }
    return n;
}

BB_EXPORT int bbmod_init(const BBModAPI *a) {
    api = a;
    if (a->version != BBMOD_API_VERSION) return 1;
    char d[16], r[16], buf[400];
    a->ini_str("aging", "decline", "on", d, sizeof d);
    a->ini_str("aging", "retire", "curve", r, sizeof r);
    decline_on = !lstrcmpiA(d, "on");
    retire_curve = !lstrcmpiA(r, "curve");
    fa_mult = a->ini_int("aging", "fa_mult", 180);
    probe = a->ini_int("aging", "probe", 0);
    if (!by_age_table("drop", "31:10,32:15,33:20,34:25,35:30,36:35,37:40,38:45,39:50,40:55,41:60", drop_t)) return 3;
    if (!by_age_table("base", "29:2,30:4,31:6,32:9,33:13,34:18,35:24,36:31,37:40,38:50,39:60,40:70,41:80,42:90",
                      base_pct)) return 3;
    a->ini_str("aging", "weight", "100,90,120,80,20,90,50,90", buf, sizeof buf);
    char *s = buf, *e;
    for (int k = 0; k < 8; k++) {
        weight[k] = (int)strtol(s, &e, 10);
        if (e == s) return 3;
        s = *e == ',' ? e + 1 : e;
    }
    a->ini_str("aging", "q", "70:35,62:60,52:100,44:160,0:220", buf, sizeof buf);
    nq = pairs(buf, q_floor, q_factor, 8);
    if (!nq) return 3;
    if (a->redirect_call(SHELL, 0x6806cb9a, 0x68055630, (void *)h_age_roster, (void **)&orig_age_roster) < 0 ||
        a->redirect_call(SHELL, 0x6807184e, 0x68055630, (void *)h_age_fa, (void **)&orig_age_fa) < 0 ||
        a->redirect_call(SHELL, 0x6806cc15, 0x68055670, (void *)h_ret_roster, (void **)&orig_ret_roster) < 0 ||
        a->redirect_call(SHELL, 0x680718a5, 0x68055670, (void *)h_ret_fa, (void **)&orig_ret_fa) < 0) return 2;
    a->log("aging: decline=%s retire=%s fa_mult=%d probe=%d drop[33]=%d drop[38]=%d base[30]=%d base[35]=%d "
           "base[40]=%d q-bands=%d registered", d, r, fa_mult, probe, drop_t[33], drop_t[38], base_pct[30],
           base_pct[35], base_pct[40], nq);
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD why, LPVOID r) {
    (void)h; (void)r;
    if (why == DLL_PROCESS_DETACH && api) report("final");
    return TRUE;
}
