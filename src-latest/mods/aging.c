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
                       base=29:1,30:3,...          retirement age:percent, ages past the last entry use the last value
                       q=70:35,62:60,52:100,44:160,0:220   ability floor:percent factor, highest floor first

   v2 (decline only; retirement is unchanged):
   - Per-group curves. drop_bat (contact, power) peaks late, drop_run (speed, arm, fielding) early, drop_pit (hold,
     endurance, control, pitches) in between. drop_bat and drop_run default to drop; drop_pit defaults to
     29:8,30:15,...,41:85 (tenths of a percent).
   - rel_mult=130 (percent): a pitcher whose current endurance is below rel_end=40 (a reliever) declines this much
     faster.
   - var=50 (percent): each player's decline this season is scaled by a factor rolled once, 100-var .. 100+var, so
     careers diverge instead of every 34-year-old losing the same points.
   - Development focus (mods\focus.txt, written by the news bridge, re-read when it changes): lines
     "pid birth kind", birth the record's +0x1c date serial, kind contact|power|speed|control|stuff|defense. A
     focused player gains focus_gain=2 on each nonzero peak of that class (capped at 99) and loses none there this
     season; every other nonzero rating declines focus_cost=10 more tenths of a percent. Keyed by pid and birth, so
     copies of one association share a focus. */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../bbmod.h"

#define MAXAGE 60
#define SHELL "BBShell.dll"

static const BBModAPI *api;
static int decline_on, retire_curve, fa_mult, probe;
static int drop_t[MAXAGE + 1], base_pct[MAXAGE + 1], weight[8];
static int drop_grp[3][MAXAGE + 1];             /* 0 bat, 1 run, 2 pit */
static int rel_mult, rel_end, var_pct, focus_gain, focus_cost;
static long varied[2], relief[2], focused[2], focus_pts[2];

#define MAXFOCUS 2000
enum { F_CONTACT = 1, F_POWER, F_SPEED, F_CONTROL, F_STUFF, F_DEFENSE };
static struct { int16_t pid; uint32_t birth; uint8_t kind; } focus_tab[MAXFOCUS];
static int nfocus;
static FILETIME focus_mtime;
static DWORD focus_checked;
static const char *const FOCUS_NAMES[] = {"", "contact", "power", "speed", "control", "stuff", "defense"};
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
        api->log("aging %s %s: aged=%ld declined=%ld peak points lost=%ld relievers=%ld varied=%ld focused=%ld "
                 "focus points=%ld", when, w ? "fa" : "roster", aged[w], declined[w], peak_lost[w], relief[w],
                 varied[w], focused[w], focus_pts[w]);
        int n = _snprintf(line, sizeof line, "retire %s %s: seen=%ld retired=%ld by age (retired/seen)", when,
                          w ? "fa" : "roster", seen[w], retired[w]);
        for (int a = 18; a <= MAXAGE && n < (int)sizeof line - 24; a++)
            if (by_age[w][a] || kept_age[w][a])
                n += _snprintf(line + n, sizeof line - n, " %d:%ld/%ld", a, by_age[w][a], by_age[w][a] + kept_age[w][a]);
        api->log("%s", line);
    }
}

static int group_of(int k) { return k <= 1 ? 0 : (k == 2 || k == 3 || k >= 14) ? 1 : 2; }

/* the rating class a focus kind covers */
static int in_focus(int kind, int k) {
    switch (kind) {
    case F_CONTACT: return k == 0;
    case F_POWER: return k == 1;
    case F_SPEED: return k == 2;
    case F_CONTROL: return k == 6;
    case F_STUFF: return k >= 7 && k <= 13;
    case F_DEFENSE: return k == 3 || k >= 14;
    }
    return 0;
}

/* re-read mods\focus.txt when its write time changes (checked at most every 2 s) */
static void load_focus(void) {
    DWORD now = GetTickCount();
    if (focus_checked && now - focus_checked < 2000) return;
    focus_checked = now ? now : 1;
    WIN32_FILE_ATTRIBUTE_DATA fa;
    if (!GetFileAttributesExA("mods\\focus.txt", GetFileExInfoStandard, &fa)) {
        if (nfocus) api->log("aging focus: file gone, 0 players");
        nfocus = 0; focus_mtime.dwLowDateTime = focus_mtime.dwHighDateTime = 0;
        return;
    }
    if (!CompareFileTime(&fa.ftLastWriteTime, &focus_mtime)) return;
    focus_mtime = fa.ftLastWriteTime;
    FILE *f = fopen("mods\\focus.txt", "r");
    nfocus = 0;
    if (!f) return;
    char line[128], kind[16];
    while (nfocus < MAXFOCUS && fgets(line, sizeof line, f)) {
        int pid; unsigned long birth;
        if (sscanf(line, "%d %lu %15s", &pid, &birth, kind) != 3 || pid < 100 || pid > 32767) continue;
        for (int k = 1; k <= F_DEFENSE; k++)
            if (!lstrcmpiA(kind, FOCUS_NAMES[k])) {
                focus_tab[nfocus].pid = (int16_t)pid; focus_tab[nfocus].birth = (uint32_t)birth;
                focus_tab[nfocus].kind = (uint8_t)k; nfocus++;
                break;
            }
    }
    fclose(f);
    api->log("aging focus: %d players", nfocus);
}

static int focus_of(const uint8_t *rec) {
    int16_t pid = *(const int16_t *)rec;
    uint32_t birth = *(const uint32_t *)(rec + 0x1c);
    for (int i = 0; i < nfocus; i++)
        if (focus_tab[i].pid == pid && focus_tab[i].birth == birth) return focus_tab[i].kind;
    return 0;
}

static void decline(void *self, uint32_t *today, int fa) {
    uint8_t *rec = *(uint8_t **)self;
    aged[fa]++;
    if (!decline_on || !rec) return;
    load_focus();
    int a = clamp_age(age_of(rec, today)), fk = nfocus ? focus_of(rec) : 0;
    int pitcher = 0, k;
    for (k = 7; k < 14; k++) if (rec[0x4c + k]) pitcher = 1;
    long scale = 100;                                              /* percent */
    if (pitcher && rec[0x4c + 5] < rel_end) { scale = scale * rel_mult / 100; relief[fa]++; }
    if (var_pct) { scale = scale * (100 + (long)var_pct * (2 * roll() - 101) / 100) / 100; varied[fa]++; }
    if (scale < 0) scale = 0;
    int any = 0;
    for (k = 0; k < 23; k++) {
        uint8_t *peak = rec + 0x35 + k, *cur = rec + 0x4c + k;
        if (!*peak) continue;
        if (fk && in_focus(fk, k)) {
            int up = *peak + focus_gain > 99 ? 99 - *peak : focus_gain;
            if (up > 0) { *peak = (uint8_t)(*peak + up); focus_pts[fa] += up; any = 1; }
            continue;
        }
        long t = drop_grp[group_of(k)][a] * scale / 100 + (fk ? focus_cost : 0);
        if (t <= 0) continue;
        long num = (long)*peak * t * weight[k < 7 ? k : 7];        /* peak * tenths * percent, in 1/100000 */
        int dec = (int)(num / 100000);
        if ((roll() - 1) * 1000L < num % 100000) dec++;
        if (dec >= *peak) dec = *peak - 1;
        if (dec <= 0) continue;
        *peak = (uint8_t)(*peak - dec);
        if (*cur > *peak) *cur = *peak;
        peak_lost[fa] += dec;
        any = 1;
    }
    if (fk) focused[fa]++;
    if (any) { declined[fa]++; rec[0x8b] = 1; }
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
    static const char *const GRP[3] = {"drop_bat", "drop_run", "drop_pit"};
    /* drop_pit's default is the curve the 2009-2018 roll passed with (next10 v3j); bat and run default to drop. */
    static const char *const GRP_DEF[3] = {"", "",
        "29:8,30:15,31:22,32:30,33:38,34:45,35:52,36:58,37:64,38:70,39:75,40:80,41:85"};
    for (int g = 0; g < 3; g++)
        if (!by_age_table(GRP[g], GRP_DEF[g], drop_grp[g])) memcpy(drop_grp[g], drop_t, sizeof drop_t);
    rel_mult = a->ini_int("aging", "rel_mult", 130);
    rel_end = a->ini_int("aging", "rel_end", 40);
    var_pct = a->ini_int("aging", "var", 50);
    if (var_pct < 0) var_pct = 0;
    if (var_pct > 100) var_pct = 100;
    focus_gain = a->ini_int("aging", "focus_gain", 2);
    focus_cost = a->ini_int("aging", "focus_cost", 10);
    if (!by_age_table("base", "29:1,30:3,31:5,32:8,33:12,34:16,35:22,36:30,37:39,38:49,39:60,40:70,41:80,42:90",
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
    a->log("aging: decline=%s retire=%s fa_mult=%d probe=%d drop[33]=%d drop[38]=%d bat[33]=%d run[33]=%d pit[33]=%d "
           "rel_mult=%d rel_end=%d var=%d focus_gain=%d focus_cost=%d base[30]=%d base[35]=%d base[40]=%d q-bands=%d "
           "registered", d, r, fa_mult, probe, drop_t[33], drop_t[38], drop_grp[0][33], drop_grp[1][33],
           drop_grp[2][33], rel_mult, rel_end, var_pct, focus_gain, focus_cost, base_pct[30], base_pct[35],
           base_pct[40], nq);
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD why, LPVOID r) {
    (void)h; (void)r;
    if (why == DLL_PROCESS_DETACH && api) report("final");
    return TRUE;
}
