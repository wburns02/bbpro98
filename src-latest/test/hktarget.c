/* hktarget.c: synthetic target for the bbfix mod-engine unit test (hktest.py). Exact bytes via naked asm. */
int g_val = 7;
__declspec(dllexport) int helper5(int a) { return a * 5; }
/* f_add(a,b) = a+b. Prolog 55 8b ec 83 ec 08 (detour, n=6) */
__asm__(".globl _f_add\n_f_add:\n .byte 0x55,0x8b,0xec,0x83,0xec,0x08\n movl 8(%ebp),%eax\n addl 12(%ebp),%eax\n movl %ebp,%esp\n popl %ebp\n ret\n");
/* f_call(a) = helper5(a): first instruction is a lone call rel32 (detour n=5, call retargeted) */
__asm__(".globl _f_call\n_f_call:\n pushl 4(%esp)\n call _helper5\n addl $4,%esp\n ret\n");
/* f_call2(a) = helper5(a), midhooked at the call (handler bumps the pushed arg: helper5(a+1)) */
__asm__(".globl _f_call2\n_f_call2:\n pushl 4(%esp)\n call _helper5\n addl $4,%esp\n ret\n");
/* f_mid(a) = a+1, mid site at the add (83 c0 01 90 90 = add eax,1 / nop / nop, n=5) */
__asm__(".globl _f_mid\n_f_mid:\n movl 4(%esp),%eax\n.globl _f_mid_site\n_f_mid_site:\n .byte 0x83,0xc0,0x01,0x90,0x90\n ret\n.globl _f_mid_alt\n_f_mid_alt:\n movl $999,%eax\n ret\n");
/* f_patch() = 3 (b8 03 00 00 00 = mov eax,3), patched to 4 */
__asm__(".globl _f_patch\n_f_patch:\n .byte 0xb8,0x03,0x00,0x00,0x00\n ret\n");
/* f_bad() = 11, hooked with a wrong expect: must stay stock */
__asm__(".globl _f_bad\n_f_bad:\n .byte 0x55,0x8b,0xec,0xb8,0x0b,0x00,0x00,0x00\n popl %ebp\n ret\n");
/* f_rel() = g_val: mov eax,[g_val] has a base relocation inside the hooked bytes: must be refused */
__asm__(".globl _f_rel\n_f_rel:\n movl _g_val,%eax\n nop\n nop\n ret\n");
__asm__(".section .drectve\n .ascii \" -export:f_add -export:f_call -export:f_call2 -export:f_mid -export:f_mid_site -export:f_mid_alt -export:f_patch -export:f_bad -export:f_rel\"\n .text\n");
