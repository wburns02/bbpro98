// bbfix.dll: emulate Win9x tolerance for windows left behind by unloaded shell DLLs.
// Hooks FreeLibrary (via IAT of every game module) and destroys windows owned by the DLL
// (wndproc inside its image, or hInstance == module) BEFORE it is unmapped.
#include <windows.h>
#include <tlhelp32.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

static FILE *lg;
static char ini_path[MAX_PATH];
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
/* ---- text-draw trace (off by default). bbfix.ini [trace] text=1 match=Avg   or env BBFIX_TRACE_TEXT=1 BBFIX_TRACE_MATCH=Avg.
   When a drawn string contains match (empty = every string), logs the API, string, caller and a raw stack walk of return
   addresses (values inside game modules preceded by a call opcode) to bbtrace.log. Finds the drawing function in one run. */
static int tx_on,tx_cell,tx_draw; static char tx_match[64]; static unsigned tx_cnt;
static int looks_like_ret(uint32_t v){ if((v&0xfff)<6) return 0; if(IsBadReadPtr((void*)(uintptr_t)(v-6),6)) return 0; uint8_t *p=(uint8_t*)(uintptr_t)v;
    return p[-5]==0xe8 || (p[-6]==0xff&&p[-5]==0x15) || (p[-2]==0xff&&(p[-1]&0xf8)==0xd0); }
static void stack_walk(const uint32_t *sp,char *w,int k,int cap){ char c[96]; int found=0;
    for(int i=0;i<256&&found<12&&k<cap-100;i++){ if(IsBadReadPtr(sp+i,4)) break; uint32_t v=sp[i]; HMODULE m=0;
        if(v<0x10000||!GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,(LPCSTR)(uintptr_t)v,&m)||!m) continue;
        char p[MAX_PATH]; GetModuleFileNameA(m,p,MAX_PATH); if(_strnicmp(p,"C:\\Sierra",9)||!_stricmp(strrchr(p,'\\')+1,"bbfix.dll")) continue;
        if(!looks_like_ret(v)) continue; k+=snprintf(w+k,cap-k," %s(va %08x)",modname((void*)(uintptr_t)v,c,96),v); found++; } }
static void text_trace(const char *api,const char *s,int n,void *ret){
    if(!tx_on||!s||IsBadReadPtr(s,1)) return; char b[160]; if(n<0) n=(int)strnlen(s,150); if(n>150) n=150; memcpy(b,s,n); b[n]=0;
    if(tx_match[0] && !strstr(b,tx_match)) return; if(tx_cnt++>3000) return;
    char c[96],w[700]; int k=snprintf(w,sizeof w,"TEXT   %s '%s' ret=%s stack:",api,b,modname(ret,c,96));
    stack_walk((uint32_t*)__builtin_frame_address(0),w,k,sizeof w);
    T("%s",w); }
static int (WINAPI *R_DrawTextA)(HDC,LPCSTR,int,LPRECT,UINT);
static int WINAPI H_DrawTextA(HDC dc,LPCSTR s,int n,LPRECT r,UINT f){ text_trace("DrawTextA",s,n,__builtin_return_address(0)); return R_DrawTextA(dc,s,n,r,f); }
static BOOL (WINAPI *R_TextOutA)(HDC,int,int,LPCSTR,int);
static BOOL WINAPI H_TextOutA(HDC dc,int x,int y,LPCSTR s,int n){ text_trace("TextOutA",s,n,__builtin_return_address(0)); return R_TextOutA(dc,x,y,s,n); }
static BOOL (WINAPI *R_ExtTextOutA)(HDC,int,int,UINT,const RECT*,LPCSTR,UINT,const INT*);
static BOOL WINAPI H_ExtTextOutA(HDC dc,int x,int y,UINT o,const RECT*r,LPCSTR s,UINT n,const INT*d){ if(!(o&ETO_GLYPH_INDEX)) text_trace("ExtTextOutA",s,(int)n,__builtin_return_address(0)); return R_ExtTextOutA(dc,x,y,o,r,s,n,d); }
static void trace_cfg(void){ char e[64]; tx_on=GetPrivateProfileIntA("trace","text",0,ini_path); tx_cell=GetPrivateProfileIntA("trace","cell",0,ini_path); tx_draw=GetPrivateProfileIntA("trace","draw",0,ini_path); GetPrivateProfileStringA("trace","match","",tx_match,sizeof tx_match,ini_path);
    if(GetEnvironmentVariableA("BBFIX_TRACE_TEXT",e,sizeof e)) tx_on=atoi(e); if(GetEnvironmentVariableA("BBFIX_TRACE_MATCH",e,sizeof e)){ strncpy(tx_match,e,63); tx_match[63]=0; }
    if(tx_on) T("TRACE  text trace ON match='%s'",tx_match); }
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
 {"USER32.dll","DrawTextA",H_DrawTextA,(void**)&R_DrawTextA},{"GDI32.dll","TextOutA",H_TextOutA,(void**)&R_TextOutA},{"GDI32.dll","ExtTextOutA",H_ExtTextOutA,(void**)&R_ExtTextOutA},
 {"USER32.dll","MessageBoxA",H_MessageBoxA,(void**)&R_MessageBoxA},{"USER32.dll","PostQuitMessage",H_PostQuitMessage,(void**)&R_PostQuitMessage}};

/* ---- BBShell.dll widening hooks (League Statistics screen: 4 extra stat columns) ----
   BBShell.dll is mapped and freed per screen, so the hooks are applied in-memory on every load (on_load) and the
   on-disk DLL stays pristine. All-or-nothing: every site is verified against its expected original bytes first; if any
   byte differs nothing is written. Hooks are jmp detours into naked stubs that save flags + all registers (pushfd,
   pushad), call a C handler with a Regs frame, restore, run the displaced instructions the handler did not emulate,
   and jmp back. Handlers see the site's own stack frame at stk[k] == [site_esp + 4*k] (no "+4 for our call"), and
   only the registers a handler writes into Regs change, so a stray clobber (edx etc.) cannot happen.
   Liveness of every site is recorded in work/NOTES_widen.md. Config: bbfix.ini [widen] enable=1 bat=a,b,c,d pit=a,b,c,d */
typedef struct { uint32_t edi,esi,ebp,esp_,ebx,edx,ecx,eax,efl; uint32_t stk[16]; } Regs;
static uint32_t ext_tab[2][4]={{49,50,57,52},{262,251,276,277}};   /* stat ids for ext columns: [view][col] */
static uint32_t ext_id(uint32_t view,uint32_t k){ return (view<2&&k<4)?ext_tab[view][k]:0; }
#define TC __attribute__((thiscall))
typedef void (TC *tc2_t)(void *self,int a,int b);
#define HANDLER __attribute__((used,force_align_arg_pointer))
/* site 1, 6805cae2: movsx ecx,bp / push eax / mov edx,[esi+ecx*4+0x6c]. Slots 0..9 as before, 10..13 -> ext id. */
HANDLER void h_slot(Regs *r){ int cx=(int16_t)r->ebp; r->ecx=(uint32_t)cx;
    r->edx = cx<10 ? *(uint32_t*)(r->esi+cx*4+0x6c) : ext_id(*(uint32_t*)(r->esi+0xe8),(uint32_t)(cx-10)); }
/* site 4, 6805cbe7: mov eax,[ebp] / mov ecx,ebp / add ebp,4. Header ids 0x1d..0x20 -> ext id; block = param_5 = [esp+0x28] */
HANDLER void h_hdr(Regs *r){ uint32_t p=r->ebp; r->eax=*(uint32_t*)p; r->ecx=p; r->ebp=p+4;
    uint32_t k=r->esi-0x1d; if(k<4) r->eax=ext_id(r->stk[0x28/4],k); }
/* site 5, 6800ec2c: mov cx,bx / sub cx,9. Cell index = gadget id-9, or id-0x26 for ext ids >= 0x30. Only cx changes. */
HANDLER void h_cell(Regs *r){ if(tx_cell){ static int n; if(n<8){ n++; char w[700]; int k=snprintf(w,sizeof w,"CELL   cb gadget=%04x stack:",r->ebx&0xffff); stack_walk(r->stk,w,k,sizeof w); T("%s",w);} } uint32_t bx=r->ebx&0xffff, cx=bx>=0x30?bx-0x26:bx-9; r->ecx=(r->ecx&0xffff0000u)|(cx&0xffff); }
/* site 6, 6800d3aa: after the 9..0x12 init loop, init body gadgets 0x30..0x33 the same way (2 stack args, ret 8). */
HANDLER void h_init(Regs *r){ (void)r; tc2_t f1=(tc2_t)0x680436c0, f2=(tc2_t)0x68043400;
    for(int id=0x30;id<0x34;id++){ f1((void*)0x6808dd10,id,0x6800ea40); f2((void*)0x6808dd10,id,0); } }
uint32_t resume_slot,resume_hdr,resume_cell,resume_init;
extern void stub_slot(void),stub_hdr(void),stub_cell(void),stub_init(void);
#define STUB(n,tail) __asm__(".text\n.globl _stub_" #n "\n_stub_" #n ":\n pushfl\n pushal\n pushl %esp\n call _h_" #n "\n addl $4,%esp\n popal\n popfl\n" tail " jmp *_resume_" #n "\n")
STUB(slot," pushl %eax\n");            /* displaced: push eax (reordered after movsx/mov, independent of them) */
STUB(hdr,"");
STUB(cell,"");
STUB(init," pushl $0\n movl 0x34(%esi),%eax\n");   /* displaced: push 0 / mov eax,[esi+0x34] */
typedef struct { const char *name; uint32_t va; int n; uint8_t orig[8]; int immoff; uint8_t immnew; void (*stub)(void); uint32_t *resume; int call; } Site;
static Site sites[]={
 {"slot",   0x6805cae2,8,{0x0f,0xbf,0xcd,0x50,0x8b,0x54,0x8e,0x6c},0,0,stub_slot,&resume_slot},
 {"bound",  0x6805cafb,4,{0x66,0x83,0xfd,0x0a},3,0x0e,0,0},       /* cmp bp,10 -> 14 */
 {"term",   0x6805cb0b,2,{0x6a,0x0a},1,0x0e,0,0},                 /* push 10 -> 14 */
 {"hdr",    0x6805cbe7,8,{0x8b,0x45,0x00,0x8b,0xcd,0x83,0xc5,0x04},0,0,stub_hdr,&resume_hdr},
 {"cell",   0x6800ec2c,7,{0x66,0x8b,0xcb,0x66,0x83,0xe9,0x09},0,0,stub_cell,&resume_cell},
 {"init",   0x6800d3aa,5,{0x6a,0x00,0x8b,0x46,0x34},0,0,stub_init,&resume_init},
 {"hdrrng", 0x6800d442,2,{0x6a,0x1c},1,0x20,0,0},                /* header range 0x13..0x1c -> 0x20 */
 {"click",  0x6800d74f,4,{0x66,0x83,0xfe,0x1c},3,0x20,0,0},
 {"vt8",    0x68081f7c,4,{0xf0,0x5c,0x07,0x68},0,0,0,0,2},          /* vtable slot +4 (redraw) of the stats list frame, gadget id 8: 68075cf0 -> w_vt8 */
 {"rd1",    0x680721d7,5,{0xe8},0,0,0,0,1},                      /* the 3 calls to GadgetMgr_RedrawList 68043cb0 go through w_redraw so ext gadgets redraw/scroll/sort too */
 {"rd2",    0x68072227,5,{0xe8},0,0,0,0,1},
 {"rd3",    0x68072255,5,{0xe8},0,0,0,0,1}};      /* header click handler FUN_6800d740: cmp si,0x1c -> 0x20, so ext headers sort */
#define NSITE ((int)(sizeof sites/sizeof*sites))
/* wrapper for 68043cb0 (thiscall, 4 stack args id,a,flag,b, ret 0x10; verified from the disassembly, Ghidra had 3): original ring walk, then the same for ext body gadgets 0x30..0x33 when the list is the stats grid (group id 9) */
static int rd_ext=1;
/* ext body gadgets are not in the list's gadget ring, so sort/scroll redraws (which redraw gadget 8 and its ring) miss them: redraw them after gadget 8 */
static void TC w_vt8(void *self){
    ((void (TC*)(void*))0x68075cf0)(self);
    if(!rd_ext||*(uint16_t*)((uint8_t*)self+0xc)!=8) return;
    void *mgr=(void*)0x6808dd10; uint32_t *vt=*(uint32_t**)mgr;
    for(int id=0x30;id<0x34;id++){ void **g=((void**(TC*)(void*,int))vt[0x48/4])(mgr,id); if(!g||IsBadReadPtr(g,4)) continue;
        uint32_t *gv=(uint32_t*)*g; if(((short(TC*)(void*))gv[0x14/4])(g)!=8) continue; ((void(TC*)(void*))gv[4/4])(g); } }
static void TC w_redraw(void *self,uint32_t id,int a,int flag,int b){
    ((void (TC*)(void*,uint32_t,int,int,int))0x68043cb0)(self,id,a,flag,b);
    if((int16_t)id!=9||!rd_ext) return;
    int16_t a16=(int16_t)a,s5=a16?(int16_t)b:0; uint32_t *vt=*(uint32_t**)self;
    for(int g_id=0x30;g_id<0x34;g_id++){ void **g=((void**(TC*)(void*,int))vt[0x48/4])(self,g_id); if(!g||IsBadReadPtr(g,4)) continue;
        uint32_t *gv=(uint32_t*)*g; if(((short(TC*)(void*))gv[0x14/4])(g)!=8) continue;
        ((void(TC*)(void*,int,int))gv[0x2c/4])(g,a16,s5); if((int16_t)flag) ((void(TC*)(void*))gv[4/4])(g); } }static void widen_cfg(void){
    char b[128]; int en=GetPrivateProfileIntA("widen","enable",0,ini_path); (void)en;
    const char *keys[2]={"bat","pit"};
    for(int v=0;v<2;v++){ GetPrivateProfileStringA("widen",keys[v],"",b,sizeof b,ini_path); if(!b[0]) continue;
        uint32_t t[4]; int n=0; for(char *s=strtok(b,", ");s&&n<4;s=strtok(0,", ")) t[n++]=strtoul(s,0,0);
        if(n==4) memcpy(ext_tab[v],t,sizeof t); } }

/* trace hook on BBShell DrawText_Shell 68065650 (cdecl, text = 7th arg). Entry: sub esp,4 / push ebx / push esi (83 ec 04 53 56). Flag [trace] draw=1, separate from widen. */
static unsigned dt_cnt; uint32_t resume_dt;
HANDLER void h_dt(Regs *r){ const char *t=(const char*)r->stk[7]; if(!t||IsBadReadPtr(t,2)||dt_cnt>=400) return;
    char b[64]; int i=0; for(;i<63&&!IsBadReadPtr(t+i,1)&&t[i];i++) b[i]=t[i]; b[i]=0;
    if(tx_match[0]&&!strstr(b,tx_match)) return; dt_cnt++;
    char w[700]; int k=snprintf(w,sizeof w,"DRAW   '%s' x=%d y=%d font=%d stack:",b,(int16_t)r->stk[1],(int16_t)r->stk[2],(int16_t)r->stk[4]);
    stack_walk(r->stk+1,w,k,sizeof w); T("%s",w); }
extern void stub_dt(void);
STUB(dt," subl $4,%esp\n pushl %ebx\n pushl %esi\n");
static void dt_apply(HMODULE m){
    if(!tx_draw||(uintptr_t)m!=0x68000000) return; uint8_t *p=(uint8_t*)0x68065650; static const uint8_t orig[5]={0x83,0xec,0x04,0x53,0x56};
    if(IsBadReadPtr(p,5)) return; if(p[0]==0xe9){ return; }
    if(memcmp(p,orig,5)){ T("DRAW hook skipped: bytes at 68065650 differ"); return; }
    DWORD o; if(!VirtualProtect(p,5,PAGE_EXECUTE_READWRITE,&o)) return;
    resume_dt=0x68065655; uint32_t rel=(uint32_t)(uintptr_t)stub_dt-(0x68065650+5); p[0]=0xe9; memcpy(p+1,&rel,4);
    DWORD o2; VirtualProtect(p,5,o,&o2); FlushInstructionCache(GetCurrentProcess(),p,5); T("DRAW hook applied at 68065650"); }
static int widen_apply(HMODULE m){
    if(!GetPrivateProfileIntA("widen","enable",0,ini_path)){ T("WIDEN off (bbfix.ini [widen] enable=0), BBShell left pristine"); return 0; }
    if((uintptr_t)m!=0x68000000){ T("WIDEN skip ALL: BBShell base %p != 68000000",m); return 0; }
    widen_cfg(); rd_ext=GetPrivateProfileIntA("widen","rdext",1,ini_path);
    uint8_t want[NSITE][8]; int nap=0;
    for(int i=0;i<NSITE;i++){ Site *s=&sites[i]; uint8_t *p=(uint8_t*)(uintptr_t)s->va;
        if(IsBadReadPtr(p,s->n)){ T("WIDEN skip ALL: site %s %08x unreadable",s->name,s->va); return 0; }
        if(s->call==1){ uint32_t r=0x68043cb0-(s->va+5); ((Site*)s)->orig[0]=0xe8; memcpy(((Site*)s)->orig+1,&r,4); }
        memcpy(want[i],s->orig,s->n);
        if(s->call==2){ uint32_t r=(uint32_t)(uintptr_t)w_vt8; memcpy(want[i],&r,4); }
        else if(s->call==1){ uint32_t r=(uint32_t)(uintptr_t)w_redraw-(s->va+5); memcpy(want[i]+1,&r,4); }
        else if(s->stub){ uint32_t rel=(uint32_t)(uintptr_t)s->stub-(s->va+5); want[i][0]=0xe9; memcpy(want[i]+1,&rel,4); for(int k=5;k<s->n;k++) want[i][k]=0x90; *s->resume=s->va+s->n; }
        else want[i][s->immoff]=s->immnew;
        if(!memcmp(p,s->orig,s->n)) continue;
        if(!memcmp(p,want[i],s->n)){ nap++; continue; }
        char h[40]="",w[40]=""; for(int k=0;k<s->n;k++){ sprintf(h+2*k,"%02x",p[k]); sprintf(w+2*k,"%02x",s->orig[k]); }
        T("WIDEN skip ALL: site %s %08x has %s expected %s (no hooks applied)",s->name,s->va,h,w); return 0; }
    if(nap==NSITE) return 1;                                         /* already hooked this mapping */
    if(nap){ T("WIDEN skip ALL: %d of %d sites already hooked (inconsistent)",nap,NSITE); return 0; }
    DWORD old[NSITE]; int i;
    for(i=0;i<NSITE;i++) if(!VirtualProtect((void*)(uintptr_t)sites[i].va,sites[i].n,PAGE_EXECUTE_READWRITE,&old[i])) break;
    if(i<NSITE){ T("WIDEN skip ALL: VirtualProtect failed at %s err=%lu",sites[i].name,GetLastError()); for(int k=0;k<i;k++){ DWORD o; VirtualProtect((void*)(uintptr_t)sites[k].va,sites[k].n,old[k],&o);} return 0; }
    for(i=0;i<NSITE;i++) memcpy((void*)(uintptr_t)sites[i].va,want[i],sites[i].n);
    for(i=0;i<NSITE;i++){ DWORD o; VirtualProtect((void*)(uintptr_t)sites[i].va,sites[i].n,old[i],&o); FlushInstructionCache(GetCurrentProcess(),(void*)(uintptr_t)sites[i].va,sites[i].n); }
    T("WIDEN applied %d hooks to BBShell.dll; bat=%u,%u,%u,%u pit=%u,%u,%u,%u",NSITE,ext_tab[0][0],ext_tab[0][1],ext_tab[0][2],ext_tab[0][3],ext_tab[1][0],ext_tab[1][1],ext_tab[1][2],ext_tab[1][3]);
    return 1; }

/* ---- mod hook engine (roadmap #9): mods are DLLs listed in bbfix.ini [mods] load=a.dll,b.dll; SDK + contract in
   bbmod.h. Hooks are registered once (bbmod_init) and applied on every mapping of their module, rebased from the
   preferred ImageBase, all-or-nothing per (mod, module): expected bytes, inside the image, no base-relocation overlap. */
#include "bbmod.h"
enum { HK_DETOUR, HK_MID, HK_PATCH, HK_CALL };
typedef struct { int owner, kind, n, built; char module[64]; uint32_t va; uint8_t expect[16], repl[16], inst[16]; void *handler; void **orig; } ModHook;
#define MAXMH 512
static ModHook mh[MAXMH]; static int nmh, cur_owner=-1; static char mod_names[32][64]; static int nmods;
static uint8_t *pool; static unsigned pool_used;
static uint8_t *pool_get(unsigned n){ n=(n+15)&~15u; if(!pool||pool_used+n>65536){ pool=VirtualAlloc(0,65536,MEM_COMMIT|MEM_RESERVE,PAGE_EXECUTE_READWRITE); pool_used=0; if(!pool) return 0; }
    uint8_t *p=pool+pool_used; pool_used+=n; return p; }
static void m_log(const char *f,...){ char b[600]; va_list a; va_start(a,f); vsnprintf(b,sizeof b,f,a); va_end(a); T("MOD    %s",b); }
static int m_ini_int(const char *s,const char *k,int d){ return GetPrivateProfileIntA(s,k,d,ini_path); }
static int m_ini_str(const char *s,const char *k,const char *d,char *o,int n){ return GetPrivateProfileStringA(s,k,d,o,n,ini_path); }
/* preferred ImageBase from the file on disk: the loader rewrites the mapped header's ImageBase to the actual base */
static uint32_t pref_base(HMODULE m){ static struct { HMODULE m; uint32_t pref; char path[MAX_PATH]; } c[16]; static int nc;
    char p[MAX_PATH]; if(!GetModuleFileNameA(m,p,MAX_PATH)) return 0;
    for(int i=0;i<nc;i++) if(c[i].m==m&&!strcmp(c[i].path,p)) return c[i].pref;
    uint8_t b[1024]; DWORD got=0; HANDLE f=CreateFileA(p,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,0,OPEN_EXISTING,0,0); if(f==INVALID_HANDLE_VALUE) return 0;
    ReadFile(f,b,sizeof b,&got,0); CloseHandle(f); uint32_t e=got>=0x40?*(uint32_t*)(b+0x3c):0; if(e+0x38>got) return 0;
    uint32_t pref=*(uint32_t*)(b+e+0x34); int i=nc<16?nc++:15; c[i].m=m; c[i].pref=pref; strcpy(c[i].path,p); return pref; }
static void *m_addr(const char *module,uint32_t va){ HMODULE m=GetModuleHandleA(module); if(!m) return 0;
    IMAGE_NT_HEADERS *nt=(IMAGE_NT_HEADERS*)((char*)m+((IMAGE_DOS_HEADER*)m)->e_lfanew); uint32_t rva=va-pref_base(m);
    return rva<nt->OptionalHeader.SizeOfImage?(char*)m+rva:0; }
static int m_add(int kind,const char *module,uint32_t va,const uint8_t *expect,const uint8_t *repl,int n,void *handler,void **orig){
    const char *why=0; if(cur_owner<0) why="registration outside bbmod_init"; else if(nmh>=MAXMH) why="too many hooks";
    else if(!module||strlen(module)>=64) why="bad module name"; else if(!expect||n<1||n>16) why="n must be 1..16";
    else if(kind!=HK_PATCH&&n<5) why="detour/midhook/call need n >= 5"; else if(kind==HK_PATCH&&!repl) why="patch needs repl";
    else if(kind!=HK_PATCH&&!handler) why="no handler";
    if(why){ T("MOD    %s: rejected hook %s!%08x: %s",cur_owner<0?"?":mod_names[cur_owner],module?module:"?",va,why); return -1; }
    ModHook *h=&mh[nmh]; memset(h,0,sizeof *h); h->owner=cur_owner; h->kind=kind; h->n=n; strcpy(h->module,module); h->va=va;
    memcpy(h->expect,expect,n); if(repl) memcpy(h->repl,repl,n); h->handler=handler; h->orig=orig; if(orig) *orig=0; return nmh++; }
static int m_detour(const char *mo,uint32_t va,const uint8_t *e,int n,void *h,void **orig){ return m_add(HK_DETOUR,mo,va,e,0,n,h,orig); }
static int m_midhook(const char *mo,uint32_t va,const uint8_t *e,int n,bb_mid_fn h){ return m_add(HK_MID,mo,va,e,0,n,(void*)h,0); }
static int m_patch(const char *mo,uint32_t va,const uint8_t *e,const uint8_t *r,int n){ return m_add(HK_PATCH,mo,va,e,r,n,0,0); }
/* call site: e8 rel32 to target_va; rel32 is base independent (site and target move together), so expect is fixed */
static int m_redirect_call(const char *mo,uint32_t va,uint32_t target_va,void *h,void **orig){ uint8_t e[5]; uint32_t rel=target_va-(va+5); e[0]=0xe8; memcpy(e+1,&rel,4); return m_add(HK_CALL,mo,va,e,0,5,h,orig); }
static const BBModAPI mod_api={BBMOD_API_VERSION,m_log,m_ini_int,m_ini_str,m_detour,m_midhook,m_patch,m_addr,m_redirect_call};
static int reloc_overlap(HMODULE m,uint32_t rva,int n){
    IMAGE_NT_HEADERS *nt=(IMAGE_NT_HEADERS*)((char*)m+((IMAGE_DOS_HEADER*)m)->e_lfanew);
    IMAGE_DATA_DIRECTORY dd=nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_BASERELOC];
    for(uint32_t off=0;off+8<=dd.Size;){ IMAGE_BASE_RELOCATION *b=(IMAGE_BASE_RELOCATION*)((char*)m+dd.VirtualAddress+off);
        if(b->SizeOfBlock<8) break; uint16_t *e=(uint16_t*)(b+1); int cnt=(b->SizeOfBlock-8)/2;
        for(int i=0;i<cnt;i++) if((e[i]>>12)==IMAGE_REL_BASED_HIGHLOW){ uint32_t r=b->VirtualAddress+(e[i]&0xfff); if(r<rva+n&&r+4>rva) return 1; }
        off+=b->SizeOfBlock; }
    return 0; }
/* displaced bytes into code at q: verbatim, or a lone call/jmp rel32 retargeted; then jmp back to site+n. Returns the end. */
static uint8_t *emit_displaced(uint8_t *q,const uint8_t *site,const uint8_t *orig,int n){
    if(n==5&&(orig[0]==0xe8||orig[0]==0xe9)){ uint32_t tgt=(uint32_t)(uintptr_t)site+5+*(uint32_t*)(orig+1),rel=tgt-((uint32_t)(uintptr_t)q+5); q[0]=orig[0]; memcpy(q+1,&rel,4); q+=5; }
    else { memcpy(q,orig,n); q+=n; }
    uint32_t rel=(uint32_t)(uintptr_t)site+n-((uint32_t)(uintptr_t)q+5); q[0]=0xe9; memcpy(q+1,&rel,4); return q+5; }
static void mods_apply(HMODULE m,const char *bn){
    IMAGE_NT_HEADERS *nt=(IMAGE_NT_HEADERS*)((char*)m+((IMAGE_DOS_HEADER*)m)->e_lfanew); uint32_t pref=pref_base(m),size=nt->OptionalHeader.SizeOfImage;
    if(!pref){ T("MOD    cannot read the preferred base of %s, no mod hooks applied to it",bn); return; }
    for(int o=0;o<nmods;o++){
        int cnt=0,done=0; const char *why=0; int bad=-1;
        for(int i=0;i<nmh;i++){ ModHook *h=&mh[i]; if(h->owner!=o||_stricmp(h->module,bn)) continue; cnt++; if(why) continue;
            uint32_t rva=h->va-pref; uint8_t *p=(uint8_t*)m+rva;
            if(rva>=size||rva+h->n>size) why="outside the module image";
            else if(IsBadReadPtr(p,h->n)) why="unreadable";
            else if(reloc_overlap(m,rva,h->n)) why="overlaps a base relocation";
            else if(h->built&&!memcmp(p,h->inst,h->n)) done++;          /* this mapping already hooked */
            else if(memcmp(p,h->expect,h->n)) why="bytes differ from expect";
            if(why) bad=i; }
        if(!cnt) continue;
        if(why){ ModHook *h=&mh[bad]; char x[40]="",w[40]=""; uint8_t *p=(uint8_t*)m+(h->va-pref);
            if(!IsBadReadPtr(p,h->n)) for(int k=0;k<h->n;k++){ sprintf(x+2*k,"%02x",p[k]); sprintf(w+2*k,"%02x",h->expect[k]); }
            T("MOD    %s: NOT applied to %s (%d hooks): hook %d at %08x %s (have %s expect %s)",mod_names[o],bn,cnt,bad,h->va,why,x,w); continue; }
        if(done==cnt) continue;
        if(done){ T("MOD    %s: NOT applied to %s: %d of %d sites already hooked (inconsistent)",mod_names[o],bn,done,cnt); continue; }
        /* build trampolines/stubs first; write sites only if all succeed */
        int ok=1;
        for(int i=0;i<nmh&&ok;i++){ ModHook *h=&mh[i]; if(h->owner!=o||_stricmp(h->module,bn)) continue; uint8_t *p=(uint8_t*)m+(h->va-pref);
            if(h->kind==HK_PATCH){ memcpy(h->inst,h->repl,h->n); h->built=1; continue; }
            if(h->kind==HK_CALL){ uint32_t r=(uint32_t)(uintptr_t)h->handler-((uint32_t)(uintptr_t)p+5); if(h->orig) *h->orig=p+5+*(int32_t*)(h->expect+1);
                h->inst[0]=0xe8; memcpy(h->inst+1,&r,4); h->built=1; continue; }
            uint8_t *t=pool_get(64); if(!t){ ok=0; break; } uint32_t entry=(uint32_t)(uintptr_t)t;
            if(h->kind==HK_DETOUR){ emit_displaced(t,p,h->expect,h->n); if(h->orig) *h->orig=t; entry=(uint32_t)(uintptr_t)h->handler; }
            else { uint8_t *q=t; uint32_t cont=(uint32_t)(uintptr_t)t+27;         /* push cont/pushfd/pushad/push esp/call h/add esp,4/test/jz/mov [esp+36],eax/popad/popfd/ret */
                q[0]=0x68; memcpy(q+1,&cont,4); q[5]=0x9c; q[6]=0x60; q[7]=0x54; q[8]=0xe8; uint32_t rel=(uint32_t)(uintptr_t)h->handler-((uint32_t)(uintptr_t)t+13); memcpy(q+9,&rel,4);
                static const uint8_t tail[]={0x83,0xc4,0x04,0x85,0xc0,0x74,0x04,0x89,0x44,0x24,0x24,0x61,0x9d,0xc3}; memcpy(q+13,tail,sizeof tail);
                emit_displaced(t+27,p,h->expect,h->n); }
            uint32_t rel=entry-((uint32_t)(uintptr_t)p+5); h->inst[0]=0xe9; memcpy(h->inst+1,&rel,4); for(int k=5;k<h->n;k++) h->inst[k]=0x90; h->built=1; }
        if(!ok){ T("MOD    %s: NOT applied to %s: out of trampoline memory",mod_names[o],bn); continue; }
        for(int i=0;i<nmh;i++){ ModHook *h=&mh[i]; if(h->owner!=o||_stricmp(h->module,bn)) continue; uint8_t *p=(uint8_t*)m+(h->va-pref); DWORD old,o2;
            VirtualProtect(p,h->n,PAGE_EXECUTE_READWRITE,&old); memcpy(p,h->inst,h->n); VirtualProtect(p,h->n,old,&o2); FlushInstructionCache(GetCurrentProcess(),p,h->n); }
        T("MOD    %s: applied %d hooks to %s at %p (pref %08x)",mod_names[o],cnt,bn,m,pref); } }
static void mods_load(void){
    char list[512],dir[MAX_PATH]; GetPrivateProfileStringA("mods","load","",list,sizeof list,ini_path); if(!list[0]) return;
    strcpy(dir,ini_path); *strrchr(dir,'\\')=0;
    for(char *s=strtok(list,", ");s&&nmods<32;s=strtok(0,", ")){ char p[MAX_PATH]; snprintf(p,sizeof p,"%s\\%s",dir,s);
        HMODULE dl=LoadLibraryA(p); bbmod_init_fn init=dl?(bbmod_init_fn)GetProcAddress(dl,"bbmod_init"):0;
        if(!init){ T("MOD    %s: load failed (%s, err=%lu)",s,dl?"no bbmod_init export":"LoadLibrary",GetLastError()); continue; }
        snprintf(mod_names[nmods],64,"%s",s); cur_owner=nmods++; int first=nmh, r=init(&mod_api); cur_owner=-1;
        if(r){ T("MOD    %s: bbmod_init returned %d, its %d hooks dropped",s,r,nmh-first); nmh=first; nmods--; continue; }
        T("MOD    %s: loaded, %d hooks registered",s,nmh-first); }
    for(int i=0;i<nmh;i++){ HMODULE m=GetModuleHandleA(mh[i].module); if(m) mods_apply(m,mh[i].module); } }

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
        int ism=!_stricmp((char*)m+id->Name,"msvcrt.dll")||!_stricmp((char*)m+id->Name,"GDI32.dll");
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
static VOID CALLBACK on_load(ULONG reason, LDR_NOTE *d, PVOID ctx) { if(reason==1 && d){ char p[MAX_PATH]; GetModuleFileNameA((HMODULE)d->DllBase,p,MAX_PATH); if(!_strnicmp(p,"C:\\Sierra",9)){ const char *bn=strrchr(p,'\\')+1; T("DLL    loaded %s at %p",bn,d->DllBase); if(!_stricmp(bn,"BBShell.dll")) { widen_apply((HMODULE)d->DllBase); dt_apply((HMODULE)d->DllBase); } }
    if(nmh){ const char *bn=strrchr(p,'\\'); mods_apply((HMODULE)d->DllBase,bn?bn+1:p); } patch_iat((HMODULE)d->DllBase);} }

BOOL WINAPI DllMain(HINSTANCE h, DWORD why, LPVOID r) {
    if(why==DLL_PROCESS_ATTACH) {
        char p[MAX_PATH]; GetModuleFileNameA(h,p,MAX_PATH); char *s=strrchr(p,'\\'); if(s) strcpy(s+1,"bbfix.log");
        lg=fopen(p,"w"); L("bbfix loaded");
        strcpy(s+1,"bbfix.ini"); strcpy(ini_path,p); InitializeCriticalSection(&trcs); strcpy(s+1,"bbtrace.log"); tr=CreateFileA(p,GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE,0,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,0);
        trace_cfg(); T("=== BBPRO98 action trace started (pid %lu) ===",GetCurrentProcessId()); AddVectoredExceptionHandler(1,VEH); CreateThread(0,0,HandleWatch,0,0,0);
        patch_all(); mods_load();
        typedef LONG (NTAPI *Reg_t)(ULONG,LDR_CB,PVOID,PVOID*);
        Reg_t reg=(Reg_t)GetProcAddress(GetModuleHandleA("ntdll.dll"),"LdrRegisterDllNotification");
        PVOID cookie; if(reg) L("LdrRegisterDllNotification -> %ld", reg(0,on_load,0,&cookie)); else L("no LdrRegisterDllNotification");
    }
    return TRUE;
}
