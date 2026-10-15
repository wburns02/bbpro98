/* champtext.c: the season-end texts ("Led by Coach %2, the %0 %1 capture the %8 ...") print each empty argument as
   "<No Name>" (BBShell FUN_68012160, s_<No_Name>_6808a740). %1 and %5 are the team nickname, the t record's 16
   characters at 0x23, which no stock or Lahman association fills, so every World Series read "the Chicago Cubs
   <No Name>". This mod blanks that string: an empty argument then prints nothing. docs/lanes/bbnickname.md.
   bbfix.ini:  [mods] load=...,mods\champtext.dll */
#include <windows.h>
#include "../bbmod.h"

BB_EXPORT int bbmod_init(const BBModAPI *a) {
    if (a->version != BBMOD_API_VERSION) return 1;
    static const uint8_t expect[10] = {'<', 'N', 'o', ' ', 'N', 'a', 'm', 'e', '>', 0}, repl[10] = {0};
    if (a->patch("BBShell.dll", 0x6808a740, expect, repl, 10) < 0) return 2;
    a->log("champtext: <No Name> blanked");
    return 0;
}
