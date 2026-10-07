# Format Decode Status (Tier 2, 2026-10-06)

## Summary Table

| Format | Status | Evidence | Notes | Next Action |
|--------|--------|----------|-------|-------------|
| **PYR** (Player Roster) | Decoded (round-trip verified) | /home/will/bbpro98/BBPRO98_package/research/pyr_io.py both read/write; header 192B + 192B records with per-file substitution table | CONFIRMED: byte-identical round-trip test included in pyr_io.py __main__. 256-entry inverse table recovered from record IDs. | None: fully done |
| **mlbpa97.DAT** (Stats Container) | Decoded (read-only, filtered) | /home/will/bbpro98/work/parse_stats.py (record scanner), /home/will/bbpro98/work/lib.py (filters OK records), /home/will/bbpro98/work/bbstats.py (batting/pitching extractor). NOTES_stats_format.md: 512B pages, 0xfafa record markers, 40/70/36/22/150-byte payloads. | CONFIRMED via game screen verification (Maddux AB, monthly splits sum to totals). scope 1=current season, scope 2=career. 40-byte batting line: AB,1B,2B,3B,HR,RBI,BB,SO,IBB,HBP,SH,SF,G,R,SB,CS,GIDP. 70-byte pitching line: same batting-block + pitcher fields (outs, W/L/SV, ER, etc.). | Write round-trip test (no writer yet); map unmapped pitch cols (c23-c25, c26-c27) |
| **SHELL.VOL** (Resource Archive) | Decoded (read-only) | /home/will/bbpro98/work/volx.py unpacks VOLM archive (directory, offsets, file extraction). Magic: "VOLM". | CONFIRMED: crude unpacker reads offset table, extracts files. SHELL.VOL unpacks to MENU.REQ, DIAL.REQ, and others. | Reverse inner file formats (MENU.REQ, DIAL.REQ); test round-trip on SHELL.VOL rebuild |
| **DIAL.REQ** | Partial | Inside SHELL.VOL; unpacked by volx.py. No parser yet. | Size ~unknown; format TBD. Suspect dialog/resource format. | Reverse structure; likely Win32 resource or custom binary format |
| **MENU.REQ** | Partial | Inside SHELL.VOL; unpacked by volx.py. No parser yet. | Size ~unknown; format TBD. Suspect menu/UI resource format. | Reverse structure |
| **bb.cfg** | Partial (text hints) | Magic: "MLBPA97\0\0\0\0". First 8 bytes = association name. Format TBD. Inventory: 124 bytes, entropy 2.42 (text-like). | UNVERIFIED: likely association config (league, teams?). No parser. | Extract full structure; likely text or fixed records |
| **Game snapshot files (.apc/.pyc/.pyf/.eos)** | Unknown | Not yet found or inventoried in install. | — | Search /home/will/seasons/s*/ for examples; reverse structure |
| **game.bki / game.bko** | Unknown | Not found in current install (Assn snapshot may not include them). | Suspect "before" / "after" game state snapshots. | Check /mnt/nvme/bbpro98/work or season snapshots |
| **SIM.DAT** | Partial | Size 1.9M, magic unknown (first 4B: 00 01 06 07), entropy 5.10 (fixed-record), divisible by [512, 256, 128, 100, 64]? → no. | Suspect simulation state or formula tables. No parser. | Investigate structure; likely large lookup table or compressed state |
| **SCHEDTMP.DAT** | Partial | Size ~704KB, magic: ff ff 0a 00, entropy 3.82, divisible by [512, 256, 128, 64]. | Suspect schedule (games, dates). No parser. | Extract and verify against game schedule in UI |
| **ARCDBM.DAT** | Encrypted/Compressed | Magic: 42 00 0e 01 (stored 0x42 = 'B'), high entropy 7.18+, indices Arcdbm4.dat / Arcdbm8.dat | Family of archive database files (3x main, 3x variant by version?). Unencrypted: no. | Reverse encryption/compression; check if match DBM.DAT pattern |
| **GAMEDBM.DAT** | Encrypted/Compressed | Magic: 09 00 2a 00, entropy 7.34, ~46KB. | Suspect game database. Encrypted/compressed like ARCDBM. | Check DBM.DAT family pattern (BPIDBM.DAT, NUMDBM.DAT, OVERDBM.DAT, NOVDBM.DAT, NUMDBM4/8.DAT) |
| **BPIDBM.DAT** | Fixed-record table | Magic: 48 00 26 01, entropy 6.87, ~1.6MB, divisibility unknown. | Likely player index or rating lookup. | Extract records; verify against player ID range (100+) |
| **NUMDBM.DAT** (and variants 4/8) | Fixed-record table | Magic: 42 00 0e 01, entropy 6.09-6.35, ~200KB-900KB. | Numeric lookup tables (possibly stat lookup). | Extract record structure; test round-trip |
| **OVERDBM.DAT** | Encrypted/Compressed | Magic: 42 00 0e 01, entropy 7.21 (high), ~602KB. | Suspect "override" or modifier table. | Reverse encryption; test against game behavior |
| **NOVDBM.DAT** | Paged Container | Magic: 42 00 0e 01, entropy 6.40, ~64KB. | Smaller DBM variant. | Extract structure; likely configuration or default data |
| **DMP.DAT** | Fixed-record table | Magic: 42 00 0e 01, entropy 5.00, ~38KB. | Suspect dump/state file. No parser. | Extract record structure |
| **HHA.DAT** | Fixed-record table | Magic: 69 69 01 00, entropy 3.17, ~19KB. | Suspect "Hall of Achievement" or similar. | Extract records; verify against game display |
| **hilights/*.tap** | Partial | Magic: "+ 10-27-06 TOR..." (timestamp), entropy 4.52-4.74 (fixed-record). | Suspect play-by-play or game recording (tape format?). No parser. | Extract structure; likely record stream with dates/events |
| **MLBPA97.ASN** | Unknown | Assn/MLBPA97.ASN size TBD. No parser. Ghidra index: FPS_CT._all.c, BBShell._all.c should have ASN open calls. | Association file: leagues, divisions, teams, schedule. | **TASK 4**: Reverse structure using decompiled ASN open functions; produce asn_read.py |
| **.FNX** (Font?) | Text-like | Magic: "FNX:", entropy 1.69-3.83 (text). Sizes 1.7KB - 34KB. | Likely font data with header. | Extract character table; test rendering in Wine |
| **.PLX** (Palette?) | Paged Container | Magic: mostly zeros, entropy 0.45 (very low), 768B, divisible by 256/128/64. | Likely lookup table (pal data, 256 entries @ 3B RGB = 768B). | Extract and verify as palette file |
| **.BMX** (Sprite/Bitmap?) | Various | Magic varies, entropy 1.43-3.77. Sizes 5KB-57KB. | Suspect sprite or bitmap archive. No parser. | Reverse header; check if match .BMP pattern |
| **.JOY** (Joystick config) | Text-like | Magic: "[Joystick]", entropy 5.15-5.18 (text), ~3KB. | INI-like config for joystick mapping. | Parse as INI; extract action mappings |
| **.INI** (Config) | Text-like | Magic: "[Play]" or INI headers, entropy 4.25-5.17 (text). | Standard Windows INI format. | Parse with Python configparser |
| **.TXT** (Documentation/Config) | Text | PBINI.TXT, BBPROINI.TXT, game.txt are text. | Documentation and initialization hints. | Extract configuration, game notes |
| **BBPRO.1-9** | INI-like | Magic: "[Play]\r\n MainShow", entropy 5.13-5.14 (text). | Suspect per-season or per-game INI files. | Parse as INI; extract active season/game state |
| **wls.sav** | Small state | Magic: 0a 00 00 00, entropy 0.81, 4 bytes. | Likely single-value state file (e.g., selected league, season). | Unpack as u32 LE; verify against current state in UI |
| **glue.dat** | Small state | Magic: all zeros + 0a 00, entropy 0.50, 24 bytes. | Unknown state. | Unpack fields; check game startup traces |

## Cross-Format Notes

1. **DBM.DAT family** (ARCDBM, GAMEDBM, BPIDBM, NUMDBM, NOVDBM, OVERDBM, DMP.DAT):
   - All share magic `42 00 0e 01` or similar prefix (0x42 = stored 'B')
   - High or medium entropy (5.0-7.3) suggests fixed-record structure or weak encryption
   - Sizes range 19KB to 13MB
   - Hypothesis: Index/lookup tables, possibly with per-record encryption or compression

2. **Stats DAT Verification Chain** (NOTES_stats_format.md, verified 2026-10-06):
   - Read: parse_stats.py scanner + lib.py filter ✓
   - Verified via game screen (Association > Statistics > Show > Players) ✓
   - Player comparison: Maddux 1997 s5, 6/6 exact match (AB, H, HR, RBI) ✓
   - Scope mapping: 1=season, 2=career, 3=unknown split ✓
   - Missing: pitcher-only column mapping (c23-c27); round-trip writer

3. **VOL Archives** (SHELL.VOL, SHELL1.VOL, SHELL2.VOL):
   - Format: VOLM magic, directory with name/offset pairs, file offsets at end of directory
   - Parser exists (volx.py) ✓
   - Missing: round-trip rebuild; inner file format parsing (MENU.REQ, DIAL.REQ)

4. **Association File** (MLBPA97.ASN):
   - Expected: Team names, divisions, league structure, schedule
   - Decompiled references: FPS_CT.dll (FPS_CT._all.c), BBShell.dll (BBShell._all.c)
   - Not yet reverse-engineered
   - Target: asn_read.py produces league/team/division structure matching game display

## To-Do (Tier 2 Completion)

- [ ] TASK 3: Write and run round-trip test for PYR (read/write/compare bytes)
- [ ] TASK 4: Reverse ASN file structure using decompiled open/read functions
- [ ] TASK 4: Write asn_read.py to extract league, division, team names
- [ ] Extend Stats DAT decoder to map all pitcher columns (c23-c27)
- [ ] Reverse SIM.DAT structure (1.9MB lookup table?)
- [ ] Reverse SCHEDTMP.DAT (game schedule container?)
- [ ] Reverse DBM.DAT family encryption (if any) or fixed-record layout
- [ ] Create round-trip writers for Stats DAT, SIM.DAT, SCHEDTMP.DAT

## Addendum 2026-10-06 (Claude)
- ASN: record framing decoded and per-table counts verified (28 team, 2 league, 6 division records). Payload encoding unknown. See ASN.md CORRECTION.
- hit.log (debug output, not game data): fixed 74-byte records, two nonzero bytes per record (6 at +50, 3 at +62). Meaning unknown, low value.
- pitchres.log: 60 little-endian u32 pitch-outcome counts, first row matches the 0-0 row of prlog.txt (verified). Read-only.
- PB.INI: confirmed read at runtime from the exe directory (see work/RE_FINDINGS.md).
