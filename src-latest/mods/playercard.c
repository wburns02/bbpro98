/* playercard.c: click a player row in the League Statistics screen (Players, Retired Players, any period) and a player
   card opens with that player's batting and pitching lines for every period the stats file holds (last 7 days, this
   season, last season, career) and his career games by position. Works for retired players: the card reads the
   association's stats file, not the roster.

   Hook: detour on the gadget manager's event handler FUN_68043d20 (ushort __thiscall (mgr, x, y, buttons, code, p5),
   ret 0x14), which sees every input tick. The body column gadgets 9..0x12 (and the widened columns 0x30..0x33 from
   bbfix [widen]) carry flag 0x20, so the game's own hit test (flags & 0x60) never routes a click to them; the mod
   hit-tests them itself on the left button's rising edge while the stats screen is up (its callback 6800d460 is at
   mgr+0xc0). Gadget rects are shorts at +0xe x, +0x10 y, +0x12 w, +0x14 h; rows are 11 pixels high. The visible row
   maps to the table row through FUN_68043bf0(&g_GadgetMgr, screen+0x694 scroll group, row), as
   StatsGrid_CellCallback 6800ec00 does. StatsGrid_FillRowCells 6805c930 fills the stat cells and then writes the
   player id (type 0x2000) into the cell after them: cell 10 stock, cell 14 when bbfix [widen] has patched that
   "push 10" at 6805cb0b to 14, so the mod reads the cell index from that instruction.
   The association name is (*(char ***)screen->asn)[0x25] (FUN_6803da90 builds "STATS\<name>.DAT" from it).

   bbfix.ini:  [mods] load=mods\playercard.dll      [playercard] enable=1  probe=0 (1 = log each click and its row)
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

#define MGR_VA 0x6808dd10u
#define MAP_ROW_VA 0x68043bf0u          /* ushort __thiscall (mgr, short scroll_group, short visible_row), ret 8 */
#define STATS_CB_VA 0x6800d460u         /* the stats screen's gadget callback (mgr+0xc0 while it is up) */
#define STATS_SCREEN_VA 0x6808d818u     /* the stats screen object */
#define ID_PUSH_VA 0x6805cb0bu        /* push <id cell> (6a 0a stock, 6a 0e under bbfix [widen]) */
#define ROW_H 11                        /* list row height in pixels (fixed font of the stats grid) */
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

/* A left click (button edge) inside a body column of the stats screen: the visible row under it, else -1. */
static int hit_row(uint8_t *mgr, int x, int y, int *gid_out) {
    uint32_t *vt = *(uint32_t **)mgr;
    for (int id = 9; id <= 0x33; id++) {
        if (id == 0x13) id = 0x30;
        uint8_t *g = ((uint8_t * (BB_THISCALL *)(void *, int)) vt[0x48 / 4])(mgr, id);
        /* body columns carry flag 0x20 (input-inert, so the game's hit test, flags & 0x60, skips them); 0x40 marks a
           hidden gadget, which must not take the click */
        if (!readable(g, 0x34) || (*(uint16_t *)(g + 0xc)) != id || (*(uint16_t *)(g + 0x18) & 0x40)) continue;
        int gx = *(int16_t *)(g + 0xe), gy = *(int16_t *)(g + 0x10), gw = *(int16_t *)(g + 0x12), gh = *(int16_t *)(g + 0x14);
        if (x < gx || x >= gx + gw || y < gy || y >= gy + gh) continue;
        *gid_out = id;
        return (y - gy) / ROW_H;
    }
    return -1;
}

static void open_card(void *screen, int gid, int vis) {
    uint8_t *mgr = (uint8_t *)api->addr("BBShell.dll", MGR_VA);
    void *map_fn = api->addr("BBShell.dll", MAP_ROW_VA);
    if (!mgr || !map_fn || !readable(screen, 0x6a0)) return;
    int16_t group = *(int16_t *)((uint8_t *)screen + 0x694);
    uint16_t row = ((uint16_t (BB_THISCALL *)(void *, int, int))map_fn)(mgr, group, vis);
    uint8_t *tab = (uint8_t *)screen + 0x3c;
    uint16_t nrows = *(uint16_t *)tab;
    uint8_t *rows = *(uint8_t **)(tab + 4);
    if (row >= nrows || !readable(rows + row * 0xa0, 0xa0)) return;
    uint8_t *rr = rows + row * 0xa0;
    const uint8_t *push = (const uint8_t *)api->addr("BBShell.dll", ID_PUSH_VA);
    if (!readable(push, 2) || push[0] != 0x6a || (push[1] != 10 && push[1] != 14)) {
        api->log("playercard: id cell push at 6805cb0b not recognised");
        return;
    }
    int cell = push[1];
    int32_t type = *(int32_t *)(rr + cell * 8);
    unsigned pid = *(uint16_t *)(rr + cell * 8 + 4);
    if (probe) api->log("playercard probe: gadget %#x vis=%d row=%u/%u cell %d type=%#x pid=%u name='%.31s'", gid, vis, row,
                        nrows, cell, type, pid, (char *)rr + 0x80);
    if (type != 0x2000 || pid < 100) return;                   /* the id cell; ids below 100 are teams */
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

static uint16_t (BB_THISCALL *orig_event)(void *mgr, int x, int y, int buttons, int code, int p5);

/* The gadget manager's event handler, called for every input tick with the mouse position (client coordinates of
   the screen) and the button state (bit 0 = left). Body list gadgets are not hit-tested by the game, so the click is
   taken here: on the left button going down, on the stats screen (its callback is installed at mgr+0xc0). */
static uint16_t BB_THISCALL h_event(void *mgr, int x, int y, int buttons, int code, int p5) {
    static int was_down;
    uint16_t r = orig_event(mgr, x, y, buttons, code, p5);
    int down = buttons & 1;
    if (down && !was_down && mgr == api->addr("BBShell.dll", MGR_VA) &&
        *(void **)((uint8_t *)mgr + 0xc0) == api->addr("BBShell.dll", STATS_CB_VA)) {
        void *screen = *(void **)api->addr("BBShell.dll", STATS_SCREEN_VA);
        int gid = 0, vis = hit_row((uint8_t *)mgr, (int16_t)x, (int16_t)y, &gid);
        if (probe) api->log("playercard probe: click x=%d y=%d gadget %#x vis=%d", (int16_t)x, (int16_t)y, gid, vis);
        if (vis >= 0 && screen) open_card(screen, gid, vis);
    }
    was_down = down;
    return r;
}

BB_EXPORT int bbmod_init(const BBModAPI *a) {
    api = a;
    if (a->version != BBMOD_API_VERSION) return 1;
    if (!a->ini_int("playercard", "enable", 1)) { a->log("playercard: disabled"); return 0; }
    probe = a->ini_int("playercard", "probe", 0);
    static const uint8_t ev_prolog[5] = {0x83, 0xec, 0x04, 0x53, 0x56};               /* sub esp,4 / push ebx / push esi */
    if (a->detour("BBShell.dll", 0x68043d20, ev_prolog, 5, (void *)h_event, (void **)&orig_event) < 0) return 3;
    a->log("playercard: registered (probe=%d)", probe);
    return 0;
}
