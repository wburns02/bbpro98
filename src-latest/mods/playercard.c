/* playercard.c: click a player row in the League Statistics screen (Players, Retired Players, any period) and a player
   card opens with that player's batting and pitching lines for every period the stats file holds (last 7 days, this
   season, last season, career) and his career games by position. Works for retired players: the card reads the
   association's stats file, not the roster.

   Hook: detour on the gadget manager's event handler FUN_68043d20 (ushort __thiscall (mgr, x, y, buttons, code, p5),
   ret 0x14), which sees every input tick. The body column gadgets 9..0x12 (and the widened columns 0x30..0x33 from
   bbfix [widen]) carry flag 0x20, so the game's own hit test (flags & 0x60) never routes a click to them; the mod
   hit-tests them itself on the left button's rising edge while a stats screen is up. The callback at mgr+0xc0 names
   the screen (SCREENS: League 6800d460, Team 68036ec0). Gadget rects are shorts at +0xe x, +0x10 y, +0x12 w, +0x14 h;
   rows are 11 pixels high. The visible row maps to the table row through FUN_68043bf0(&g_GadgetMgr, screen's scroll
   group, row), as StatsGrid_CellCallback 6800ec00 does. StatsGrid_FillRowCells 6805c930 fills the stat cells and then
   writes the player id (type 0x2000) into the cell after them: cell 10 stock, cell 14 when bbfix [widen] has patched
   that "push 10" at 6805cb0b to 14, so the mod reads the cell index from that instruction. Both screens fill their
   rows through 6805c930, so the same cell applies to both.
   The association name is (*(char ***)(screen+8))[0x25] (FUN_6803da90 builds "STATS\<name>.DAT" from it); both
   screens store the same singleton (FUN_68046580) at +8.
   When modmenu.dll is loaded (GetModuleHandleA), the click opens /news/card/<assn>/p/<pid> in its News reader through
   its export mm_open_page; the built-in card above opens when modmenu is absent or the bridge does not answer.
   The screen objects, offsets and addresses are in bbcard.md (Round 2).

   bbfix.ini:  [mods] load=mods\playercard.dll      [playercard] enable=1  probe=0 (1 = log each left click: the
   callback at mgr+0xc0, both screen objects, the hit gadget and row, and the outcome)
   Build:  /mnt/nvme/bbpro98/zigenv/bin/python -m ziglang cc -target x86-windows-gnu -O2 -shared -Isrc-latest
           -o playercard.dll src-latest/mods/playercard.c -lgdi32 -luser32 */
#include <windows.h>
#include <ctype.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../bbmod.h"

static const BBModAPI *api;
static int probe;

#define MGR_VA 0x6808dd10u
#define MAP_ROW_VA 0x68043bf0u          /* ushort __thiscall (mgr, short scroll_group, short visible_row), ret 8 */
#define ID_PUSH_VA 0x6805cb0bu        /* push <id cell> (6a 0a stock, 6a 0e under bbfix [widen]) */
#define CUR_SCREEN_VA 0x6808da50u       /* the screen id FUN_68038ef0 last installed (probe only) */
#define TEAM_OBJ_VA 0x6808da24u         /* the Team Statistics object pointer (probe only) */
#define ROW_H 11                        /* list row height in pixels (fixed font of the stats grid) */
#define MAXLINES 40

/* The two stats screens, told apart by the callback at mgr+0xc0 (FUN_68038ef0 writes it; nothing clears it when the
   screen closes, so the probe logs the screen id global to show a stale one).
   League: ctor 6800ccc0, object pointer in 0x6808d818, id 7 at +0 (6800cd5a), asn at +8 (6800cd73), row table at +0x3c,
   scroll group (short) at +0x694, body gadgets 9..0x12 and the widened 0x30..0x33 (ext).
   Team: ctor 680367e0, object pointer in 0x6808da24, id 0x14 at +0, asn at +8 (680368ba), row table at +0x14, scroll
   group (short) at +0xfa (zeroed in the ctor at 680369c6), body gadgets 9..0x12 (FUN_68036dc0's init loop), object
   allocated as 0x5f4 bytes (68036212). Row table layout (count u16 at +0, rows at +4, 0xa0 a row, 8-byte cells)
   is the one FUN_68060740 reads. */
typedef struct {
    const char *name;
    uint32_t cb_va;      /* gadget callback at mgr+0xc0 while the screen is up */
    uint32_t obj_va;     /* pointer global holding the screen object */
    int table_off;       /* row table inside the object */
    int group_off;       /* scroll group, a short */
    int size;            /* bytes of the object the mod reads */
    int ext;             /* body gadgets 0x30..0x33 also belong to the screen */
} StatsScreen;

static const StatsScreen SCREENS[2] = {
    {"League", 0x6800d460u, 0x6808d818u, 0x3c, 0x694, 0x6a0, 1},
    {"Team",   0x68036ec0u, 0x6808da24u, 0x14, 0xfa,  0x5f4, 0},
};

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
    int mb = data_member(d, n, "bt"), mp = data_member(d, n, "pt"), mf = data_member(d, n, "ft");   /* -1 when absent */
    for (DWORD i = 0; i + 20 < n;) {
        if (d[i] == 0xfa && d[i + 1] == 0xfa) {
            uint32_t tot = rd32(d + i + 2), pl = rd32(d + i + 6);
            if (tot == pl + 18 && pl > 0 && pl < 2000 && i + 18 + pl <= n) {
                const uint8_t *p = d + i + 18;
                int mem = (int)rd32(d + i + 10);
                if (p[0] != 0xff && pl >= 6 && pl <= 160 && !(pl & 1) && rd16(p + 2) == 2 && rd16(p + 4) == pid) {
                    unsigned scope = rd16(p);
                    Line *l = 0;
                    if (mb >= 0 && scope < 4 && mem == mb) { l = &c->bat[scope]; c->has_bat[scope] = 1; }
                    else if (mp >= 0 && scope < 4 && mem == mp) { l = &c->pit[scope]; c->has_pit[scope] = 1; }
                    else if (mf >= 0 && scope == 2 && mem == mf) { l = &c->fld; c->has_fld = 1; }
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

/* A left click (button edge) inside a body column of a stats screen: the visible row under it, else -1. The body is
   gadgets 9..0x12, and 0x30..0x33 too when ext (League under bbfix [widen]). */
static int hit_row(uint8_t *mgr, int x, int y, int ext, int *gid_out, int *gy_out) {
    uint32_t *vt = *(uint32_t **)mgr;
    for (int id = 9; id <= (ext ? 0x33 : 0x12); id++) {
        if (id == 0x13) id = 0x30;
        uint8_t *g = ((uint8_t * (BB_THISCALL *)(void *, int)) vt[0x48 / 4])(mgr, id);
        /* body columns carry flag 0x20 (input-inert, so the game's hit test, flags & 0x60, skips them); 0x40 marks a
           hidden gadget, which must not take the click */
        if (!readable(g, 0x34) || (*(uint16_t *)(g + 0xc)) != id || (*(uint16_t *)(g + 0x18) & 0x40)) continue;
        int gx = *(int16_t *)(g + 0xe), gy = *(int16_t *)(g + 0x10), gw = *(int16_t *)(g + 0x12), gh = *(int16_t *)(g + 0x14);
        if (x < gx || x >= gx + gw || y < gy || y >= gy + gh) continue;
        *gid_out = id;
        *gy_out = gy;
        return (y - gy) / ROW_H;
    }
    return -1;
}

/* The stats screen whose callback is at mgr+0xc0, or 0. */
static const StatsScreen *screen_at(const uint8_t *mgr) {
    void *cb = *(void *const *)(mgr + 0xc0);
    for (int i = 0; i < 2; i++)
        if (cb && cb == api->addr("BBShell.dll", SCREENS[i].cb_va)) return &SCREENS[i];
    return 0;
}

static uint32_t global_u32(uint32_t va) {
    const uint32_t *p = api->addr("BBShell.dll", va);
    return readable(p, 4) ? *p : 0;
}

/* The player's card in modmenu's News reader (mm_open_page, /news/card/<assn>/p/<pid>): true when the bridge answered and
   the reader showed it. Not loaded, a name the bridge would refuse, or no answer (mm_open_page's 1) and the built-in card
   opens instead. */
typedef int (*mm_open_page_fn)(const char *path);

static int card_in_reader(const char *stem, unsigned pid) {
    HMODULE mm = GetModuleHandleA("modmenu.dll");
    mm_open_page_fn open_page = mm ? (mm_open_page_fn)GetProcAddress(mm, "mm_open_page") : 0;
    char page[64];
    if (!open_page || !readable(stem, 9)) return 0;
    size_t n = 0;
    while (n < 9 && stem[n]) n++;           /* the bridge takes 1 to 8 letters and digits, nothing else */
    if (n == 0 || n > 8) return 0;
    for (size_t i = 0; i < n; i++)
        if (!isalnum((unsigned char)stem[i])) return 0;
    snprintf(page, sizeof page, "/news/card/%.*s/p/%u", (int)n, stem, pid);
    int rc = open_page(page);
    api->log("playercard: %s in the News reader -> %d", page, rc);
    return rc == 0;
}

/* The card's window takes the releases: the game sees the press that closes the card but not its release, keeps the
   button held, and the next press on the stats screen is no edge and opens nothing. Hand the game the release it
   missed once the card is gone. */
static void release_game_button(void) {
    HWND w = GetCapture();
    POINT p;
    if (!GetCursorPos(&p)) return;
    if (!w) w = WindowFromPoint(p);         /* the screen's child window (FrontOffice and so on), not the desktop frame */
    if (!w || GetWindowThreadProcessId(w, 0) != GetCurrentThreadId() || !ScreenToClient(w, &p)) return;
    PostMessageA(w, WM_LBUTTONUP, 0, MAKELPARAM(p.x, p.y));
}

/* Why a click on a stats screen opened no card (probe only). */
static void none(const char *why) {
    if (probe) api->log("playercard probe: no card: %s", why);
}

static void open_card(const StatsScreen *s, uint8_t *screen, int gid, int gy, int vis) {
    uint8_t *mgr = (uint8_t *)api->addr("BBShell.dll", MGR_VA);
    void *map_fn = api->addr("BBShell.dll", MAP_ROW_VA);
    if (!mgr || !map_fn) return;
    int16_t group = *(int16_t *)(screen + s->group_off);
    uint16_t row = ((uint16_t (BB_THISCALL *)(void *, int, int))map_fn)(mgr, group, vis);
    uint8_t *tab = screen + s->table_off;
    uint16_t nrows = *(uint16_t *)tab;
    uint8_t *rows = *(uint8_t **)(tab + 4);
    if (probe) api->log("playercard probe: %s hit gadget %#x gy=%d vis=%d -> scroll group %d, table row %u of %u", s->name,
                        gid, gy, vis, group, row, nrows);
    if (row >= nrows || !readable(rows, (size_t)(row + 1) * 0xa0)) { none("visible row not in the table"); return; }
    uint8_t *rr = rows + row * 0xa0;
    const uint8_t *push = (const uint8_t *)api->addr("BBShell.dll", ID_PUSH_VA);
    if (!readable(push, 2) || push[0] != 0x6a || (push[1] != 10 && push[1] != 14)) {
        api->log("playercard: id cell push at 6805cb0b not recognised");
        return;
    }
    int cell = push[1];
    int32_t type = *(int32_t *)(rr + cell * 8);
    unsigned pid = *(uint16_t *)(rr + cell * 8 + 4);
    if (probe) api->log("playercard probe: %s row %u cell %d type=%#x pid=%u name='%.31s'", s->name, row, cell, type, pid,
                        (char *)rr + 0x80);
    if (type != 0x2000) { none("the id cell is not type 0x2000"); return; }
    if (pid < 100) { none("the id is below 100 (a team row)"); return; }   /* ids below 100 are teams */
    char name[40];
    snprintf(name, sizeof name, "%.31s", (char *)rr + 0x80);
    if (!name[0] || (uint8_t)name[0] < 32) snprintf(name, sizeof name, "Player %u", pid);
    void *asn = *(void **)(screen + 8);
    char **inner = readable(asn, 4) ? *(char ***)asn : 0;
    const char *an = readable(inner, 0x98) ? inner[0x25] : 0;
    if (!readable(an, 1) || !an[0]) { api->log("playercard: association name not found"); return; }
    if (card_in_reader(an, pid)) return;
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


/* A left button press on a stats screen. The probe line logs what the click saw before any card is resolved. */
static void on_click(uint8_t *mgr, int x, int y) {
    const StatsScreen *s = screen_at(mgr);
    uint8_t *screen = s ? *(uint8_t **)api->addr("BBShell.dll", s->obj_va) : 0;
    if (probe)
        api->log("playercard probe: click x=%d y=%d mgr+0xc0=%p screen=%s obj=%p team_obj=%#x cur_screen=%#x",
                 (int16_t)x, (int16_t)y, *(void **)(mgr + 0xc0), s ? s->name : "none", (void *)screen,
                 global_u32(TEAM_OBJ_VA), global_u32(CUR_SCREEN_VA));
    if (!s || !readable(screen, s->size)) return;
    int gid = 0, gy = 0;
    int vis = hit_row(mgr, (int16_t)x, (int16_t)y, s->ext, &gid, &gy);
    if (vis < 0) { none("no body cell under the click"); return; }
    open_card(s, screen, gid, gy, vis);
}

static uint16_t (BB_THISCALL *orig_event)(void *mgr, int x, int y, int buttons, int code, int p5);

/* Mouse wheel on the game's lists. The stock shell ignores WM_MOUSEWHEEL; only the arrow gadgets scroll, one row a
   click. A WH_GETMESSAGE hook on the UI thread takes the wheel message (turned into WM_NULL) and banks its delta; the
   next event tick spends it as presses of the list's own up or down arrow, through the same path the handler takes for
   a clicked gadget (BBShell 68043e3c): each scroll group's FUN_68072020 until one takes the id, then the screen's
   callback at mgr+0xc0, which refills the rows. Setting a group's top directly (FUN_68043ae0) is not enough: the body
   draws rows the screen never loaded and the game jumps to a garbage address. Faking a click at the arrow's position
   does not work either: dialog gadget rects are relative to the dialog, the handler's x and y to the screen. Scroll
   groups are a list at mgr+0xbc (node: +0 next, +0xa top, +0xc visible rows, +0x10 total rows, +0x12 scrollbar id,
   +0x14 up id, +0x16 down id, +0x18 body id). A list with a selection bar (node +8) moves the bar, which scrolls at the
   edge, as the arrows do. */
#define WHEEL_ROWS 3
#define GROUP_CLICK_VA 0x68072020u      /* fastcall (ecx node, edx unused, mgr, id), ret 8: nonzero when it took the id */
static int wheel_on;
static volatile LONG wheel_acc;
static HHOOK wheel_hook;

static LRESULT CALLBACK wheel_proc(int code, WPARAM wp, LPARAM lp) {
    MSG *m = (MSG *)lp;
    char cls[32] = "";
    if (code == HC_ACTION && wp == PM_REMOVE && m && m->message == WM_MOUSEWHEEL &&
        !(GetClassNameA(GetAncestor(m->hwnd, GA_ROOT), cls, sizeof cls) && !strncmp(cls, "BB", 2))) {   /* mod windows */
        InterlockedExchangeAdd(&wheel_acc, (short)HIWORD(m->wParam));
        m->message = WM_NULL;
    }
    return CallNextHookEx(wheel_hook, code, wp, lp);
}

static uint8_t *gadget(uint8_t *mgr, int id) {
    uint32_t *vt = *(uint32_t **)mgr;
    uint8_t *g = ((uint8_t * (BB_THISCALL *)(void *, int)) vt[0x48 / 4])(mgr, id);
    return readable(g, 0x1a) && *(uint16_t *)(g + 0xc) == id ? g : 0;
}

/* The scroll group a wheel at (x, y) moves: the one whose body-to-scrollbar box holds the cursor, else the only group
   with rows off screen. 0 when none. Rects are compared as the game passes them; in a dialog they do not line up with
   x and y, and the single-list fallback picks the group. */
static uint8_t *wheel_group(uint8_t *mgr, int x, int y) {
    uint8_t *only = 0;
    int idx = 0, nscroll = 0;
    for (uint8_t *n = *(uint8_t **)(mgr + 0xbc); readable(n, 0x1a) && idx < 64; n = *(uint8_t **)n, idx++) {
        if (*(int16_t *)(n + 0x10) <= *(int16_t *)(n + 0xc)) continue;
        nscroll++, only = n;
        uint8_t *sb = gadget(mgr, *(uint16_t *)(n + 0x12)), *body = gadget(mgr, *(uint16_t *)(n + 0x18));
        if (!sb || (*(uint16_t *)(sb + 0x18) & 0x40)) continue;
        int sx = *(int16_t *)(sb + 0xe), sy = *(int16_t *)(sb + 0x10);
        int right = sx + *(int16_t *)(sb + 0x12), bottom = sy + *(int16_t *)(sb + 0x14);
        int left = body ? *(int16_t *)(body + 0xe) : sx;
        if (x >= left && x < right && y >= sy && y < bottom) return n;
    }
    return nscroll == 1 ? only : 0;
}

static int apply_wheel(uint8_t *mgr, int x, int y) {
    LONG acc = InterlockedExchange(&wheel_acc, 0);
    int notches = acc / WHEEL_DELTA;
    if (acc % WHEEL_DELTA) InterlockedExchangeAdd(&wheel_acc, acc % WHEEL_DELTA);
    if (!notches) return 0;
    if (notches > 10) notches = 10;       /* a long stall between ticks would otherwise replay every notch at once */
    if (notches < -10) notches = -10;
    uint8_t *n = wheel_group(mgr, x, y);
    int top = n ? *(int16_t *)(n + 0xa) : -1, id = n ? *(uint16_t *)(n + (notches > 0 ? 0x14 : 0x16)) : 0;
    if (n && id) {
        uint32_t (__attribute__((fastcall)) *click)(void *, int, void *, int) =
            (uint32_t (__attribute__((fastcall)) *)(void *, int, void *, int))api->addr("BBShell.dll", GROUP_CLICK_VA);
        void (*cb)(int) = *(void (**)(int))(mgr + 0xc0);
        for (int i = WHEEL_ROWS * (notches < 0 ? -notches : notches); i > 0; i--) {
            int idx = 0;
            for (uint8_t *g = *(uint8_t **)(mgr + 0xbc); readable(g, 0x1a) && idx < 64; g = *(uint8_t **)g, idx++)
                if ((uint16_t)click(g, 0, mgr, id)) break;
            if (cb) cb(id);
        }
    }
    if (probe)
        api->log("playercard probe: wheel %d at x=%d y=%d group %p arrow %d top %d -> %d (total %d visible %d)", notches,
                 x, y, (void *)n, id, top, n ? *(int16_t *)(n + 0xa) : -1, n ? *(int16_t *)(n + 0x10) : 0,
                 n ? *(int16_t *)(n + 0xc) : 0);
    return n && id;
}

/* The gadget manager's event handler, called for every input tick with the mouse position (client coordinates of
   the screen) and the button state (bit 0 = left). Body list gadgets are not hit-tested by the game, so the click is
   taken here: on the left button going down. The card's reader runs a modal loop that keeps the game ticking, so the
   edge is recorded before the card opens and ticks inside that loop are ignored; otherwise every tick while the card is
   up reads as a new press and opens the card again. */
static uint16_t BB_THISCALL h_event(void *mgr, int x, int y, int buttons, int code, int p5) {
    static int was_down, in_click;
    uint16_t r = orig_event(mgr, x, y, buttons, code, p5);
    if (wheel_on) {
        if (!wheel_hook) wheel_hook = SetWindowsHookExA(WH_GETMESSAGE, wheel_proc, 0, GetCurrentThreadId());
        if (wheel_acc && !in_click && !(buttons & 1) && readable(mgr, 0xc4) &&
            apply_wheel((uint8_t *)mgr, (int16_t)x, (int16_t)y))
            r = 1;                                                       /* as the handler answers a gadget press */
    }
    int down = buttons & 1, edge = down && !was_down;
    was_down = down;
    if (edge && !in_click && mgr == api->addr("BBShell.dll", MGR_VA)) {
        in_click = 1;
        on_click((uint8_t *)mgr, x, y);
        in_click = 0;
        release_game_button();
    }
    return r;
}

BB_EXPORT int bbmod_init(const BBModAPI *a) {
    api = a;
    if (a->version != BBMOD_API_VERSION) return 1;
    if (!a->ini_int("playercard", "enable", 1)) { a->log("playercard: disabled"); return 0; }
    probe = a->ini_int("playercard", "probe", 0);
    wheel_on = a->ini_int("playercard", "wheel", 1);
    static const uint8_t ev_prolog[5] = {0x83, 0xec, 0x04, 0x53, 0x56};               /* sub esp,4 / push ebx / push esi */
    if (a->detour("BBShell.dll", 0x68043d20, ev_prolog, 5, (void *)h_event, (void **)&orig_event) < 0) return 3;
    a->log("playercard: registered (probe=%d wheel=%d)", probe, wheel_on);
    return 0;
}
