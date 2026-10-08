/* pctest.c: runs playercard.c's stats-file reader and card text outside the game, for pctest.py.
   usage: pctest.exe STATS.DAT pid [pid ...]   prints one RAW line per (table, scope) record found, then the card text. */
#include "../mods/playercard.c"

static void tlog(const char *f, ...) { (void)f; }

int main(int argc, char **argv) {
    static BBModAPI a;
    a.version = BBMOD_API_VERSION;
    a.log = tlog;
    api = &a;
    for (int i = 2; i < argc; i++) {
        unsigned pid = (unsigned)atoi(argv[i]);
        static Card c;
        int rc = load_card(argv[1], pid, &c);
        printf("PID %u rc %d\n", pid, rc);
        const char *tn[2] = {"bat", "pit"};
        for (int t = 0; t < 2; t++)
            for (int s = 0; s < 4; s++) {
                const Line *l = t ? &c.pit[s] : &c.bat[s];
                if (!(t ? c.has_pit[s] : c.has_bat[s])) continue;
                printf("RAW %s %d", tn[t], s);
                for (int k = 0; k < l->n; k++) printf(" %u", l->w[k]);
                printf("\n");
            }
        if (c.has_fld) {
            printf("RAW fld 2");
            for (int k = 0; k < c.fld.n; k++) printf(" %u", c.fld.w[k]);
            printf("\n");
        }
        build_text("Test Player", pid, &c);
        for (int k = 0; k < nlines; k++) printf("TXT %s\n", lines[k]);
    }
    fflush(stdout);
    return 0;
}
