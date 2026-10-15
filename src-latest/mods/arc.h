/* arc.h: a player's career arc, a pure function of (pid, birth date) so the game (aging.c) and the news sidecar
   (news/arc.py) compute the same trait without sharing any state. Keep the two identical: news/tests/test_arc.py
   compiles this header with the host cc and compares it with the Python on random pairs.
   h = FNV-1a 32-bit over 6 bytes (pid as 2 bytes little-endian, then birth as 4 bytes little-endian).
   shift = h % (2*years+1) - years    years of decline onset: positive declines later, negative earlier
   size  = 100 - spread + (h >> 16) % (2*spread+1)    percent applied to the decline amount
   years and spread below 0 count as 0 (years 0 gives shift 0, spread 0 gives size 100). Returns shift, writes *size
   (size may be NULL). Fixed-width unsigned arithmetic only, no CRT. */
#ifndef ARC_H
#define ARC_H
#include <stdint.h>

static __inline int arc_trait(int pid, unsigned int birth, int years, int spread, int *size) {
    uint32_t h = 2166136261u;
    uint32_t b[6], m, k;
    if (years < 0) years = 0;
    if (spread < 0) spread = 0;
    b[0] = (uint32_t)pid & 0xffu; b[1] = ((uint32_t)pid >> 8) & 0xffu;
    for (k = 0; k < 4; k++) b[2 + k] = ((uint32_t)birth >> (8 * k)) & 0xffu;
    for (k = 0; k < 6; k++) { h ^= b[k]; h *= 16777619u; }
    m = 2u * (uint32_t)years + 1u;
    if (size) {
        uint32_t n = 2u * (uint32_t)spread + 1u;
        *size = 100 - spread + (int)((h >> 16) % n);
    }
    return (int)(h % m) - years;
}

#endif
