/* playercard.c: click a player row in the League Statistics screen (Players, Retired Players, any period) and a player
   card opens with that player's batting and pitching lines for every period the stats file holds (last 7 days, this
   season, last season, career) and his career games by position. Works for retired players: the card reads the
   association's stats file, not the roster.

   Hook: detour on the stats screen's gadget handler FUN_6800d740 (void __thiscall (screen *, short gadget), ret 4).
   The stock handler only acts on the column headers 0x13..0x1c (sort). Body column gadgets 9..0x12 (and the widened
   columns 0x30..0x33 from bbfix [widen]) are list gadgets that keep the clicked visible row at +0x30 (or +0x2c, picked
   by the same flag test ListGrid_DrawRows 680758f0 uses for its highlight). The visible row maps to the table row
   through FUN_68043bf0(&g_GadgetMgr, screen+0x694 scroll group, row), as StatsGrid_CellCallback 6800ec00 does, and
   table cell 10 of that row carries the player id (type 0x2000, set by StatsGrid_FillRowCells 6805c930).
   The association name is (*(char ***)screen->asn)[0x25] (FUN_6803da90 builds "STATS\<name>.DAT" from it).

   bbfix.ini:  [mods] load=mods\playercard.dll      [playercard] enable=1  probe=0 (1 = log gadget state per click)
   Build:  /mnt/nvme/bbpro98/zigenv/bin/python -m ziglang cc -target x86-windows-gnu -O2 -shared -Isrc-latest
           -o playercard.dll src-latest/mods/playercard.c -lgdi32 -luser32 */
#include <windows.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../bbmod.h"

static const BBModAPI *api;
static int probe;
static void (BB_THISCALL *orig_click)(void *screen, int id);

#define MGR_VA 0x6808dd10u
#define MAP_ROW_VA 0x68043bf0u          /* ushort __thiscall (mgr, short scroll_group, short visible_row), ret 8 */
#define MAXLINES 40

/* ---------------------------------------------------------------- stats file */

typedef struct { int scope; uint16_t w[80]; int n; } Line;
typedef struct { Line bat[4], pit[4], fld; int has_bat[4], has_pit[4], has_fld; } Card;

static uint32_t rd32(const uint8_t *p) { return p[0] | p[1] << 8 | p[2] << 16 | (uint32_t)p[3] << 24; }
static uint16_t rd16(const uint8_t *p) { return (uint16_t)(p[0] | p[1] << 8); }

static uint8_t *slurp(const char *path, DWORD *len) {
    HANDLE h = CreateFileA(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, 0, OPEN_EXISTING,
                           FILE_ATTRIBUTE_NORMAL, 0);
    if (h == INVALID_HANDLE_VALUE) return 0;
    DWORD n = GetFileSize(h, 0), got = 0;
    uint8_t *b = (n && n != INVALID_FILE_SIZE && n < (64u << 20)) ? malloc(n) : 0;
    if (b && (!ReadFile(h, b, n, &got, 0) || got != n)) { free(b); b = 0; }
    CloseHandle(h);
    *len = got;
    return b;
}

/* Member numbers of the data members named `base`.dat, from the member-0 index descriptors (never by number:
   ctree.parse does the same): an index descriptor named "<base>.idx" lists trees whose u32 at def+0x4c is the index
   member; the data member is that minus one. */
static int data_member(const uint8_t *d, DWORD n, const char *base) {
    char want[16];
    snprintf(want, sizeof want, "%s.idx", base);
    size_t wl = strlen(want);
    for (DWORD i = 0; i + 20 < n;) {
        if (d[i] == 0xfa && d[i + 1] == 0xfa) {
            uint32_t tot = rd32(d + i + 2), pl = rd32(d + i + 6);
            if (tot == pl + 18 && pl > 0 && pl < 2000 && i + 18 + pl <= n) {
                const uint8_t *p = d + i + 18;
                if (rd32(d + i + 10) == 0 && pl >= 0xc0 && !memcmp(p, want, wl) && (p[wl] == ' ' || p[wl] == 0)) {
                    for (uint32_t t = 0; 0x40 + t * 0x80 + 0x64 <= pl; t++) {
                        uint32_t im = rd32(p + 0x40 + t * 0x80 + 0x4c);
                        if (im > 0 && im < 256) return (int)im - 1;
                    }
                }
                i += tot;
                continue;
            }
        }
        i++;
    }
    return -1;
}

static int load_card(const char *dat, unsigned pid, Card *c) {
    DWORD n;
    uint8_t *d = slurp(dat, &n);
    memset(c, 0, sizeof *c);
    if (!d) return -1;
    int mb = data_member(d, n, "bt"), mp = data_member(d, n, "pt"), mf = data_member(d, n, "ft");
    for (DWORD i = 0; i + 20 < n;) {
        if (d[i] == 0xfa && d[i + 1] == 0xfa) {
            uint32_t tot = rd32(d + i + 2), pl = rd32(d + i + 6);
            if (tot == pl + 18 && pl > 0 && pl < 2000 && i + 18 + pl <= n) {
                const uint8_t *p = d + i + 18;
                int mem = (int)rd32(d + i + 10);
                if (p[0] != 0xff && pl >= 6 && pl <= 160 && !(pl & 1) && rd16(p + 2) == 2 && rd16(p + 4) == pid) {
                    unsigned scope = rd16(p);
                    Line *l = 0;
                    if (scope < 4 && mem == mb) { l = &c->bat[scope]; c->has_bat[scope] = 1; }
                    else if (scope < 4 && mem == mp) { l = &c->pit[scope]; c->has_pit[scope] = 1; }
                    else if (scope == 2 && mem == mf) { l = &c->fld; c->has_fld = 1; }
                    if (l) {
                        l->scope = (int)scope;
                        l->n = (int)(pl - 6) / 2;
                        if (l->n > 80) l->n = 80;
                        for (int k = 0; k < l->n; k++) l->w[k] = rd16(p + 6 + 2 * k);
                    }
                }
                i += tot;
                continue;
            }
        }
        i++;
    }
    free(d);
    return (mb < 0 && mp < 0) ? -2 : 0;
}

/* ---------------------------------------------------------------- card text */

/* stats.py BAT order: ab h1b h2b h3b hr rbi bb so ibb hbp sh sf g r sb cs gidp; PIT = BAT (opponent line) + gf outs
   bfp w l sv cg sho qs er ir irs hld svop wp.  FLD = 9 blocks (P C 1B 2B 3B SS LF CF RF) of outs gs g po a e dp pb. */
enum { AB, H1, H2, H3, HR, RBI, BB, SO, IBB, HBP, SH, SF, G, R, SB, CS, GIDP,
       GF, OUTS, BFP, W, L, SV, CG, SHO, QS, ER };
static const char *PERIOD[4] = {"Last 7 days", "This season", "Career", "Last season"};
static const int ORDER[4] = {0, 1, 3, 2};
static const char *POS[9] = {"P", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"};

static char lines[MAXLINES][128];
static int nlines;
static char title[96];

static void add(const char *fmt, ...) {
    if (nlines >= MAXLINES) return;
    va_list a;
    va_start(a, fmt);
    vsnprintf(lines[nlines++], sizeof lines[0], fmt, a);
    va_end(a);
}

static void rate(char *out, int num, int den) {          /* .xyz, or 1.000 */
    if (den <= 0) { strcpy(out, "  ---"); return; }
    int v = (int)((num * 1000L + den / 2) / den);
    if (v >= 1000) sprintf(out, "%d.%03d", v / 1000, v % 1000);
    else sprintf(out, " .%03d", v);
}

static void build_text(const char *name, unsigned pid, const Card *c) {
    nlines = 0;
    snprintf(title, sizeof title, "%s", name);
    add("%s   (player id %u)", name, pid);
    if (c->has_fld) {
        char b[120] = "Career games by position:";
        int any = 0;
        for (int k = 0; k < 9; k++) {
            int g = c->fld.n >= k * 8 + 3 ? c->fld.w[k * 8 + 2] : 0;
            if (g) { char t[16]; snprintf(t, sizeof t, " %s %d", POS[k], g); strncat(b, t, sizeof b - strlen(b) - 1); any = 1; }
        }
        if (any) add("%s", b);
    }
    int any_bat = 0, any_pit = 0;
    for (int s = 0; s < 4; s++) { any_bat |= c->has_bat[s] && c->bat[s].w[AB] + c->bat[s].w[BB]; any_pit |= c->has_pit[s] && c->pit[s].w[OUTS]; }
    if (any_bat) {
        add("");
        add("BATTING          G    AB    R    H   2B  3B   HR  RBI   BB   SO   SB    AVG   OBP   SLG");
        for (int k = 0; k < 4; k++) {
            int s = ORDER[k];
            if (!c->has_bat[s]) continue;
            const uint16_t *w = c->bat[s].w;
            int h = w[H1] + w[H2] + w[H3] + w[HR], tb = w[H1] + 2 * w[H2] + 3 * w[H3] + 4 * w[HR];
            char avg[12], obp[12], slg[12];
            rate(avg, h, w[AB]);
            rate(obp, h + w[BB] + w[HBP], w[AB] + w[BB] + w[HBP] + w[SF]);
            rate(slg, tb, w[AB]);
            add("%-12s %5u %5u %4u %4d %4u %3u %4u %4u %4u %4u %4u  %s %s %s", PERIOD[s], w[G], w[AB], w[R], h,
                w[H2], w[H3], w[HR], w[RBI], w[BB], w[SO], w[SB], avg, obp, slg);
        }
    }
    if (any_pit) {
        add("");
        add("PITCHING         G    W    L   SV      IP     H   ER   BB   SO   HR    ERA   WHIP");
        for (int k = 0; k < 4; k++) {
            int s = ORDER[k];
            if (!c->has_pit[s] || c->pit[s].n <= ER) continue;
            const uint16_t *w = c->pit[s].w;
            int h = w[H1] + w[H2] + w[H3] + w[HR], outs = w[OUTS];
            char era[12] = "   ---", whip[12] = "   ---";
            if (outs) {
                long e = (27L * w[ER] * 100 + outs / 2) / outs, wh = (3L * (h + w[BB]) * 100 + outs / 2) / outs;
                snprintf(era, sizeof era, "%3ld.%02ld", e / 100, e % 100);
                snprintf(whip, sizeof whip, "%3ld.%02ld", wh / 100, wh % 100);
            }
            add("%-12s %5u %4u %4u %4u %5d.%d %5d %4u %4u %4u %4u %s %s", PERIOD[s], w[G], w[W], w[L], w[SV],
                outs / 3, outs % 3, h, w[ER], w[BB], w[SO], w[HR], era, whip);
        }
    }
    if (!any_bat && !any_pit) { add(""); add("No batting or pitching lines in this association's stats file."); }
    add("");
    add("Esc, Enter or a click closes this card.");
}

/* ---------------------------------------------------------------- card window */

static HWND card;
static HFONT font;

static LRESULT CALLBACK card_proc(HWND h, UINT m, WPARAM wp, LPARAM lp) {
    switch (m) {
    case WM_PAINT: {
        PAINTSTRUCT ps;
        HDC dc = BeginPaint(h, &ps);
        RECT rc;
        GetClientRect(h, &rc);
        FillRect(dc, &rc, (HBRUSH)GetStockObject(WHITE_BRUSH));
        HGDIOBJ old = SelectObject(dc, font);
        TEXTMETRICA tm;
        GetTextMetricsA(dc, &tm);
        SetBkMode(dc, TRANSPARENT);
        for (int i = 0; i < nlines; i++) {
            SetTextColor(dc, i == 0 ? RGB(0, 0, 128) : RGB(0, 0, 0));
            TextOutA(dc, 10, 8 + i * tm.tmHeight, lines[i], (int)strlen(lines[i]));
        }
        SelectObject(dc, old);
        EndPaint(h, &ps);
        return 0;
    }
    case WM_KEYDOWN:
        if (wp == VK_ESCAPE || wp == VK_RETURN) DestroyWindow(h);
        return 0;
    case WM_LBUTTONDOWN:
    case WM_RBUTTONDOWN:
        DestroyWindow(h);
        return 0;
    case WM_DESTROY:
        card = 0;
        return 0;
    }
    return DefWindowProcA(h, m, wp, lp);
}

static void show_card(void) {
    HINSTANCE hi = GetModuleHandleA(0);
    static int registered;
    if (!registered) {
        WNDCLASSA wc = {0};
        wc.lpfnWndProc = card_proc;
        wc.hInstance = hi;
        wc.hCursor = LoadCursorA(0, (LPCSTR)IDC_ARROW);
        wc.lpszClassName = "BBPlayerCard";
        if (!RegisterClassA(&wc)) { api->log("playercard: RegisterClass failed %lu", GetLastError()); return; }
        registered = 1;
    }
    if (!font) font = CreateFontA(-14, 0, 0, 0, FW_NORMAL, 0, 0, 0, ANSI_CHARSET, 0, 0, 0, FIXED_PITCH | FF_MODERN,
                                  "Courier New");
    HWND owner = GetActiveWindow();
    HDC dc = GetDC(0);
    HGDIOBJ old = SelectObject(dc, font);
    int w = 0;
    for (int i = 0; i < nlines; i++) {
        SIZE sz;
        GetTextExtentPoint32A(dc, lines[i], (int)strlen(lines[i]), &sz);
        if (sz.cx > w) w = sz.cx;
    }
    TEXTMETRICA tm;
    GetTextMetricsA(dc, &tm);
    SelectObject(dc, old);
    ReleaseDC(0, dc);
    RECT r = {0, 0, w + 20, nlines * tm.tmHeight + 16};
    DWORD st = WS_POPUP | WS_CAPTION | WS_SYSMENU | WS_BORDER;
    AdjustWindowRectEx(&r, st, FALSE, WS_EX_TOOLWINDOW);
    int cw = r.right - r.left, ch = r.bottom - r.top, x = 40, y = 40;
    RECT orc;
    if (owner && GetWindowRect(owner, &orc)) { x = orc.left + (orc.right - orc.left - cw) / 2; y = orc.top + (orc.bottom - orc.top - ch) / 2; }
    if (x < 0) x = 0;
    if (y < 0) y = 0;
    if (card) DestroyWindow(card);
    card = CreateWindowExA(WS_EX_TOOLWINDOW | WS_EX_TOPMOST, "BBPlayerCard", title, st, x, y, cw, ch, owner, 0, hi, 0);
    if (!card) { api->log("playercard: CreateWindow failed %lu", GetLastError()); return; }
    ShowWindow(card, SW_SHOW);
    UpdateWindow(card);
    SetForegroundWindow(card);
    SetFocus(card);
}

/* ---------------------------------------------------------------- click hook */

static int readable(const void *p, size_t n) { return p && !IsBadReadPtr(p, n); }

static void BB_THISCALL h_click(void *screen, int id) {
    orig_click(screen, id);
    int16_t gid = (int16_t)id;
    if (!((gid >= 9 && gid <= 0x12) || (gid >= 0x30 && gid <= 0x33)) || !readable(screen, 0x6a0)) return;
    uint8_t *mgr = (uint8_t *)api->addr("BBShell.dll", MGR_VA);
    void *map_fn = api->addr("BBShell.dll", MAP_ROW_VA);
    if (!mgr || !map_fn) return;
    uint32_t *vt = *(uint32_t **)mgr;
    uint8_t *g = ((uint8_t * (BB_THISCALL *)(void *, int)) vt[0x48 / 4])(mgr, gid);
    if (!readable(g, 0x34)) return;
    int alt = (g[0x16] & 0x10) ? (g[0x18] & 8) : (g[0x18] & 1);
    int16_t vis = *(int16_t *)(g + (alt ? 0x2c : 0x30));
    if (probe) {
        POINT pt;
        DWORD mp = GetMessagePos();
        pt.x = (int16_t)LOWORD(mp); pt.y = (int16_t)HIWORD(mp);
        api->log("playercard probe: gadget %#x alt=%d +2c=%d +30=%d f16=%02x f18=%02x msgpos=%ld,%ld", gid, !!alt,
                 *(int16_t *)(g + 0x2c), *(int16_t *)(g + 0x30), g[0x16], g[0x18], pt.x, pt.y);
    }
    if (vis < 0) return;
    int16_t group = *(int16_t *)((uint8_t *)screen + 0x694);
    uint16_t row = ((uint16_t (BB_THISCALL *)(void *, int, int))map_fn)(mgr, group, vis);
    uint8_t *tab = (uint8_t *)screen + 0x3c;
    uint16_t nrows = *(uint16_t *)tab;
    uint8_t *rows = *(uint8_t **)(tab + 4);
    if (row >= nrows || !readable(rows + row * 0xa0, 0xa0)) return;
    uint8_t *rr = rows + row * 0xa0;
    int32_t type = *(int32_t *)(rr + 10 * 8);
    unsigned pid = *(uint16_t *)(rr + 10 * 8 + 4);
    if (probe) api->log("playercard probe: vis=%d row=%u/%u type=%#x pid=%u name='%.31s'", vis, row, nrows, type, pid, (char *)rr + 0x80);
    if (type != 0x2000 || pid < 100) return;                    /* team rows carry ids < 100 */
    char name[40];
    snprintf(name, sizeof name, "%.31s", (char *)rr + 0x80);
    if (!name[0] || (uint8_t)name[0] < 32) snprintf(name, sizeof name, "Player %u", pid);
    void *asn = *(void **)((uint8_t *)screen + 8);
    char **inner = readable(asn, 4) ? *(char ***)asn : 0;
    const char *an = readable(inner, 0x98) ? inner[0x25] : 0;
    if (!readable(an, 1) || !an[0]) { api->log("playercard: association name not found"); return; }
    char exe[MAX_PATH], path[MAX_PATH + 64];
    GetModuleFileNameA(0, exe, MAX_PATH);
    char *sl = strrchr(exe, '\\');
    if (sl) sl[1] = 0; else exe[0] = 0;
    snprintf(path, sizeof path, "%sSTATS\\%.40s.DAT", exe, an);
    static Card c;
    int rc = load_card(path, pid, &c);
    api->log("playercard: pid %u '%s' from %s -> rc %d bat %d%d%d%d pit %d%d%d%d", pid, name, path, rc, c.has_bat[0],
             c.has_bat[1], c.has_bat[2], c.has_bat[3], c.has_pit[0], c.has_pit[1], c.has_pit[2], c.has_pit[3]);
    if (rc == -1) { nlines = 0; snprintf(title, sizeof title, "%s", name); add("Could not read %s", path); }
    else build_text(name, pid, &c);
    show_card();
}

BB_EXPORT int bbmod_init(const BBModAPI *a) {
    api = a;
    if (a->version != BBMOD_API_VERSION) return 1;
    if (!a->ini_int("playercard", "enable", 1)) { a->log("playercard: disabled"); return 0; }
    probe = a->ini_int("playercard", "probe", 0);
    static const uint8_t prolog[7] = {0x56, 0x57, 0x66, 0x8b, 0x74, 0x24, 0x0c};   /* push esi / push edi / mov si,[esp+0c] */
    if (a->detour("BBShell.dll", 0x6800d740, prolog, 7, (void *)h_click, (void **)&orig_click) < 0) return 2;
    a->log("playercard: registered (probe=%d)", probe);
    return 0;
}
