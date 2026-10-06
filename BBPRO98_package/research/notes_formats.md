# BBPro98 file formats (static analysis)
- PYR: 192-byte header (4 bytes: u16 seed + u16 version=1; then plain text comment lines in shipped files, zeros in mods) + N*192-byte records.
- Every record byte goes through a per-file byte substitution T. Mods: T(x)=(m*x+c)&255 (002: m=0x73,c=0x3a; 006: m=0x5f,c=0xdd). Shipped 96/97/_DEFAULT: non-affine permutation (seed f5dc). Table is recovered from data: record i has ID 100+i in bytes 0-1.
- Record: 0-1 id; 26-29 birth daynum; 30 first name; 47 last name (17 B each); 64 yrs; 65 bats; 66 throws; 68 pos; 70/93 ratings/potentials 23 B; 116 25 B splits.
- ASN: Btrieve-like container (tables a,l,d,t,r,s,xs; 'FC!DEF' defs), same cipher family (seed at 0x310). t.dat = team records (city, nickname(mods), manager, stadium, file code).
- PYF: 'PPD:' u32 len, u16 count, count*u16 player IDs. RMT: 32KB Btrieve-like table 'rm.dat' (remote manager config), no player data.
