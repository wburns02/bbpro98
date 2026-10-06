// bbfix.dll: emulate Win9x tolerance for windows left behind by unloaded shell DLLs.
// Hooks FreeLibrary (via IAT of every game module) and destroys windows owned by the DLL
// (wndproc inside its image, or hInstance == module) BEFORE it is unmapped.
#include <windows.h>
#include <tlhelp32.h>
#include <stdio.h>
#include <string.h>

static FILE *lg;
static void L(const char *f, ...) { if(!lg) return; va_list a; va_start(a,f); vfprintf(lg,f,a); va_end(a); fputc('\n',lg); fflush(lg); }
#include <stdarg.h>
static HANDLE tr; static CRITICAL_SECTION trcs;
static void T(const char *f, ...) {   // timestamped trace line -> bbtrace.log (flushed immediately)
    if(!tr) return; char b[900]; SYSTEMTIME st; GetLocalTime(&st);
    int n=snprintf(b,200,"%02d:%02d:%02d.%03d [%04lx] ",st.wHour,st.wMinute,st.wSecond,st.wMilliseconds,GetCurrentThreadId());
    va_list a; va_start(a,f); n+=vsnprintf(b+n,sizeof b-n-2,f,a); va_end(a); b[n++]='\n';
    EnterCriticalSection(&trcs); DWORD w; WriteFile(tr,b,n,&w,0); LeaveCriticalSection(&trcs);
}
static const char *modname(void *addr,char *buf,int n){ HMODULE m=0; buf[0]=0;
    if(GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,(LPCSTR)addr,&m)){ char p[MAX_PATH]; GetModuleFileNameA(m,p,MAX_PATH); char*b=strrchr(p,'\\'); snprintf(buf,n,"%s+0x%lx",b?b+1:p,(unsigned long)((char*)addr-(char*)m)); } else snprintf(buf,n,"%p",addr); return buf; }
#define CALLER(buf) modname(__builtin_return_address(0),buf,96)

typedef BOOL (WINAPI *FreeLibrary_t)(HMODULE);
static FreeLibrary_t RealFreeLibrary;
typedef ATOM (WINAPI *RegClassA_t)(const WNDCLASSA*);
typedef ATOM (WINAPI *RegClassExA_t)(const WNDCLASSEXA*);
static RegClassA_t RealRegClassA; static RegClassExA_t RealRegClassExA;
#define MAXCLS 4096
static struct { char name[96]; HINSTANCE hi; HMODULE caller; } cls_tab[MAXCLS]; static int ncls;
static HMODULE module_of(void *addr){ HMODULE m=0; GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,(LPCSTR)addr,&m); return m; }
static void note_class(LPCSTR name, HINSTANCE hi, void *ret){
    if(IS_INTRESOURCE(name)) return;
    HMODULE caller=module_of(ret); int slot=-1;
    for(int k=0;k<ncls;k++){ if(cls_tab[k].name[0] && !strcmp(cls_tab[k].name,name) && cls_tab[k].hi==hi){ cls_tab[k].caller=caller; return; } if(slot<0 && !cls_tab[k].name[0]) slot=k; }
    if(slot<0){ if(ncls>=MAXCLS){ L("class table full!"); return; } slot=ncls++; }
    strncpy(cls_tab[slot].name,name,95); cls_tab[slot].name[95]=0; cls_tab[slot].hi=hi; cls_tab[slot].caller=caller;
    L("RegisterClass '%s' hinst=%p caller=%p", name, hi, (void*)caller);
}
static ATOM WINAPI MyRegClassA(const WNDCLASSA *w){ ATOM a=RealRegClassA(w); note_class(w->lpszClassName,w->hInstance,__builtin_return_address(0)); if(!a) L("  RegisterClassA FAILED err=%lu",GetLastError()); return a; }
static ATOM WINAPI MyRegClassExA(const WNDCLASSEXA *w){ ATOM a=RealRegClassExA(w); note_class(w->lpszClassName,w->hInstance,__builtin_return_address(0)); if(!a) L("  RegisterClassExA FAILED err=%lu",GetLastError()); return a; }

static const char *watch[] = { "LINEUP.DLL","EZSHELL.DLL","UPSTATS.DLL","BBSHELL.DLL","FASTSIM.DLL","BBSIM.DLL",0 };

static DWORD image_size(HMODULE m) {
    IMAGE_DOS_HEADER *d=(IMAGE_DOS_HEADER*)m; IMAGE_NT_HEADERS *n=(IMAGE_NT_HEADERS*)((char*)m+d->e_lfanew);
    return n->OptionalHeader.SizeOfImage;
}
typedef struct { HMODULE m; DWORD size; int n; } Ctx;
static BOOL CALLBACK killwin(HWND h, LPARAM lp) {
    Ctx *c=(Ctx*)lp; DWORD pid; DWORD tid=GetWindowThreadProcessId(h,&pid);
    if(pid!=GetCurrentProcessId()) return TRUE;
    EnumChildWindows(h, killwin, lp);               // children first
    if(tid!=GetCurrentThreadId()) return TRUE;
    ULONG_PTR proc=(ULONG_PTR)GetWindowLongA(h,GWL_WNDPROC), hi=(ULONG_PTR)GetWindowLongA(h,GWL_HINSTANCE);
    if ((proc>=(ULONG_PTR)c->m && proc<(ULONG_PTR)c->m+c->size) || hi==(ULONG_PTR)c->m) {
        char cls[128]="",title[64]=""; GetClassNameA(h,cls,128); GetWindowTextA(h,title,64);
        L("  destroying hwnd=%p class='%s' title='%s' proc=%p", h, cls, title, (void*)proc);
        if (IsWindow(h)) DestroyWindow(h);
        c->n++;
    }
    return TRUE;
}
static BOOL WINAPI MyFreeLibrary(HMODULE m) {
    char path[MAX_PATH]=""; GetModuleFileNameA(m,path,MAX_PATH);
    const char *b=strrchr(path,'\\'); b=b?b+1:path;
    int ours = !_strnicmp(path,"C:\\Sierra\\",10);
    for(int i=0;i<1 && ours;i++) {
        Ctx c={m,image_size(m),0};
        L("FreeLibrary(%s) base=%p size=%lx", b, m, c.size); T("DLL    unload %s base=%p",b,m);
        EnumWindows(killwin,(LPARAM)&c);
        L("  windows destroyed: %d", c.n);
        for(int k=0;k<ncls;k++) if(cls_tab[k].name[0] && (cls_tab[k].caller==m || cls_tab[k].hi==m)) {
            BOOL ok=UnregisterClassA(cls_tab[k].name, cls_tab[k].hi);
            L("  UnregisterClass '%s' -> %d", cls_tab[k].name, ok); cls_tab[k].name[0]=0;
        }
        break;
    }
    return RealFreeLibrary(m);
}


/* ---- generic API hooks: log every interesting call the game makes ---- */
static void hnote(HANDLE h,const char*p); static void on_open(HANDLE h,const char*p);
static HANDLE (WINAPI *R_CreateFileA)(LPCSTR,DWORD,DWORD,LPSECURITY_ATTRIBUTES,DWORD,DWORD,HANDLE);
static HANDLE WINAPI H_CreateFileA(LPCSTR p,DWORD a,DWORD s,LPSECURITY_ATTRIBUTES sa,DWORD d,DWORD f,HANDLE t){ HANDLE h=R_CreateFileA(p,a,s,sa,d,f,t); char c[96]; hnote(h,p); on_open(h,p); T("FILE   %s %s%s -> %s  (by %s)",(a&GENERIC_WRITE)?"write":"read",p,(d==CREATE_NEW||d==CREATE_ALWAYS)?" [create]":"",h==INVALID_HANDLE_VALUE?"FAILED":"ok",CALLER(c)); return h; }
static BOOL (WINAPI *R_DeleteFileA)(LPCSTR);
static BOOL WINAPI H_DeleteFileA(LPCSTR p){ char c[96]; BOOL r=R_DeleteFileA(p); T("FILE   delete %s -> %d (by %s)",p,r,CALLER(c)); return r; }
static HMODULE (WINAPI *R_LoadLibraryA)(LPCSTR);
static HMODULE WINAPI H_LoadLibraryA(LPCSTR p){ char c[96]; HMODULE m=R_LoadLibraryA(p); T("DLL    load %s -> %p (by %s)",p,m,CALLER(c)); return m; }
static HWND (WINAPI *R_CreateWindowExA)(DWORD,LPCSTR,LPCSTR,DWORD,int,int,int,int,HWND,HMENU,HINSTANCE,LPVOID);
static HWND WINAPI H_CreateWindowExA(DWORD ex,LPCSTR cl,LPCSTR nm,DWORD st,int x,int y,int w,int h,HWND par,HMENU mn,HINSTANCE hi,LPVOID lp){ char c[96]; HWND r=R_CreateWindowExA(ex,cl,nm,st,x,y,w,h,par,mn,hi,lp); T("WINDOW create class='%s' title='%s' %dx%d -> %p (by %s)",IS_INTRESOURCE(cl)?"#atom":cl,nm?nm:"",w,h,r,CALLER(c)); return r; }
static BOOL (WINAPI *R_DestroyWindow)(HWND);
static BOOL WINAPI H_DestroyWindow(HWND h){ char cl[64]="",ti[64]=""; if(IsWindow(h)){GetClassNameA(h,cl,64);GetWindowTextA(h,ti,64);} T("WINDOW destroy %p class='%s' title='%s'",h,cl,ti); return R_DestroyWindow(h); }
static UINT_PTR (WINAPI *R_SetTimer)(HWND,UINT_PTR,UINT,TIMERPROC);
static UINT_PTR WINAPI H_SetTimer(HWND h,UINT_PTR id,UINT ms,TIMERPROC fn){ char c[96]; T("TIMER  set hwnd=%p id=%lu every %ums (by %s)",h,(unsigned long)id,ms,CALLER(c)); return R_SetTimer(h,id,ms,fn); }
static BOOL (WINAPI *R_KillTimer)(HWND,UINT_PTR);
static BOOL WINAPI H_KillTimer(HWND h,UINT_PTR id){ T("TIMER  kill hwnd=%p id=%lu",h,(unsigned long)id); return R_KillTimer(h,id); }
static int (WINAPI *R_MessageBoxA)(HWND,LPCSTR,LPCSTR,UINT);
static int WINAPI H_MessageBoxA(HWND h,LPCSTR t,LPCSTR c2,UINT u){ char c[96]; T("DIALOG messagebox '%s' / '%s' (by %s)",c2?c2:"",t?t:"",CALLER(c)); return R_MessageBoxA(h,t,c2,u); }
static void (WINAPI *R_PostQuitMessage)(int);
static void WINAPI H_PostQuitMessage(int n){ char c[96]; T("APP    PostQuitMessage(%d) (by %s)",n,CALLER(c)); R_PostQuitMessage(n); }
static void (WINAPI *R_ExitProcess)(UINT);
static void WINAPI H_ExitProcess(UINT n){ char c[96]; T("APP    ExitProcess(%u) (by %s)",n,CALLER(c)); R_ExitProcess(n); }
static HANDLE (WINAPI *R_CreateThread)(LPSECURITY_ATTRIBUTES,SIZE_T,LPTHREAD_START_ROUTINE,LPVOID,DWORD,LPDWORD);
static HANDLE WINAPI H_CreateThread(LPSECURITY_ATTRIBUTES a,SIZE_T s,LPTHREAD_START_ROUTINE f,LPVOID p,DWORD fl,LPDWORD id){ char c[96],d[96]; T("THREAD create start=%s (by %s)",modname((void*)f,d,96),CALLER(c)); return R_CreateThread(a,s,f,p,fl,id); }
static DWORD (WINAPI *R_WaitForSingleObject)(HANDLE,DWORD);
static DWORD WINAPI H_WaitForSingleObject(HANDLE h,DWORD ms){ if(ms>=500){ char c[96]; T("WAIT   WaitForSingleObject(%p, %lums) (by %s)",h,ms,CALLER(c)); DWORD r=R_WaitForSingleObject(h,ms); T("WAIT   ...returned %lu",r); return r;} return R_WaitForSingleObject(h,ms); }
static void (WINAPI *R_Sleep)(DWORD);
static void WINAPI H_Sleep(DWORD ms){ if(ms>=1000){ char c[96]; T("WAIT   Sleep(%lu) (by %s)",ms,CALLER(c)); } R_Sleep(ms); }
static BOOL (WINAPI *R_CreateProcessA)(LPCSTR,LPSTR,LPSECURITY_ATTRIBUTES,LPSECURITY_ATTRIBUTES,BOOL,DWORD,LPVOID,LPCSTR,LPSTARTUPINFOA,LPPROCESS_INFORMATION);
static BOOL WINAPI H_CreateProcessA(LPCSTR a,LPSTR b,LPSECURITY_ATTRIBUTES c1,LPSECURITY_ATTRIBUTES c2,BOOL i,DWORD f,LPVOID e,LPCSTR d,LPSTARTUPINFOA si,LPPROCESS_INFORMATION pi){ T("APP    CreateProcess %s %s",a?a:"",b?b:""); return R_CreateProcessA(a,b,c1,c2,i,f,e,d,si,pi); }

/* ---- disk-space + write-failure diagnostics ---- */
#define MAXH 512
static struct { HANDLE h; char path[200]; } htab[MAXH]; static int hn;
static void hnote(HANDLE h,const char*p){ if(h==INVALID_HANDLE_VALUE) return; int i=hn++%MAXH; htab[i].h=h; strncpy(htab[i].path,p,199); htab[i].path[199]=0; }
static const char* hname(HANDLE h){ for(int k=0;k<MAXH;k++) if(htab[k].h==h) return htab[k].path; return "?"; }
static BOOL (WINAPI *R_WriteFile)(HANDLE,LPCVOID,DWORD,LPDWORD,LPOVERLAPPED);
static BOOL WINAPI H_WriteFile(HANDLE h,LPCVOID b,DWORD n,LPDWORD w,LPOVERLAPPED o){ BOOL r=R_WriteFile(h,b,n,w,o); DWORD e=GetLastError(); if(!r||(w&&*w!=n)){ char c[96]; T("WRITEFAIL %s want=%lu wrote=%lu err=%lu (by %s)",hname(h),n,w?*w:0,e,CALLER(c)); } SetLastError(e); return r; }
static BOOL (WINAPI *R_GetDiskFreeSpaceA)(LPCSTR,LPDWORD,LPDWORD,LPDWORD,LPDWORD);
static BOOL WINAPI H_GetDiskFreeSpaceA(LPCSTR root,LPDWORD spc,LPDWORD bps,LPDWORD fc,LPDWORD tc){
    BOOL r=R_GetDiskFreeSpaceA(root,spc,bps,fc,tc); char c[96];
    if(r){ unsigned long long fb=(unsigned long long)*spc**bps**fc; int clamp=GetFileAttributesA("clamp.on")!=INVALID_FILE_ATTRIBUTES;
        T("DISK   GetDiskFreeSpaceA(%s) spc=%lu bps=%lu freeclusters=%lu total=%lu => free %llu MB%s (by %s)",root?root:"(cwd)",*spc,*bps,*fc,*tc,fb>>20,clamp?" [clamping to <2GB]":"",CALLER(c));
        if(clamp){ unsigned long long cl=(unsigned long long)*spc**bps; if(cl && fb>0x7FFF0000ULL){ *fc=(DWORD)(0x7FFF0000ULL/cl); } if(cl && (unsigned long long)*tc*cl>0x7FFF0000ULL) *tc=(DWORD)(0x7FFF0000ULL/cl); } }
    else T("DISK   GetDiskFreeSpaceA(%s) FAILED err=%lu (by %s)",root?root:"(cwd)",GetLastError(),CALLER(c));
    return r; }


static void game_site(char *out,int n){ void *fr[24]; USHORT k=CaptureStackBackTrace(1,24,fr,0); out[0]=0;
    for(int i=0;i<k;i++){ HMODULE m=0; if(GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,(LPCSTR)fr[i],&m)&&m){ char p[MAX_PATH]; GetModuleFileNameA(m,p,MAX_PATH); if(!_strnicmp(p,"C:\\Sierra\\",10)&&_stricmp(strrchr(p,'\\')+1,"bbfix.dll")){ snprintf(out,n,"%s+0x%lx",strrchr(p,'\\')+1,(unsigned long)((char*)fr[i]-(char*)m)); return; } } }
    snprintf(out,n,"?"); }
/* ---- open-handle accounting (finds leaks) ---- */
#define OH 16384
static struct { HANDLE h; char path[110]; char site[28]; unsigned seq; DWORD tick; } oh[OH]; static unsigned ohseq;
static void on_open(HANDLE h,const char*p){ if(h==INVALID_HANDLE_VALUE||!h) return; unsigned i=((unsigned)(size_t)h>>2)&(OH-1); oh[i].h=h; strncpy(oh[i].path,p,109); oh[i].path[109]=0; oh[i].site[0]=0; oh[i].seq=++ohseq; oh[i].tick=GetTickCount(); }
static void on_close(HANDLE h){ unsigned i=((unsigned)(size_t)h>>2)&(OH-1); if(oh[i].h==h){ oh[i].h=0; oh[i].path[0]=0; } }
static HANDLE (WINAPI *R_CreateFileW)(LPCWSTR,DWORD,DWORD,LPSECURITY_ATTRIBUTES,DWORD,DWORD,HANDLE);
static HANDLE WINAPI H_CreateFileW(LPCWSTR p,DWORD a,DWORD s,LPSECURITY_ATTRIBUTES sa,DWORD d,DWORD f,HANDLE t){ HANDLE h=R_CreateFileW(p,a,s,sa,d,f,t); char n[260]=""; if(p) WideCharToMultiByte(CP_ACP,0,p,-1,n,259,0,0); on_open(h,n); hnote(h,n); if(h==INVALID_HANDLE_VALUE){ char c[96]; T("FILEW  open %s -> FAILED err=%lu (by %s)",n,GetLastError(),CALLER(c)); }
    else if(strstr(n,"Stats\\")||strstr(n,"stats\\")){ static int k; if(k++<4000){ char c[96]; T("FILEW  open %s h=%p access=%08lx share=%lu (by %s)",n,h,a,s,CALLER(c)); } }
    return h; }
static BOOL (WINAPI *R_CloseHandle)(HANDLE);
static BOOL WINAPI H_CloseHandle(HANDLE h){ unsigned i=((unsigned)(size_t)h>>2)&(OH-1); int tracked=(oh[i].h==h); char nm[110]; strcpy(nm,tracked?oh[i].path:""); BOOL r=R_CloseHandle(h); if(r) on_close(h); { static int k; if(tracked&&strstr(nm,"Stats")&&k++<15){ char c[96]; T("CLOSE  %s h=%p (by %s)",nm,h,CALLER(c)); } } return r; }
static DWORD WINAPI HandleWatch(LPVOID p){
    typedef BOOL (WINAPI *GPHC)(HANDLE,PDWORD); GPHC gp=(GPHC)GetProcAddress(GetModuleHandleA("kernel32.dll"),"GetProcessHandleCount");
    typedef intptr_t (__cdecl *GOH)(int); typedef int (__cdecl *CL)(int);
    HMODULE cr=GetModuleHandleA("msvcrt.dll"); GOH goh=cr?(GOH)GetProcAddress(cr,"_get_osfhandle"):0; CL clo=cr?(CL)GetProcAddress(cr,"_close"):0; int tick=0;
    for(;;){ Sleep(5000); tick++;
        int used=0, swept=0;
        if(goh&&clo){ struct { int fd; unsigned seq; DWORD tick; } v[2048]; int nv=0; DWORD now=GetTickCount();
            for(int fd=3; fd<2048; fd++){ intptr_t h=goh(fd); if(h==-1||h==0||h==-2) continue; used++;
                unsigned i=((unsigned)h>>2)&(OH-1); if(oh[i].h==(HANDLE)h && strstr(oh[i].path,"tats") && strstr(oh[i].path,".dat") ){ v[nv].fd=fd; v[nv].seq=oh[i].seq; v[nv].tick=oh[i].tick; nv++; } }
            for(int a=1;a<nv;a++){ int f=v[a].fd; unsigned q=v[a].seq; DWORD t=v[a].tick; int b=a-1; while(b>=0&&v[b].seq>q){ v[b+1]=v[b]; b--; } v[b+1].fd=f; v[b+1].seq=q; v[b+1].tick=t; }
            const int KEEP_OLD=2; const DWORD MAXAGE=90000;
            for(int a=KEEP_OLD; a<nv; a++) if(now-v[a].tick>MAXAGE){ clo(v[a].fd); swept++; } }
        if(swept && (tick%6==0 || swept>20)) T("SWEEP  closed %d stale stats descriptors; crt_fds_in_use=%d",swept,used);
        if(tick%3!=0) continue;
        DWORD tot=0; if(gp) gp(GetCurrentProcess(),&tot); T("CRTFDS in_use=%d",used);
        static char seen[8][110]; static int cnt[8]; int ns=0; memset(cnt,0,sizeof cnt); memset(seen,0,sizeof seen); int open=0;
        for(int i=0;i<OH;i++) if(oh[i].h){ open++; int k; for(k=0;k<ns;k++) if(!strcmp(seen[k],oh[i].path)){cnt[k]++;break;} if(k==ns&&ns<8){ strcpy(seen[ns],oh[i].path); cnt[ns]=1; ns++; } }
        char b[600]; int n=snprintf(b,sizeof b,"HANDLES process=%lu tracked_files_open=%d top:",tot,open); for(int k=0;k<ns&&n<500;k++) n+=snprintf(b+n,sizeof b-n," [%s x%d]",strrchr(seen[k],'\\')?strrchr(seen[k],'\\')+1:seen[k],cnt[k]); T("%s",b);
        { static char ss[8][28]; static int sc[8]; int nn=0; memset(sc,0,sizeof sc); memset(ss,0,sizeof ss); for(int i=0;i<OH;i++) if(oh[i].h && oh[i].site[0]){ int k; for(k=0;k<nn;k++) if(!strcmp(ss[k],oh[i].site)){sc[k]++;break;} if(k==nn&&nn<8){ strcpy(ss[nn],oh[i].site); sc[nn]=1; nn++; } } if(nn){ char b2[300]; int m=snprintf(b2,sizeof b2,"STATSITES open stats handles by opener:"); for(int k=0;k<nn;k++) m+=snprintf(b2+m,sizeof b2-m," [%s x%d]",ss[k],sc[k]); T("%s",b2);} } }
    return 0; }

/* ---- CRT leak control: the game fopen()s / _open()s the season stats file once per game and never closes it.
   After 2048 leaked descriptors the C runtime refuses new files ("Error writing association data"). We close stale ones. ---- */
static int (__cdecl *R_open)(const char*,int,int);
static int (__cdecl *R_close)(int);
static int (__cdecl *R_sopen)(const char*,int,int,int);
static void* (__cdecl *R_fopen)(const char*,const char*);
static int (__cdecl *R_fclose)(void*);
#define FDT 4096
static struct { void *h; int kind; void *site; unsigned seq; } fdt[FDT]; static unsigned fdseq; static CRITICAL_SECTION fdcs; static int fdcs_init;
static int is_stats(const char*p){ if(!p) return 0; const char*b=strrchr(p,'\\'); b=b?b+1:p; const char*s2=strrchr(p,'/'); if(s2&&s2+1>b) b=s2+1; size_t n=strlen(b); return n>4 && !_strnicmp(b,"mlbpa",5) && !_stricmp(b+n-4,".dat"); }
static void fd_init(void){ if(!fdcs_init){ InitializeCriticalSection(&fdcs); fdcs_init=1; } }
static void track(void *h,int kind,void *site,const char*p,const char*what){
    fd_init(); char c[96]; EnterCriticalSection(&fdcs);
    int slot=-1; for(int k=0;k<FDT;k++) if(!fdt[k].h){ slot=k; break; }
    if(slot>=0){ fdt[slot].h=h; fdt[slot].kind=kind; fdt[slot].site=site; fdt[slot].seq=++fdseq; }
    int cnt=0; for(int k=0;k<FDT;k++) if(fdt[k].h && fdt[k].site==site && fdt[k].kind==kind) cnt++;
    int closed=0; const int KEEP=1000000;
    while(cnt>KEEP){ int old=-1; unsigned best=0xFFFFFFFF; for(int k=0;k<FDT;k++) if(fdt[k].h && fdt[k].site==site && fdt[k].kind==kind && fdt[k].seq<best){best=fdt[k].seq; old=k;} if(old<0) break;
        if(kind==0) R_close((int)(intptr_t)fdt[old].h); else R_fclose(fdt[old].h); fdt[old].h=0; cnt--; closed++; }
    LeaveCriticalSection(&fdcs);
    static int lg; if(1) T("CRTFD  %s(%s) outstanding_from_site=%d%s (by %s)",what,p,cnt,closed?" [closed stale]":"",modname(site,c,96)); }
static void untrack(void *h,int kind){ if(!fdcs_init) return; EnterCriticalSection(&fdcs); for(int k=0;k<FDT;k++) if(fdt[k].h==h && fdt[k].kind==kind){ fdt[k].h=0; break; } LeaveCriticalSection(&fdcs); }
static int __cdecl H_open(const char*p,int f,int m){ int fd=R_open(p,f,m); if(fd>=0 && is_stats(p)) track((void*)(intptr_t)(fd+1),0,__builtin_return_address(0),p,"_open"); return fd; }
static int __cdecl H_sopen(const char*p,int f,int sh,int m){ int fd=R_sopen(p,f,sh,m); if(fd>=0 && is_stats(p)) track((void*)(intptr_t)(fd+1),0,__builtin_return_address(0),p,"_sopen"); return fd; }
static int __cdecl H_close(int fd){ untrack((void*)(intptr_t)(fd+1),0); return R_close(fd); }
static void* __cdecl H_fopen(const char*p,const char*m){ void *f=R_fopen(p,m); if(f && is_stats(p)) track(f,1,__builtin_return_address(0),p,"fopen"); return f; }
static int __cdecl H_fclose(void*f){ untrack(f,1); return R_fclose(f); }
static struct { const char *dll,*name; void *hook; void **real; } HK[]={
 {"msvcrt.dll","_open",H_open,(void**)&R_open},{"msvcrt.dll","_sopen",H_sopen,(void**)&R_sopen},{"msvcrt.dll","_close",H_close,(void**)&R_close},{"msvcrt.dll","fopen",H_fopen,(void**)&R_fopen},{"msvcrt.dll","fclose",H_fclose,(void**)&R_fclose},
 {"KERNEL32.dll","CreateFileW",H_CreateFileW,(void**)&R_CreateFileW},{"KERNEL32.dll","CloseHandle",H_CloseHandle,(void**)&R_CloseHandle},
 {"KERNEL32.dll","WriteFile",H_WriteFile,(void**)&R_WriteFile},{"KERNEL32.dll","GetDiskFreeSpaceA",H_GetDiskFreeSpaceA,(void**)&R_GetDiskFreeSpaceA},
 {"KERNEL32.dll","CreateFileA",H_CreateFileA,(void**)&R_CreateFileA},{"KERNEL32.dll","DeleteFileA",H_DeleteFileA,(void**)&R_DeleteFileA},
 {"KERNEL32.dll","LoadLibraryA",H_LoadLibraryA,(void**)&R_LoadLibraryA},{"KERNEL32.dll","CreateThread",H_CreateThread,(void**)&R_CreateThread},
 {"KERNEL32.dll","WaitForSingleObject",H_WaitForSingleObject,(void**)&R_WaitForSingleObject},{"KERNEL32.dll","Sleep",H_Sleep,(void**)&R_Sleep},
 {"KERNEL32.dll","ExitProcess",H_ExitProcess,(void**)&R_ExitProcess},{"KERNEL32.dll","CreateProcessA",H_CreateProcessA,(void**)&R_CreateProcessA},
 {"USER32.dll","CreateWindowExA",H_CreateWindowExA,(void**)&R_CreateWindowExA},{"USER32.dll","DestroyWindow",H_DestroyWindow,(void**)&R_DestroyWindow},
 {"USER32.dll","SetTimer",H_SetTimer,(void**)&R_SetTimer},{"USER32.dll","KillTimer",H_KillTimer,(void**)&R_KillTimer},
 {"USER32.dll","MessageBoxA",H_MessageBoxA,(void**)&R_MessageBoxA},{"USER32.dll","PostQuitMessage",H_PostQuitMessage,(void**)&R_PostQuitMessage}};
static LONG CALLBACK VEH(EXCEPTION_POINTERS *ep){ static int n; static void *last; DWORD c=ep->ExceptionRecord->ExceptionCode;
    if(c==0xC0000005 || c==0xC000001D || c==0xC0000094 || c==0xC00000FD){ void*a=ep->ExceptionRecord->ExceptionAddress; if(a!=last && n<400){ char b[96]; last=a; n++; T("CRASH  exception %08lx at %s  (fault addr %p)",c,modname(a,b,96),c==0xC0000005&&ep->ExceptionRecord->NumberParameters>1?(void*)ep->ExceptionRecord->ExceptionInformation[1]:0);} }
    return EXCEPTION_CONTINUE_SEARCH; }
static DWORD WINAPI Heartbeat(LPVOID p){ for(;;){ Sleep(5000); HWND fg=GetForegroundWindow(); T("BEAT   alive; top window='%s'",""); (void)fg; } return 0; }
static void patch_iat(HMODULE m) {
    if(!m || m==GetModuleHandleA("bbfix.dll")) return;
    IMAGE_DOS_HEADER *d=(IMAGE_DOS_HEADER*)m; if(d->e_magic!=IMAGE_DOS_SIGNATURE) return;
    IMAGE_NT_HEADERS *n=(IMAGE_NT_HEADERS*)((char*)m+d->e_lfanew);
    IMAGE_DATA_DIRECTORY dd=n->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    if(!dd.VirtualAddress) return;
    for(IMAGE_IMPORT_DESCRIPTOR *id=(IMAGE_IMPORT_DESCRIPTOR*)((char*)m+dd.VirtualAddress); id->Name; id++) {
        int isk=!_stricmp((char*)m+id->Name,"KERNEL32.dll"), isu=!_stricmp((char*)m+id->Name,"USER32.dll");
        int ism=!_stricmp((char*)m+id->Name,"msvcrt.dll");
        if(!isk && !isu && !ism) continue;
        IMAGE_THUNK_DATA *ot=(IMAGE_THUNK_DATA*)((char*)m+(id->OriginalFirstThunk?id->OriginalFirstThunk:id->FirstThunk));
        IMAGE_THUNK_DATA *ft=(IMAGE_THUNK_DATA*)((char*)m+id->FirstThunk);
        for(;ot->u1.AddressOfData;ot++,ft++) {
            if(ot->u1.Ordinal & 0x80000000) continue;
            IMAGE_IMPORT_BY_NAME *ibn=(IMAGE_IMPORT_BY_NAME*)((char*)m+ot->u1.AddressOfData);
            DWORD repl=0; const char *nm=(char*)ibn->Name;
            if(isk && !strcmp(nm,"FreeLibrary")){ if(!RealFreeLibrary) RealFreeLibrary=(FreeLibrary_t)ft->u1.Function; repl=(DWORD)MyFreeLibrary; }
            else if(isu && !strcmp(nm,"RegisterClassA")){ if(!RealRegClassA) RealRegClassA=(RegClassA_t)ft->u1.Function; repl=(DWORD)MyRegClassA; }
            else if(isu && !strcmp(nm,"RegisterClassExA")){ if(!RealRegClassExA) RealRegClassExA=(RegClassExA_t)ft->u1.Function; repl=(DWORD)MyRegClassExA; }
            if(!repl) for(unsigned k=0;k<sizeof HK/sizeof*HK;k++) if(!_stricmp((char*)m+id->Name,HK[k].dll) && !strcmp(nm,HK[k].name)){ if(!*HK[k].real) *HK[k].real=(void*)ft->u1.Function; repl=(DWORD)HK[k].hook; break; }
            if(!repl) continue;
            DWORD old; VirtualProtect(&ft->u1.Function,4,PAGE_READWRITE,&old);
            ft->u1.Function=repl;
            VirtualProtect(&ft->u1.Function,4,old,&old);
            char p[MAX_PATH]; GetModuleFileNameA(m,p,MAX_PATH); L("patched %s IAT in %s", nm, p);
        }
    }
}
static void patch_all(void) {
    HANDLE s=CreateToolhelp32Snapshot(TH32CS_SNAPMODULE,GetCurrentProcessId()); MODULEENTRY32 e={sizeof e};
    if(s!=INVALID_HANDLE_VALUE){ if(Module32First(s,&e)) do { if(e.szExePath[0]=='C'||e.szExePath[0]=='c') patch_iat((HMODULE)e.modBaseAddr); } while(Module32Next(s,&e)); CloseHandle(s);}
}
typedef struct { ULONG Flags; void *FullDllName; void *BaseDllName; PVOID DllBase; ULONG SizeOfImage; } LDR_NOTE;
typedef VOID (CALLBACK *LDR_CB)(ULONG reason, LDR_NOTE *data, PVOID ctx);
static VOID CALLBACK on_load(ULONG reason, LDR_NOTE *d, PVOID ctx) { if(reason==1 && d){ char p[MAX_PATH]; GetModuleFileNameA((HMODULE)d->DllBase,p,MAX_PATH); if(!_strnicmp(p,"C:\\Sierra",10)) T("DLL    loaded %s at %p",strrchr(p,'\\')+1,d->DllBase); patch_iat((HMODULE)d->DllBase);} }

BOOL WINAPI DllMain(HINSTANCE h, DWORD why, LPVOID r) {
    if(why==DLL_PROCESS_ATTACH) {
        char p[MAX_PATH]; GetModuleFileNameA(h,p,MAX_PATH); char *s=strrchr(p,'\\'); if(s) strcpy(s+1,"bbfix.log");
        lg=fopen(p,"w"); L("bbfix loaded");
        InitializeCriticalSection(&trcs); strcpy(s+1,"bbtrace.log"); tr=CreateFileA(p,GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE,0,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,0);
        T("=== BBPRO98 action trace started (pid %lu) ===",GetCurrentProcessId()); AddVectoredExceptionHandler(1,VEH); CreateThread(0,0,HandleWatch,0,0,0);
        patch_all();
        typedef LONG (NTAPI *Reg_t)(ULONG,LDR_CB,PVOID,PVOID*);
        Reg_t reg=(Reg_t)GetProcAddress(GetModuleHandleA("ntdll.dll"),"LdrRegisterDllNotification");
        PVOID cookie; if(reg) L("LdrRegisterDllNotification -> %ld", reg(0,on_load,0,&cookie)); else L("no LdrRegisterDllNotification");
    }
    return TRUE;
}
