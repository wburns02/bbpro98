/* mmtest.c: runs modmenu.c's spool protocol outside the game, for mmtest.py.
   send <spooldir> <op> [k v ...]: sends the request, polls for the answer (MMTEST_TIMEOUT_MS, default 20 s) and prints
     ID <id>, H <key>=<value> per header, then BODY and the body. Exit 2 on timeout (after mm_cancel), 3 when the send
     fails (prints SEND <code>), 4 on a bad answer.
   clean <text>: prints mm_clean(text) in brackets.
   visible: makes a window with make_win and prints VISIBLE 1 when it is shown (a top-level popup without WS_VISIBLE
     and no ShowWindow is never mapped, so the menu would open invisibly). */
#include "../mods/modmenu.c"

static void tlog(const char *f, ...) { (void)f; }

/* raw bytes to stdout: no CRT text-mode translation of the body's CR LF */
static void wr(const char *s, size_t n) {
    HANDLE h = GetStdHandle(STD_OUTPUT_HANDLE);
    DWORD w = 0;
    while (n) {
        if (!WriteFile(h, s, (DWORD)n, &w, 0) || !w) break;
        s += w;
        n -= w;
    }
}

static void wrs(const char *s) { wr(s, strlen(s)); }

int main(int argc, char **argv) {
    static BBModAPI a;
    static MMResp r;
    char id[9], line[64];
    const char *env;
    int rc, i, to = 20000;
    a.version = BBMOD_API_VERSION;
    a.log = tlog;
    api = &a;
    if (argc == 3 && !strcmp(argv[1], "clean")) {
        char out[512];
        mm_clean(out, argv[2], sizeof out);
        wrs("[");
        wrs(out);
        wrs("]\n");
        return 0;
    }
    if (argc == 2 && !strcmp(argv[1], "visible")) {
        WNDCLASSA c;
        HWND h;
        memset(&c, 0, sizeof c);
        c.lpfnWndProc = DefWindowProcA;
        c.hInstance = GetModuleHandleA(0);
        c.lpszClassName = "MMTestWin";
        hinst = c.hInstance;
        RegisterClassA(&c);
        h = make_win("MMTestWin", "test", 200, 100, 0, 0);
        snprintf(line, sizeof line, "VISIBLE %d\n", h && IsWindowVisible(h) ? 1 : 0);
        wrs(line);
        if (h) DestroyWindow(h);
        return 0;
    }
    if (argc < 4 || strcmp(argv[1], "send")) {
        wrs("usage: mmtest.exe send <spooldir> <op> [k v ...] | clean <text>\n");
        return 1;
    }
    env = getenv("MMTEST_TIMEOUT_MS");
    if (env && atoi(env) > 0) to = atoi(env);
    mm_set_spool(argv[2]);
    rc = mm_send(argv[3], (const char *const *)(argv + 4), (argc - 4) / 2, id);
    if (rc) {
        snprintf(line, sizeof line, "SEND %d\n", rc);
        wrs(line);
        return 3;
    }
    snprintf(line, sizeof line, "ID %s\n", id);
    wrs(line);
    for (i = 0; (rc = mm_poll(id, &r)) == 0 && i < to / 50; i++) Sleep(50);
    if (rc == 0) {
        mm_cancel(id);
        wrs("TIMEOUT\n");
        return 2;
    }
    if (rc < 0) {
        wrs("BAD\n");
        return 4;
    }
    for (i = 0; i < r.n; i++) {
        wrs("H ");
        wrs(r.kv[i].key);
        wrs("=");
        wrs(r.kv[i].val);
        wrs("\n");
    }
    wrs("BODY\n");
    wrs(r.body);
    mm_free(&r);
    return 0;
}
