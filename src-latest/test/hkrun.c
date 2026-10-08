/* hkrun.c: loads bbfix.dll (which loads the test mods), then hktarget.dll and its relocated copy hkreloc.dll, calls
   every test function and prints one line per result for hktest.py. */
#include <windows.h>
#include <stdio.h>
typedef int (*f0)(void); typedef int (*f1)(int); typedef int (*f2)(int, int);
int main(void) {
    if (!LoadLibraryA("bbfix.dll")) { printf("ERR bbfix %lu\n", GetLastError()); return 1; }
    const char *names[2] = {"hktarget.dll", "hkreloc.dll"};
    for (int i = 0; i < 2; i++) {
        HMODULE m = LoadLibraryA(names[i]);
        if (!m) { printf("ERR load %s %lu\n", names[i], GetLastError()); return 1; }
        printf("%s base %p\n", names[i], (void *)m);
        printf("%s f_add %d\n", names[i], ((f2)GetProcAddress(m, "f_add"))(2, 3));
        printf("%s f_call %d\n", names[i], ((f1)GetProcAddress(m, "f_call"))(4));
        printf("%s f_call2 %d\n", names[i], ((f1)GetProcAddress(m, "f_call2"))(4));
        printf("%s f_mid41 %d\n", names[i], ((f1)GetProcAddress(m, "f_mid"))(41));
        printf("%s f_mid5 %d\n", names[i], ((f1)GetProcAddress(m, "f_mid"))(5));
        printf("%s f_mid77 %d\n", names[i], ((f1)GetProcAddress(m, "f_mid"))(77));
        printf("%s f_patch %d\n", names[i], ((f0)GetProcAddress(m, "f_patch"))());
        printf("%s f_bad %d\n", names[i], ((f0)GetProcAddress(m, "f_bad"))());
        printf("%s f_rel %d\n", names[i], ((f0)GetProcAddress(m, "f_rel"))());
    }
    fflush(stdout);
    return 0;
}
