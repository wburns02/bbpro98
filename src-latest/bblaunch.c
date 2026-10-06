// bblaunch: start Baseball.exe suspended, pin DLLs that the game unloads/reloads
// but whose addresses it assumes are stable (Win9x reloaded them at the same address).
#include <windows.h>
#include <stdio.h>
int main(int argc, char **argv) {
    char dir[MAX_PATH], exe[MAX_PATH], cmd[MAX_PATH];
    GetModuleFileNameA(NULL, dir, MAX_PATH);
    char *s = strrchr(dir, '\\'); if (s) *s = 0;
    SetCurrentDirectoryA(dir);
    snprintf(exe, MAX_PATH, "%s\\Baseball.exe", dir);
    snprintf(cmd, MAX_PATH, "\"%s\"", exe);
    STARTUPINFOA si = { sizeof si }; PROCESS_INFORMATION pi;
    if (!CreateProcessA(exe, cmd, 0, 0, FALSE, CREATE_SUSPENDED, 0, dir, &si, &pi)) return 1;
    const char *pins[] = { "bbfix.dll", 0 };
    if (argc > 1 && !strcmp(argv[1], "--nopin")) pins[0] = 0;
    FARPROC ll = GetProcAddress(GetModuleHandleA("kernel32.dll"), "LoadLibraryA");
    for (int i = 0; pins[i]; i++) {
        char path[MAX_PATH]; snprintf(path, MAX_PATH, "%s\\%s", dir, pins[i]);
        void *r = VirtualAllocEx(pi.hProcess, 0, MAX_PATH, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
        WriteProcessMemory(pi.hProcess, r, path, strlen(path) + 1, 0);
        HANDLE t = CreateRemoteThread(pi.hProcess, 0, 0, (LPTHREAD_START_ROUTINE)ll, r, 0, 0);
        WaitForSingleObject(t, 10000);
        DWORD base = 0; GetExitCodeThread(t, &base);
        printf("pinned %s at %08lx\n", pins[i], base); fflush(stdout);
        CloseHandle(t);
    }
    ResumeThread(pi.hThread);
    WaitForSingleObject(pi.hProcess, INFINITE);
    return 0;
}
