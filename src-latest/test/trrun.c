/* trrun.c: loads bbfix.dll (which loads the mod named in bbfix.ini and starts bbtrace.log) and exits; trtest.py reads
   the trace files afterwards. */
#include <windows.h>
#include <stdio.h>
int main(void) {
    if (!LoadLibraryA("bbfix.dll")) { printf("ERR bbfix %lu\n", GetLastError()); return 1; }
    printf("ok\n"); fflush(stdout);
    return 0;
}
