/* modmenu.c: replaces the dead WWW SITE button on the main menu with a Mods window. The window lists the game mods
   loaded from bbfix.ini and opens three tools that run in the host: Create a Player (a form that creates a player in an
   association's free agent pool), League News (a text browser over the league news pages) and Build a Season (builds a
   playable association for any MLB season 1871..2019 from the Lahman database).

   Hook: detour on EZShell.dll VA 0x6a006370, the WWW SITE button handler, void __fastcall handler(menu_screen): this in
   ECX, no stack arguments, plain ret. Its prolog 81 ec 54 02 00 00 (sub esp,0x254) is position independent. The original
   is never called (it would open a browser).

   Spool: a request is written as q<ID>.tmp and renamed to q<ID>.req in <exe dir>\Mods\spool\; the bridge (news/modbridge.py)
   answers with r<ID>.rsp, which the mod polls for on a 250 ms timer, reads, deletes and parses.

   bbfix.ini:  [mods] load=mods\modmenu.dll      [modmenu] enable=1
   Build:  /mnt/nvme/bbpro98/zigenv/bin/python -m ziglang cc -target x86-windows-gnu -O2 -shared -Isrc-latest
           -o modmenu.dll src-latest/mods/modmenu.c -lgdi32 -luser32 */
#include <windows.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../bbmod.h"

static const BBModAPI *api;

#define REQ_MAX 8192
#define RSP_MAX (512 * 1024)
#define HDR_MAX 400
#define TIMER_POLL 1
#define POLL_MS 250
#define TIMEOUT_MS 20000
#define BUILD_TIMEOUT_MS 1200000
#define IDC_CLOSE IDCANCEL                  /* Close buttons use IDCANCEL, so ESC and the close box share a path */

typedef struct { char key[32]; char *val; } MMKV;
typedef struct { MMKV kv[HDR_MAX]; int n; char *body; char *buf; } MMResp;   /* buf owns all the strings */

static char spool_override[MAX_PATH];
static unsigned id_counter;

/* ---------------------------------------------------------------- spool protocol (no window code) */

static int exists_dir(const char *p) {
    DWORD a = GetFileAttributesA(p);
    return a != INVALID_FILE_ATTRIBUTES && (a & FILE_ATTRIBUTE_DIRECTORY);
}

/* out gets "<exe dir>Mods\spool\"; 1 when that folder exists */
static int mm_spool_dir(char *out, int n) {
    char exe[MAX_PATH], *sl;
    GetModuleFileNameA(0, exe, MAX_PATH);
    sl = strrchr(exe, '\\');
    if (sl) sl[1] = 0; else exe[0] = 0;
    snprintf(out, n, "%sMods\\spool\\", exe);
    return exists_dir(out);
}

/* the spool folder in use: the test override when set, else the game's */
static int mm_dir(char *out, int n) {
    if (spool_override[0]) {
        snprintf(out, n, "%s", spool_override);
        return exists_dir(out);
    }
    return mm_spool_dir(out, n);
}

static void mm_set_spool(const char *dir) {
    snprintf(spool_override, sizeof spool_override, "%s", dir ? dir : "");
}

/* copy src to dst, dropping bytes below 0x20, at most n-1 bytes */
static void mm_clean(char *dst, const char *src, int n) {
    int k = 0;
    if (n <= 0) return;
    for (; *src && k < n - 1; src++)
        if ((unsigned char)*src >= 0x20) dst[k++] = *src;
    dst[k] = 0;
}

/* appends to *p, never past end; 0 when it does not fit */
static int app(char **p, const char *end, const char *fmt, ...) {
    va_list ap;
    int k;
    va_start(ap, fmt);
    k = vsnprintf(*p, end - *p, fmt, ap);
    va_end(ap);
    if (k < 0 || k >= end - *p) return 0;
    *p += k;
    return 1;
}

/* kv = {k0, v0, k1, v1, ...}, nkv pairs. 0 = written, -1 = no spool folder, -2 = io or too long */
static int mm_send(const char *op, const char *const *kv, int nkv, char *id_out) {
    char dir[MAX_PATH + 16], tmp[MAX_PATH + 32], req[MAX_PATH + 32], id[9], val[257];
    static char text[REQ_MAX];
    char *p = text, *end = text + sizeof text - 1;
    HANDLE h;
    DWORD got = 0, len;
    int i;
    if (!mm_dir(dir, sizeof dir)) return -1;
    snprintf(id, sizeof id, "%08lx",
             (unsigned long)(GetTickCount() * 2654435761u + (++id_counter) * 40503u + GetCurrentProcessId()));
    if (id_out) strcpy(id_out, id);
    if (!app(&p, end, "op=%s\r\n", op)) return -2;
    for (i = 0; i < nkv; i++) {
        mm_clean(val, kv[2 * i + 1], sizeof val);
        if (!app(&p, end, "%s=%s\r\n", kv[2 * i], val)) return -2;
    }
    snprintf(tmp, sizeof tmp, "%sq%s.tmp", dir, id);
    snprintf(req, sizeof req, "%sq%s.req", dir, id);
    h = CreateFileA(tmp, GENERIC_WRITE, 0, 0, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, 0);
    if (h == INVALID_HANDLE_VALUE) return -2;
    len = (DWORD)(p - text);
    if (!WriteFile(h, text, len, &got, 0) || got != len) {
        CloseHandle(h);
        DeleteFileA(tmp);
        return -2;
    }
    CloseHandle(h);
    if (!MoveFileA(tmp, req)) {
        DeleteFileA(tmp);
        return -2;
    }
    if (api) api->log("modmenu: send %s %s", op, id);
    return 0;
}

static const char *mm_get(const MMResp *r, const char *key) {
    int i;
    for (i = 0; i < r->n; i++)
        if (!strcmp(r->kv[i].key, key)) return r->kv[i].val;
    return 0;
}

static void mm_free(MMResp *r) {
    free(r->buf);
    memset(r, 0, sizeof *r);
}

/* header lines up to the first empty line (CRLF or bare LF), the rest is the body. Consumes buf: 0 = parsed, -1 = bad
   (no status header; buf freed) */
static int mm_parse(char *buf, MMResp *r) {
    char *p = buf, *eol, *next, *eq, *body = 0;
    size_t len;
    memset(r, 0, sizeof *r);
    r->buf = buf;
    while (*p) {
        eol = strchr(p, '\n');
        next = eol ? eol + 1 : p + strlen(p);
        len = (size_t)((eol ? eol : next) - p);
        if (len && p[len - 1] == '\r') len--;
        if (!len) {
            body = next;
            break;
        }
        p[len] = 0;
        eq = strchr(p, '=');
        if (eq && eq - p > 0 && eq - p < 32 && r->n < HDR_MAX) {
            snprintf(r->kv[r->n].key, sizeof r->kv[r->n].key, "%.*s", (int)(eq - p), p);
            r->kv[r->n].val = eq + 1;
            r->n++;
        }
        p = next;
    }
    if (!body) body = p;
    if (!mm_get(r, "status")) {
        free(buf);
        memset(r, 0, sizeof *r);
        return -1;
    }
    r->body = body;
    return 0;
}

/* 1 = response read and parsed, 0 = not yet, -1 = bad (the response is deleted either way once it exists) */
static int mm_poll(const char *id, MMResp *r) {
    char dir[MAX_PATH + 16], rsp[MAX_PATH + 32], *buf;
    HANDLE h;
    DWORD n, got = 0;
    if (!mm_dir(dir, sizeof dir)) return -1;
    snprintf(rsp, sizeof rsp, "%sr%s.rsp", dir, id);
    h = CreateFileA(rsp, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, 0, OPEN_EXISTING,
                    FILE_ATTRIBUTE_NORMAL, 0);
    if (h == INVALID_HANDLE_VALUE) return 0;
    n = GetFileSize(h, 0);
    if (n == INVALID_FILE_SIZE || n > RSP_MAX || !(buf = malloc(n + 1))) {
        CloseHandle(h);
        DeleteFileA(rsp);
        return -1;
    }
    if (!ReadFile(h, buf, n, &got, 0) || got != n) {
        CloseHandle(h);
        DeleteFileA(rsp);
        free(buf);
        return -1;
    }
    CloseHandle(h);
    DeleteFileA(rsp);
    buf[n] = 0;
    return mm_parse(buf, r) ? -1 : 1;
}

static void mm_cancel(const char *id) {
    char dir[MAX_PATH + 16], req[MAX_PATH + 32];
    mm_dir(dir, sizeof dir);
    snprintf(req, sizeof req, "%sq%s.req", dir, id);
    DeleteFileA(req);
}

/* ---------------------------------------------------------------- window helpers */

#define IDC_CREATE 10
#define IDC_NEWS 11
#define IDC_BUILD 12
#define MSG_NOSPOOL "The mods bridge is not set up (no Mods\\spool folder)."
#define MSG_NOANSWER "No answer from the mods bridge. Is it running?"
#define MSG_BADANSWER "The mods bridge sent a bad answer."
#define MSG_IO "Could not write the request to the mods bridge spool."

/* every window with a bridge request keeps one of these first in its state struct; done gets r (mm_free it) on an
   answer, or NULL and an error text when the request failed or timed out (the error is already on screen) */
typedef struct Win Win;
struct Win {
    HWND hwnd, status, msg;
    int busy, last_s;
    char id[9], op[16];
    DWORD t0, limit;
    void (*done)(Win *w, MMResp *r, const char *err);
};

static HINSTANCE hinst;
static HFONT ui_font, mono_font;
static int open_windows, classes_ok;

static void open_create(HWND owner);
static void open_news(HWND owner);
static void open_build(HWND owner);

static HWND mk(HWND p, const char *cls, const char *txt, DWORD style, int x, int y, int w, int h, int id) {
    HWND c = CreateWindowExA(0, cls, txt, WS_CHILD | WS_VISIBLE | style, x, y, w, h, p, (HMENU)(INT_PTR)id, hinst, 0);
    SendMessageA(c, WM_SETFONT, (WPARAM)ui_font, 0);
    return c;
}

static HWND lbl(HWND p, const char *txt, int x, int y, int w, int h) { return mk(p, "STATIC", txt, 0, x, y, w, h, 0); }

static HWND btn(HWND p, const char *txt, int x, int y, int w, int h, int id) {
    return mk(p, "BUTTON", txt, WS_TABSTOP, x, y, w, h, id);
}

static HWND combo(HWND p, int x, int y, int w, int id) {
    return mk(p, "COMBOBOX", "", CBS_DROPDOWNLIST | WS_VSCROLL | WS_TABSTOP, x, y, w, 220, id);
}

static HWND text_in(HWND p, int x, int y, int w, int h, int id) {
    return mk(p, "EDIT", "", WS_BORDER | WS_TABSTOP | ES_AUTOHSCROLL, x, y, w, h, id);
}

static HWND text_out(HWND p, int x, int y, int w, int h, int id, DWORD extra) {
    return mk(p, "EDIT", "", ES_MULTILINE | ES_READONLY | ES_AUTOVSCROLL | WS_VSCROLL | WS_BORDER | WS_TABSTOP | extra,
              x, y, w, h, id);
}

/* the window's client area is CW x CH; placed centred over owner (or the desktop), clamped to the screen's origin */
static HWND make_win(const char *cls, const char *title, int cw, int ch, HWND owner, void *param) {
    RECT r = {0, 0, cw, ch}, o;
    int w, h, x, y;
    AdjustWindowRectEx(&r, WS_POPUP | WS_CAPTION | WS_SYSMENU, FALSE, WS_EX_DLGMODALFRAME | WS_EX_TOPMOST);
    w = r.right - r.left;
    h = r.bottom - r.top;
    GetWindowRect(owner ? owner : GetDesktopWindow(), &o);
    x = o.left + (o.right - o.left - w) / 2;
    y = o.top + (o.bottom - o.top - h) / 2;
    if (x < 0) x = 0;
    if (y < 0) y = 0;
    return CreateWindowExA(WS_EX_DLGMODALFRAME | WS_EX_TOPMOST, cls, title, WS_POPUP | WS_CAPTION | WS_SYSMENU, x, y,
                           w, h, owner, 0, hinst, param);
}

static int is_ours(HWND h) {
    char cls[32];
    if (!h || !GetClassNameA(h, cls, sizeof cls)) return 0;
    return !strcmp(cls, "BBModMenu") || !strcmp(cls, "BBModCreate") || !strcmp(cls, "BBModNews") ||
           !strcmp(cls, "BBModBuild");
}

static void reg_class(const char *name, WNDPROC proc) {
    WNDCLASSA c;
    memset(&c, 0, sizeof c);
    c.lpfnWndProc = proc;
    c.hInstance = hinst;
    c.hCursor = LoadCursorA(0, (LPCSTR)IDC_ARROW);
    c.hbrBackground = (HBRUSH)(COLOR_BTNFACE + 1);
    c.lpszClassName = name;
    RegisterClassA(&c);
}

static LRESULT CALLBACK menu_proc(HWND h, UINT m, WPARAM wp, LPARAM lp);
static LRESULT CALLBACK create_proc(HWND h, UINT m, WPARAM wp, LPARAM lp);
static LRESULT CALLBACK news_proc(HWND h, UINT m, WPARAM wp, LPARAM lp);
static LRESULT CALLBACK build_proc(HWND h, UINT m, WPARAM wp, LPARAM lp);

static void init_once(void) {
    if (classes_ok) return;
    hinst = GetModuleHandleA(0);
    ui_font = (HFONT)GetStockObject(DEFAULT_GUI_FONT);
    mono_font = CreateFontA(-13, 0, 0, 0, FW_NORMAL, 0, 0, 0, ANSI_CHARSET, 0, 0, 0, FIXED_PITCH | FF_MODERN,
                            "Courier New");
    reg_class("BBModMenu", menu_proc);
    reg_class("BBModCreate", create_proc);
    reg_class("BBModNews", news_proc);
    reg_class("BBModBuild", build_proc);
    classes_ok = 1;
}

static BOOL CALLBACK busy_cb(HWND c, LPARAM busy) {
    char cls[16];
    GetClassNameA(c, cls, sizeof cls);
    if (!strcmp(cls, "Button") && GetDlgCtrlID(c) != IDC_CLOSE) EnableWindow(c, !busy);
    return TRUE;
}

static void win_error(Win *w, const char *msg) {
    SetWindowTextA(w->status, msg);
    if (w->msg) SetWindowTextA(w->msg, msg);
}

static void win_finish(Win *w) {
    KillTimer(w->hwnd, TIMER_POLL);
    w->busy = 0;
    EnumChildWindows(w->hwnd, busy_cb, 0);
}

/* sends a request and starts the poll timer; a failed send shows its error at once */
static void win_request(Win *w, const char *op, const char *const *kv, int nkv, DWORD limit) {
    char id[9];
    int rc = mm_send(op, kv, nkv, id);
    if (rc) {
        win_error(w, rc == -1 ? MSG_NOSPOOL : MSG_IO);
        return;
    }
    strcpy(w->id, id);
    snprintf(w->op, sizeof w->op, "%s", op);
    w->busy = 1;
    w->t0 = GetTickCount();
    w->limit = limit;
    w->last_s = -1;
    EnumChildWindows(w->hwnd, busy_cb, 1);
    SetTimer(w->hwnd, TIMER_POLL, POLL_MS, 0);
    SetWindowTextA(w->status, !strcmp(op, "build") ? "Building the season... 0 s" : "Working...");
}

static void win_poll(Win *w) {
    MMResp r;
    DWORD el = GetTickCount() - w->t0;
    char s[64];
    int rc = mm_poll(w->id, &r);
    if (rc == 0) {
        if (el >= w->limit) {
            api->log("modmenu: %s %s -> timeout", w->op, w->id);
            mm_cancel(w->id);
            win_finish(w);
            win_error(w, MSG_NOANSWER);
            w->done(w, 0, MSG_NOANSWER);
        } else if (!strcmp(w->op, "build") && (int)(el / 1000) != w->last_s) {
            w->last_s = (int)(el / 1000);
            snprintf(s, sizeof s, "Building the season... %d s", w->last_s);
            SetWindowTextA(w->status, s);
        }
        return;
    }
    win_finish(w);
    if (rc < 0) {
        win_error(w, MSG_BADANSWER);
        w->done(w, 0, MSG_BADANSWER);
        return;
    }
    api->log("modmenu: %s %s -> %s", w->op, w->id, mm_get(&r, "status"));
    w->done(w, &r, 0);
}

static void win_close(Win *w) {
    if (w->busy) {
        mm_cancel(w->id);
        win_finish(w);
    }
    DestroyWindow(w->hwnd);
}

/* WM_DESTROY of any of our windows: the owner gets its input back and is activated */
static void win_destroyed(Win *w) {
    HWND o = GetWindow(w->hwnd, GW_OWNER);
    open_windows--;
    if (w->busy) {
        mm_cancel(w->id);
        w->busy = 0;
    }
    if (o && IsWindow(o)) {
        EnableWindow(o, TRUE);
        SetActiveWindow(o);
    }
}

/* ---------------------------------------------------------------- Mods window */

typedef struct { Win w; HWND list; } MenuState;

static const struct { const char *name, *desc; } MOD_DESC[] = {
    {"playercard", "Player card: click a player on a Statistics screen."},
    {"aging", "Aging: players decline and retire by age and ability."},
    {"modmenu", "This menu."},
    {"simtrace", "Sim trace: debug log of every play."},
    {"seed", "Seed: fixed random seed for testing."},
    {"steal", "Steal: base-stealing test hook."},
    {"pitchtrace", "Pitch trace: debug log of pitch choices."},
};

static int is_dll(const char *s, size_t n) {
    static const char ext[] = ".dll";
    size_t i;
    if (n <= 4) return 0;
    for (i = 0; i < 4; i++)
        if ((s[n - 4 + i] | 0x20) != ext[i]) return 0;
    return 1;
}

static const char *describe(const char *name) {
    size_t i;
    for (i = 0; i < sizeof MOD_DESC / sizeof MOD_DESC[0]; i++)
        if (!strcmp(MOD_DESC[i].name, name)) return MOD_DESC[i].desc;
    return name;
}

/* one line per mod in bbfix.ini [mods] load=, comma-separated, paths like mods\x.dll */
static void mods_text(char *out, int n) {
    char raw[1024], name[64];
    char *p = raw, *o = out, *comma, *t, *e, *b;
    size_t len;
    out[0] = 0;
    api->ini_str("mods", "load", "", raw, sizeof raw);
    while (*p) {
        comma = strchr(p, ',');
        len = comma ? (size_t)(comma - p) : strlen(p);
        t = p;
        e = p + len;
        while (t < e && *t == ' ') t++;
        while (e > t && e[-1] == ' ') e--;
        b = e;
        while (b > t && b[-1] != '\\' && b[-1] != '/') b--;
        if (is_dll(b, e - b)) e -= 4;
        if (e > b && (size_t)(e - b) < sizeof name) {
            memcpy(name, b, e - b);
            name[e - b] = 0;
            app(&o, out + n, "%s\r\n", describe(name));
        }
        p = comma ? comma + 1 : p + len;
    }
    if (!out[0]) snprintf(out, n, "(none)");
}

static void bridge_line(HWND st, const char *body) {
    char s[200];
    int k = (int)strcspn(body, "\r\n");
    if (k > 150) k = 150;
    if (k) snprintf(s, sizeof s, "Bridge: %.*s", k, body);
    else snprintf(s, sizeof s, "Bridge: error");
    SetWindowTextA(st, s);
}

static void menu_done(Win *w, MMResp *r, const char *err) {
    (void)err;
    if (!r) return;
    if (!strcmp(mm_get(r, "status"), "ok")) SetWindowTextA(w->status, "Bridge: ready");
    else bridge_line(w->status, r->body);
    mm_free(r);
}

static void build_menu(MenuState *st) {
    HWND h = st->w.hwnd;
    char list[1024];
    btn(h, "Create a Player", 20, 16, 180, 28, IDC_CREATE);
    lbl(h, "New player, free agent in any association", 210, 21, 190, 20);
    btn(h, "League News", 20, 52, 180, 28, IDC_NEWS);
    lbl(h, "Stories, standings, previews, awards, scouting", 210, 57, 190, 20);
    btn(h, "Build a Season", 20, 88, 180, 28, IDC_BUILD);
    lbl(h, "Any MLB season from 1871 to 2019", 210, 93, 190, 20);
    lbl(h, "Loaded game mods:", 20, 130, 200, 18);
    st->list = text_out(h, 20, 150, 380, 100, 0, 0);
    mods_text(list, sizeof list);
    SetWindowTextA(st->list, list);
    btn(h, "Close", 310, 262, 90, 28, IDC_CLOSE);
    st->w.status = lbl(h, "Bridge: checking...", 20, 268, 280, 20);
    win_request(&st->w, "ping", 0, 0, TIMEOUT_MS);
}

static LRESULT CALLBACK menu_proc(HWND h, UINT m, WPARAM wp, LPARAM lp) {
    MenuState *st = (MenuState *)GetWindowLongPtrA(h, GWLP_USERDATA);
    switch (m) {
    case WM_CREATE:
        st = (MenuState *)((CREATESTRUCTA *)lp)->lpCreateParams;
        SetWindowLongPtrA(h, GWLP_USERDATA, (LONG_PTR)st);
        st->w.hwnd = h;
        st->w.done = menu_done;
        open_windows++;
        build_menu(st);
        return 0;
    case WM_TIMER:
        if (wp == TIMER_POLL) win_poll(&st->w);
        return 0;
    case WM_COMMAND:
        switch (LOWORD(wp)) {
        case IDC_CREATE: open_create(h); break;
        case IDC_NEWS: open_news(h); break;
        case IDC_BUILD: open_build(h); break;
        case IDC_CLOSE: win_close(&st->w); break;
        }
        return 0;
    case WM_CLOSE:
        win_close(&st->w);
        return 0;
    case WM_DESTROY:
        win_destroyed(&st->w);
        return 0;
    case WM_NCDESTROY:
        free(st);
        return 0;
    }
    return DefWindowProcA(h, m, wp, lp);
}

/* ---------------------------------------------------------------- Create a Player window */

#define MAXARCH 64
#define MAXSTEM 64
#define IDC_ASSN 21
#define IDC_POS 22
#define IDC_ARCH 23
#define IDC_DO 24

typedef struct { char key[32], label[64], role[8], blurb[256], now[160], ceil[160], pitches[256]; } Arch;

typedef struct {
    Win w;
    HWND assn, pos, arch, blurb, rlab[5], rnow[5], rceil[5], plab[7], pnow[7], pceil[7], phdr[3];
    HWND first, last, bats, throws, age, mode;
    char stem[MAXSTEM][32];
    int nstem, narch, pit;
    Arch arch_list[MAXARCH];
} CreateState;

/* request fields: keys and values copied in, pairs for mm_send */
typedef struct { const char *kv[96]; int n; char s[3072]; size_t used; } KVB;

static const char *const POS_T[] = {"Pitcher", "Catcher", "First base", "Second base", "Third base", "Shortstop",
                                    "Left field", "Center field", "Right field"};
static const char *const POS_C[] = {"P", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"};
static const char *const BATS_T[] = {"Left", "Right", "Switch"}, *const BATS_C[] = {"L", "R", "S"};
static const char *const THROW_T[] = {"Left", "Right"}, *const THROW_C[] = {"L", "R"};
static const char *const MODE_T[] = {"Realistic", "Sandbox"}, *const MODE_C[] = {"realistic", "sandbox"};
static const char *const RLAB[2][5] = {{"Contact", "Power", "Speed", "Arm", "Fielding"},
                                       {"Stamina", "Control", "Hold runners", "Strikeout", ""}};
static const char *const RKEY[2][5] = {{"contact", "power", "speed", "arm", "fielding"},
                                       {"stamina", "control", "hold", "strikeout", ""}};
static const char *const PSLOT[7] = {"FB", "CB", "SI", "SL", "CU", "SC", "KN"};
static const char *const PLAB[7] = {"Fastball", "Curveball", "Sinker", "Slider", "Changeup", "Screwball", "Knuckleball"};
static const struct { int v; const char *t; } GRADE[] = {
    {20, "20 poor"}, {25, "25"}, {30, "30 well below"}, {35, "35"}, {40, "40 below average"}, {45, "45"},
    {50, "50 average"}, {55, "55"}, {60, "60 plus"}, {65, "65"}, {70, "70 plus-plus"}, {75, "75"}, {80, "80 elite"}};

static void kv_put(KVB *b, const char *k, const char *fmt, ...) {
    va_list ap;
    size_t kl = strlen(k) + 1, room;
    char *kp, *vp;
    int r;
    if (b->n + 2 > 96 || b->used + kl + 1 >= sizeof b->s) return;
    kp = b->s + b->used;
    memcpy(kp, k, kl);
    vp = kp + kl;
    room = sizeof b->s - b->used - kl;
    va_start(ap, fmt);
    r = vsnprintf(vp, room, fmt, ap);
    va_end(ap);
    if (r < 0) r = 0;
    if ((size_t)r >= room) r = (int)room - 1;
    vp[r] = 0;
    b->used += kl + (size_t)r + 1;
    b->kv[b->n++] = kp;
    b->kv[b->n++] = vp;
}

/* copies the field before the first TAB into out; returns the text after that TAB (or the end) */
static const char *tab_field(const char *v, char *out, size_t n) {
    size_t full = strcspn(v, "\t"), k = full < n ? full : n - 1;
    memcpy(out, v, k);
    out[k] = 0;
    return v + full + (v[full] == '\t');
}

static void cp(char *dst, size_t n, const MMResp *r, const char *key) {
    const char *v = mm_get(r, key);
    snprintf(dst, n, "%s", v ? v : "");
}

/* value of field f in the first token "key:f1:f2" of a comma list whose field 0 is key; -1 when absent */
static int field_of(const char *list, const char *key, int f) {
    char tok[64], *fl[4], *s, *t;
    int nf;
    while (*list) {
        size_t len = strcspn(list, ",");
        if (len >= sizeof tok) len = sizeof tok - 1;
        memcpy(tok, list, len);
        tok[len] = 0;
        nf = 0;
        s = tok;
        for (;;) {
            fl[nf++] = s;
            if (nf == 4) break;
            t = strchr(s, ':');
            if (!t) break;
            *t = 0;
            s = t + 1;
        }
        if (nf > f && !strcmp(fl[0], key)) return atoi(fl[f]);
        list += len;
        if (*list == ',') list++;
    }
    return -1;
}

static void add_items(HWND c, const char *const *t, int n, int def) {
    int i;
    for (i = 0; i < n; i++) SendMessageA(c, CB_ADDSTRING, 0, (LPARAM)t[i]);
    SendMessageA(c, CB_SETCURSEL, def, 0);
}

static void fill_grades(HWND c, int notthrown) {
    int i, idx;
    if (notthrown) {
        idx = (int)SendMessageA(c, CB_ADDSTRING, 0, (LPARAM)"Not thrown");
        SendMessageA(c, CB_SETITEMDATA, idx, -1);
    }
    for (i = 0; i < (int)(sizeof GRADE / sizeof GRADE[0]); i++) {
        idx = (int)SendMessageA(c, CB_ADDSTRING, 0, (LPARAM)GRADE[i].t);
        SendMessageA(c, CB_SETITEMDATA, idx, GRADE[i].v);
    }
    SendMessageA(c, CB_SETCURSEL, 0, 0);
}

static int grade_of(HWND c) {
    int s = (int)SendMessageA(c, CB_GETCURSEL, 0, 0);
    return s < 0 ? -1 : (int)SendMessageA(c, CB_GETITEMDATA, s, 0);
}

/* selects the item nearest grade g; g < 0 selects Not thrown (the first item of a pitch list) */
static void pick_grade(HWND c, int g) {
    int n = (int)SendMessageA(c, CB_GETCOUNT, 0, 0), i, best = 0, bd = 1 << 30;
    if (g < 0) {
        SendMessageA(c, CB_SETCURSEL, 0, 0);
        return;
    }
    for (i = 0; i < n; i++) {
        int d = (int)SendMessageA(c, CB_GETITEMDATA, i, 0), diff;
        if (d < 0) continue;
        diff = d > g ? d - g : g - d;
        if (diff < bd) {
            bd = diff;
            best = i;
        }
    }
    SendMessageA(c, CB_SETCURSEL, best, 0);
}

static void show(HWND h, int on) { ShowWindow(h, on ? SW_SHOW : SW_HIDE); }

/* hitters: five rating rows; pitchers: four rating rows (no Ceiling for Strikeout) and seven pitch rows */
static void set_role(CreateState *st) {
    int i, pit = st->pit;
    for (i = 0; i < 5; i++) {
        int rowon = !(pit && i == 4), ceilon = rowon && !(pit && i == 3);
        SetWindowTextA(st->rlab[i], RLAB[pit][i]);
        show(st->rlab[i], rowon);
        show(st->rnow[i], rowon);
        show(st->rceil[i], ceilon);
    }
    for (i = 0; i < 7; i++) {
        show(st->plab[i], pit);
        show(st->pnow[i], pit);
        show(st->pceil[i], pit);
    }
    for (i = 0; i < 3; i++) show(st->phdr[i], pit);
}

static void apply_arch(CreateState *st, int ai) {
    const Arch *a;
    int r, s, nv, cv;
    if (ai < 0 || ai >= st->narch) return;
    a = &st->arch_list[ai];
    SetWindowTextA(st->blurb, a->blurb);
    for (r = 0; r < 5; r++) {
        const char *key = RKEY[st->pit][r];
        if (!*key) continue;
        nv = field_of(a->now, key, 1);
        if (nv < 0) nv = 50;
        cv = field_of(a->ceil, key, 1);
        if (cv < 0) cv = nv;
        pick_grade(st->rnow[r], nv);
        pick_grade(st->rceil[r], cv);
    }
    if (st->pit)
        for (s = 0; s < 7; s++) {
            nv = field_of(a->pitches, PSLOT[s], 1);
            cv = field_of(a->pitches, PSLOT[s], 2);
            if (nv < 0 || cv < 0) nv = cv = -1;
            pick_grade(st->pnow[s], nv);
            pick_grade(st->pceil[s], cv);
        }
}

/* the Archetype list follows the Position (Pitcher = pit, else hit); the first one is applied */
static void refill_arch(CreateState *st) {
    const char *role;
    int i, n = 0;
    st->pit = SendMessageA(st->pos, CB_GETCURSEL, 0, 0) == 0;
    role = st->pit ? "pit" : "hit";
    SendMessageA(st->arch, CB_RESETCONTENT, 0, 0);
    for (i = 0; i < st->narch; i++) {
        int idx;
        if (strcmp(st->arch_list[i].role, role)) continue;
        idx = (int)SendMessageA(st->arch, CB_ADDSTRING, 0, (LPARAM)st->arch_list[i].label);
        SendMessageA(st->arch, CB_SETITEMDATA, idx, i);
        n++;
    }
    set_role(st);
    if (n) {
        SendMessageA(st->arch, CB_SETCURSEL, 0, 0);
        apply_arch(st, (int)SendMessageA(st->arch, CB_GETITEMDATA, 0, 0));
    } else {
        SetWindowTextA(st->blurb, "");
    }
}

static void build_create(CreateState *st) {
    HWND h = st->w.hwnd;
    char t[4];
    int i, y;
    lbl(h, "Association", 10, 13, 80, 20);
    st->assn = combo(h, 95, 10, 300, IDC_ASSN);
    lbl(h, "First name", 10, 43, 80, 20);
    st->first = text_in(h, 95, 40, 140, 22, 0);
    SendMessageA(st->first, EM_LIMITTEXT, 16, 0);
    lbl(h, "Last name", 250, 43, 70, 20);
    st->last = text_in(h, 325, 40, 140, 22, 0);
    SendMessageA(st->last, EM_LIMITTEXT, 16, 0);
    lbl(h, "Position", 10, 73, 80, 20);
    st->pos = combo(h, 95, 70, 140, IDC_POS);
    add_items(st->pos, POS_T, 9, 0);
    lbl(h, "Bats", 250, 73, 70, 20);
    st->bats = combo(h, 325, 70, 70, 0);
    add_items(st->bats, BATS_T, 3, 1);
    lbl(h, "Throws", 410, 73, 45, 20);
    st->throws = combo(h, 460, 70, 70, 0);
    add_items(st->throws, THROW_T, 2, 1);
    lbl(h, "Age", 10, 103, 80, 20);
    st->age = combo(h, 95, 100, 60, 0);
    for (i = 17; i <= 45; i++) {
        snprintf(t, sizeof t, "%d", i);
        SendMessageA(st->age, CB_ADDSTRING, 0, (LPARAM)t);
    }
    SendMessageA(st->age, CB_SETCURSEL, 22 - 17, 0);
    lbl(h, "Mode", 250, 103, 70, 20);
    st->mode = combo(h, 325, 100, 140, 0);
    add_items(st->mode, MODE_T, 2, 0);
    lbl(h, "Archetype", 10, 133, 80, 20);
    st->arch = combo(h, 95, 130, 220, IDC_ARCH);
    st->blurb = lbl(h, "", 10, 158, 620, 34);
    lbl(h, "Rating", 10, 196, 115, 18);
    lbl(h, "Now", 130, 196, 72, 18);
    lbl(h, "Ceiling", 210, 196, 72, 18);
    st->phdr[0] = lbl(h, "Pitch", 330, 196, 105, 18);
    st->phdr[1] = lbl(h, "Now", 440, 196, 72, 18);
    st->phdr[2] = lbl(h, "Ceiling", 520, 196, 72, 18);
    for (i = 0; i < 5; i++) {
        y = 218 + 26 * i;
        st->rlab[i] = lbl(h, "", 10, y + 3, 115, 20);
        st->rnow[i] = combo(h, 130, y, 72, 0);
        fill_grades(st->rnow[i], 0);
        st->rceil[i] = combo(h, 210, y, 72, 0);
        fill_grades(st->rceil[i], 0);
    }
    for (i = 0; i < 7; i++) {
        y = 218 + 26 * i;
        st->plab[i] = lbl(h, PLAB[i], 330, y + 3, 105, 20);
        st->pnow[i] = combo(h, 440, y, 72, 0);
        fill_grades(st->pnow[i], 1);
        st->pceil[i] = combo(h, 520, y, 72, 0);
        fill_grades(st->pceil[i], 1);
    }
    st->w.msg = text_out(h, 10, 402, 620, 80, 0, 0);
    st->w.status = st->w.msg;
    btn(h, "Create", 440, 490, 90, 26, IDC_DO);
    btn(h, "Close", 540, 490, 90, 26, IDC_CLOSE);
    refill_arch(st);
}

static int cur(HWND c) { return (int)SendMessageA(c, CB_GETCURSEL, 0, 0); }

static void on_arch(Win *w, MMResp *r, const char *err);
static void on_create_done(Win *w, MMResp *r, const char *err);

static void do_create(CreateState *st) {
    KVB b;
    char buf[32], f[32], l[32], k[40];
    int r, s, pit = st->pit, as = cur(st->arch), sel = cur(st->assn);
    memset(&b, 0, sizeof b);
    if (sel < 0) {
        win_error(&st->w, "Pick an association first.");
        return;
    }
    if (as < 0) {
        win_error(&st->w, "No archetype is selected.");
        return;
    }
    GetWindowTextA(st->first, buf, sizeof buf);
    mm_clean(f, buf, sizeof f);
    GetWindowTextA(st->last, buf, sizeof buf);
    mm_clean(l, buf, sizeof l);
    kv_put(&b, "assn", "%s", st->stem[(int)SendMessageA(st->assn, CB_GETITEMDATA, sel, 0)]);
    kv_put(&b, "first", "%s", f);
    kv_put(&b, "last", "%s", l);
    kv_put(&b, "pos", "%s", POS_C[cur(st->pos)]);
    kv_put(&b, "bats", "%s", BATS_C[cur(st->bats)]);
    kv_put(&b, "throws", "%s", THROW_C[cur(st->throws)]);
    kv_put(&b, "age", "%d", 17 + cur(st->age));
    kv_put(&b, "archetype", "%s", st->arch_list[(int)SendMessageA(st->arch, CB_GETITEMDATA, as, 0)].key);
    kv_put(&b, "mode", "%s", MODE_C[cur(st->mode)]);
    for (r = 0; r < 5; r++) {
        if (!*RKEY[pit][r]) continue;
        snprintf(k, sizeof k, "now_%s", RKEY[pit][r]);
        kv_put(&b, k, "%d", grade_of(st->rnow[r]));
        if (pit && r == 3) continue;
        snprintf(k, sizeof k, "ceil_%s", RKEY[pit][r]);
        kv_put(&b, k, "%d", grade_of(st->rceil[r]));
    }
    if (pit)
        for (s = 0; s < 7; s++) {
            int g = grade_of(st->pnow[s]);
            snprintf(k, sizeof k, "p_%s_now", PSLOT[s]);
            if (g < 0) kv_put(&b, k, "none");
            else kv_put(&b, k, "%d", g);
            g = grade_of(st->pceil[s]);
            snprintf(k, sizeof k, "p_%s_ceil", PSLOT[s]);
            if (g < 0) kv_put(&b, k, "none");
            else kv_put(&b, k, "%d", g);
        }
    st->w.done = on_create_done;
    win_request(&st->w, "create", b.kv, b.n / 2, TIMEOUT_MS);
}

/* the association list (STEM\tlabel), then the archetypes: the window is ready when both have answered */
static void on_assns(Win *w, MMResp *r, const char *err) {
    CreateState *st = (CreateState *)w;
    char k[32];
    const char *c, *v, *q;
    int i, n;
    (void)err;
    if (!r) return;
    if (strcmp(mm_get(r, "status"), "ok")) {
        SetWindowTextA(w->msg, r->body);
        mm_free(r);
        return;
    }
    c = mm_get(r, "count");
    n = c ? atoi(c) : 0;
    SendMessageA(st->assn, CB_RESETCONTENT, 0, 0);
    st->nstem = 0;
    for (i = 0; i < n && st->nstem < MAXSTEM; i++) {
        int idx;
        snprintf(k, sizeof k, "assn.%d", i);
        v = mm_get(r, k);
        if (!v) continue;
        q = tab_field(v, st->stem[st->nstem], sizeof st->stem[0]);
        idx = (int)SendMessageA(st->assn, CB_ADDSTRING, 0, (LPARAM)q);
        SendMessageA(st->assn, CB_SETITEMDATA, idx, st->nstem);
        st->nstem++;
    }
    if (st->nstem) SendMessageA(st->assn, CB_SETCURSEL, 0, 0);
    mm_free(r);
    w->done = on_arch;
    win_request(w, "archetypes", 0, 0, TIMEOUT_MS);
}

static void on_arch(Win *w, MMResp *r, const char *err) {
    CreateState *st = (CreateState *)w;
    char k[40];
    const char *c;
    int i, n;
    (void)err;
    if (!r) return;
    w->done = on_create_done;
    if (strcmp(mm_get(r, "status"), "ok")) {
        SetWindowTextA(w->msg, r->body);
        mm_free(r);
        return;
    }
    c = mm_get(r, "count");
    n = c ? atoi(c) : 0;
    if (n > MAXARCH) n = MAXARCH;
    memset(st->arch_list, 0, sizeof st->arch_list);
    st->narch = 0;
    for (i = 0; i < n; i++) {
        Arch *a = &st->arch_list[st->narch];
        const char *v, *q;
        snprintf(k, sizeof k, "arch.%d", i);
        v = mm_get(r, k);
        if (!v) continue;
        q = tab_field(v, a->key, sizeof a->key);
        q = tab_field(q, a->label, sizeof a->label);
        tab_field(q, a->role, sizeof a->role);
        snprintf(k, sizeof k, "arch.%d.blurb", i);
        cp(a->blurb, sizeof a->blurb, r, k);
        snprintf(k, sizeof k, "arch.%d.now", i);
        cp(a->now, sizeof a->now, r, k);
        snprintf(k, sizeof k, "arch.%d.ceil", i);
        cp(a->ceil, sizeof a->ceil, r, k);
        snprintf(k, sizeof k, "arch.%d.pitches", i);
        cp(a->pitches, sizeof a->pitches, r, k);
        st->narch++;
    }
    mm_free(r);
    refill_arch(st);
}

static void on_create_done(Win *w, MMResp *r, const char *err) {
    (void)err;
    if (!r) return;
    SetWindowTextA(w->msg, r->body);
    mm_free(r);
}

static LRESULT CALLBACK create_proc(HWND h, UINT m, WPARAM wp, LPARAM lp) {
    CreateState *st = (CreateState *)GetWindowLongPtrA(h, GWLP_USERDATA);
    int sel;
    switch (m) {
    case WM_CREATE:
        st = (CreateState *)((CREATESTRUCTA *)lp)->lpCreateParams;
        SetWindowLongPtrA(h, GWLP_USERDATA, (LONG_PTR)st);
        st->w.hwnd = h;
        st->w.done = on_assns;
        open_windows++;
        build_create(st);
        win_request(&st->w, "assns", 0, 0, TIMEOUT_MS);
        return 0;
    case WM_TIMER:
        if (wp == TIMER_POLL) win_poll(&st->w);
        return 0;
    case WM_COMMAND:
        if (LOWORD(wp) == IDC_POS && HIWORD(wp) == CBN_SELCHANGE) {
            refill_arch(st);
        } else if (LOWORD(wp) == IDC_ARCH && HIWORD(wp) == CBN_SELCHANGE) {
            sel = cur(st->arch);
            if (sel >= 0) apply_arch(st, (int)SendMessageA(st->arch, CB_GETITEMDATA, sel, 0));
        } else if (LOWORD(wp) == IDC_DO && HIWORD(wp) == BN_CLICKED) {
            do_create(st);
        } else if (LOWORD(wp) == IDC_CLOSE) {
            win_close(&st->w);
        }
        return 0;
    case WM_CLOSE:
        win_close(&st->w);
        return 0;
    case WM_DESTROY:
        win_destroyed(&st->w);
        return 0;
    case WM_NCDESTROY:
        free(st);
        return 0;
    }
    return DefWindowProcA(h, m, wp, lp);
}

static void open_create(HWND owner) {
    CreateState *st = calloc(1, sizeof *st);
    if (!st) return;
    if (!make_win("BBModCreate", "Create a Player", 640, 526, owner, st)) {
        free(st);
        return;
    }
    EnableWindow(owner, FALSE);
}

/* ---------------------------------------------------------------- League News window */

#define IDC_LINKS 31
#define IDC_BACK 32
#define IDC_HOME 33
#define IDC_OPENLINK 34
#define HIST_MAX 32
#define PATH_LEN 256

typedef struct {
    Win w;
    HWND page, list;
    char cur[PATH_LEN];
    char hist[HIST_MAX][PATH_LEN];
    int nhist;
    MMResp pg;                          /* the page on screen: its links are read from here */
} NewsState;

static void news_done(Win *w, MMResp *r, const char *err) {
    NewsState *st = (NewsState *)w;
    char k[32], label[160], item[200];
    const char *t, *v;
    int i, n;
    (void)err;
    if (!r) return;
    t = mm_get(r, "title");
    SetWindowTextA(w->hwnd, t && *t ? t : "League News");
    t = mm_get(r, "path");
    if (t && *t) snprintf(st->cur, sizeof st->cur, "%s", t);
    mm_free(&st->pg);
    st->pg = *r;
    SetWindowTextA(st->page, st->pg.body);
    SendMessageA(st->list, LB_RESETCONTENT, 0, 0);
    t = mm_get(&st->pg, "count");
    n = t ? atoi(t) : 0;
    for (i = 0; i < n; i++) {
        snprintf(k, sizeof k, "link.%d", i);
        v = mm_get(&st->pg, k);
        tab_field(v ? v : "", label, sizeof label);
        snprintf(item, sizeof item, "%d. %s", i + 1, label);
        SendMessageA(st->list, LB_ADDSTRING, 0, (LPARAM)item);
    }
    t = mm_get(&st->pg, "status");
    SetWindowTextA(w->status, t && strcmp(t, "ok") ? t : "");
}

/* requests a page; push keeps the page on screen for Back */
static void news_go(NewsState *st, const char *path, int push) {
    const char *kv[2];
    if (st->w.busy) return;
    if (push && st->cur[0]) {
        if (st->nhist == HIST_MAX) {
            memmove(st->hist[0], st->hist[1], (HIST_MAX - 1) * PATH_LEN);
            st->nhist--;
        }
        snprintf(st->hist[st->nhist++], PATH_LEN, "%s", st->cur);
    }
    snprintf(st->cur, sizeof st->cur, "%s", path);
    kv[0] = "path";
    kv[1] = st->cur;
    st->w.done = news_done;
    win_request(&st->w, "news", kv, 1, TIMEOUT_MS);
}

static void news_back(NewsState *st) {
    char path[PATH_LEN];
    if (st->w.busy || !st->nhist) return;
    snprintf(path, sizeof path, "%s", st->hist[--st->nhist]);
    news_go(st, path, 0);
}

static void news_open(NewsState *st) {
    char k[32], label[160], path[PATH_LEN];
    const char *v;
    int sel = (int)SendMessageA(st->list, LB_GETCURSEL, 0, 0);
    if (st->w.busy || sel < 0) return;
    snprintf(k, sizeof k, "link.%d", sel);
    v = mm_get(&st->pg, k);
    if (!v) return;
    snprintf(path, sizeof path, "%s", tab_field(v, label, sizeof label));
    if (path[0]) news_go(st, path, 1);
}

static void build_news(NewsState *st) {
    HWND h = st->w.hwnd;
    st->page = text_out(h, 10, 10, 680, 330, 0, WS_HSCROLL | ES_AUTOHSCROLL);
    SendMessageA(st->page, WM_SETFONT, (WPARAM)mono_font, 0);
    st->list = mk(h, "LISTBOX", "", LBS_NOTIFY | WS_VSCROLL | WS_BORDER | WS_TABSTOP, 10, 348, 680, 110, IDC_LINKS);
    SendMessageA(st->list, WM_SETFONT, (WPARAM)mono_font, 0);
    btn(h, "Back", 10, 466, 90, 26, IDC_BACK);
    btn(h, "Home", 110, 466, 90, 26, IDC_HOME);
    btn(h, "Open link", 210, 466, 90, 26, IDC_OPENLINK);
    btn(h, "Close", 600, 466, 90, 26, IDC_CLOSE);
    st->w.status = lbl(h, "", 320, 471, 260, 20);
    st->w.msg = st->page;
}

static LRESULT CALLBACK news_proc(HWND h, UINT m, WPARAM wp, LPARAM lp) {
    NewsState *st = (NewsState *)GetWindowLongPtrA(h, GWLP_USERDATA);
    switch (m) {
    case WM_CREATE:
        st = (NewsState *)((CREATESTRUCTA *)lp)->lpCreateParams;
        SetWindowLongPtrA(h, GWLP_USERDATA, (LONG_PTR)st);
        st->w.hwnd = h;
        open_windows++;
        build_news(st);
        news_go(st, "/news/", 0);
        return 0;
    case WM_TIMER:
        if (wp == TIMER_POLL) win_poll(&st->w);
        return 0;
    case WM_COMMAND:
        switch (LOWORD(wp)) {
        case IDC_LINKS:
            if (HIWORD(wp) == LBN_DBLCLK) news_open(st);
            break;
        case IDC_OPENLINK: news_open(st); break;
        case IDC_BACK: news_back(st); break;
        case IDC_HOME: news_go(st, "/news/", strcmp(st->cur, "/news/") != 0); break;
        case IDC_CLOSE: win_close(&st->w); break;
        }
        return 0;
    case WM_CLOSE:
        win_close(&st->w);
        return 0;
    case WM_DESTROY:
        win_destroyed(&st->w);
        return 0;
    case WM_NCDESTROY:
        mm_free(&st->pg);
        free(st);
        return 0;
    }
    return DefWindowProcA(h, m, wp, lp);
}

static void open_news(HWND owner) {
    NewsState *st = calloc(1, sizeof *st);
    if (!st) return;
    if (!make_win("BBModNews", "League News", 700, 500, owner, st)) {
        free(st);
        return;
    }
    EnableWindow(owner, FALSE);
}

/* ---------------------------------------------------------------- Build a Season window */

#define IDC_YEAR 41
#define IDC_GO 42

typedef struct { Win w; HWND year; } BuildState;

static void build_done(Win *w, MMResp *r, const char *err) {
    const char *s;
    (void)err;
    if (!r) return;
    SetWindowTextA(w->msg, r->body);
    s = mm_get(r, "status");
    if (!strcmp(s, "ok")) SetWindowTextA(w->status, "Done.");
    else if (!strcmp(s, "busy")) SetWindowTextA(w->status, "The bridge is busy. Try again.");
    else SetWindowTextA(w->status, "The build failed.");
    mm_free(r);
}

static void build_go(BuildState *st) {
    char buf[16], yr[8];
    const char *kv[2];
    int y;
    if (st->w.busy) return;
    GetWindowTextA(st->year, buf, sizeof buf);
    y = atoi(buf);
    if (y < 1871 || y > 2019) {
        win_error(&st->w, "Enter a season from 1871 to 2019.");
        return;
    }
    snprintf(yr, sizeof yr, "%d", y);
    kv[0] = "year";
    kv[1] = yr;
    st->w.done = build_done;
    win_request(&st->w, "build", kv, 1, BUILD_TIMEOUT_MS);
}

static LRESULT CALLBACK build_proc(HWND h, UINT m, WPARAM wp, LPARAM lp) {
    BuildState *st = (BuildState *)GetWindowLongPtrA(h, GWLP_USERDATA);
    switch (m) {
    case WM_CREATE:
        st = (BuildState *)((CREATESTRUCTA *)lp)->lpCreateParams;
        SetWindowLongPtrA(h, GWLP_USERDATA, (LONG_PTR)st);
        st->w.hwnd = h;
        open_windows++;
        lbl(h, "Season (1871 to 2019):", 10, 13, 150, 20);
        st->year = mk(h, "EDIT", "", WS_BORDER | WS_TABSTOP | ES_AUTOHSCROLL | ES_NUMBER, 165, 10, 60, 22, IDC_YEAR);
        SendMessageA(st->year, EM_LIMITTEXT, 4, 0);
        btn(h, "Build", 235, 9, 90, 26, IDC_GO);
        lbl(h, "Builds the season's teams, players and schedule from the Lahman database. It appears in the "
               "association list when it is done.", 10, 44, 400, 32);
        st->w.msg = text_out(h, 10, 80, 400, 136, 0, 0);
        btn(h, "Close", 320, 224, 90, 26, IDC_CLOSE);
        st->w.status = lbl(h, "", 10, 229, 300, 20);
        return 0;
    case WM_TIMER:
        if (wp == TIMER_POLL) win_poll(&st->w);
        return 0;
    case WM_COMMAND:
        if (LOWORD(wp) == IDC_GO) build_go(st);
        else if (LOWORD(wp) == IDC_CLOSE) win_close(&st->w);
        return 0;
    case WM_CLOSE:
        win_close(&st->w);
        return 0;
    case WM_DESTROY:
        win_destroyed(&st->w);
        return 0;
    case WM_NCDESTROY:
        free(st);
        return 0;
    }
    return DefWindowProcA(h, m, wp, lp);
}

static void open_build(HWND owner) {
    BuildState *st = calloc(1, sizeof *st);
    if (!st) return;
    if (!make_win("BBModBuild", "Build a Season", 420, 260, owner, st)) {
        free(st);
        return;
    }
    EnableWindow(owner, FALSE);
}

/* ---------------------------------------------------------------- modal run and hook */

static BOOL CALLBACK close_ours_cb(HWND h, LPARAM lp) {
    (void)lp;
    if (is_ours(h)) DestroyWindow(h);
    return TRUE;
}

static int is_combo(HWND h) {
    char cls[16];
    return h && GetClassNameA(h, cls, sizeof cls) && !strcmp(cls, "ComboBox");
}

/* runs the Mods window on the game's UI thread until its windows are all closed. Esc closes the active window (not
   while a combo box is open); Enter in the link list opens the link */
static void run_menu(void) {
    HWND owner, mods, top;
    MenuState *st;
    MSG m;
    BOOL g;
    int quit = 0, code = 0;
    init_once();
    owner = GetActiveWindow();
    if (!owner) owner = GetForegroundWindow();
    open_windows = 0;
    st = calloc(1, sizeof *st);
    if (!st) return;
    mods = make_win("BBModMenu", "Baseball Pro '98 Mods", 420, 300, owner, st);
    if (!mods) {
        free(st);
        return;
    }
    if (owner) EnableWindow(owner, FALSE);
    while (open_windows > 0) {
        g = GetMessageA(&m, 0, 0, 0);
        if (g == 0) {
            quit = 1;
            code = (int)m.wParam;
            break;
        }
        if (g < 0) break;
        top = GetActiveWindow();
        if (m.message == WM_KEYDOWN && top && is_ours(top)) {
            if (m.wParam == VK_ESCAPE && !is_combo(m.hwnd)) {
                SendMessageA(top, WM_COMMAND, IDCANCEL, 0);
                continue;
            }
            if (m.wParam == VK_RETURN && GetDlgCtrlID(m.hwnd) == IDC_LINKS) {
                SendMessageA(top, WM_COMMAND, IDC_OPENLINK, 0);
                continue;
            }
        }
        if (top && is_ours(top) && IsDialogMessageA(top, &m)) continue;
        TranslateMessage(&m);
        DispatchMessageA(&m);
    }
    EnumThreadWindows(GetCurrentThreadId(), close_ours_cb, 0);
    if (owner) {
        EnableWindow(owner, TRUE);
        SetForegroundWindow(owner);
    }
    if (quit) PostQuitMessage(code);
}

static void (__attribute__((fastcall)) *orig_www)(void *self);
static void __attribute__((fastcall)) BB_HANDLER h_www(void *self) { (void)self; run_menu(); }

BB_EXPORT int bbmod_init(const BBModAPI *a) {
    static const uint8_t www_prolog[6] = {0x81, 0xec, 0x54, 0x02, 0x00, 0x00};   /* sub esp,0x254 */
    api = a;
    if (a->version != BBMOD_API_VERSION) return 1;
    if (!a->ini_int("modmenu", "enable", 1)) {
        a->log("modmenu: disabled");
        return 0;
    }
    if (a->detour("EZShell.dll", 0x6a006370, www_prolog, 6, (void *)h_www, (void **)&orig_www) < 0) return 3;
    a->log("modmenu: registered");
    return 0;
}
