# FPS Baseball Pro '98 ASN File Format (Tier 2, 2026-10-06)

## File Overview

**File:** `Assn/MLBPA97.ASN` (2.6MB, s10 snapshot)

**Purpose:** Association/League data container holding team names, divisions, leagues, schedules, and play-by-play records.

**Status:** PARTIAL DECODE - Directory and block structure identified; record encoding still under investigation.

---

## Container Structure

The ASN file is a **multi-block container** with a file directory listing named data blocks and their offsets.

### Directory Format

**Offset range:** ~0x0300 to ~0x0500 (approx)

Contains plaintext filenames for data blocks:
- Marker byte: `0x3a` (`:`) or `0x3b` (`;`)
- Block name: (1-2 letters) + `.dat` or `.idx`
- Offset: u32 little-endian (variable position after name)
- Flags/metadata: (unknown)

**Known blocks:**

| Block | Purpose | Type | Records Found |
|-------|---------|------|---------------|
| a.dat / a.idx | Associations/League config | Data+Index | 9302 |
| l.dat / l.idx | League info | Data+Index | ~9300 |
| d.dat / d.idx | Divisions | Data+Index | ~9300 |
| t.dat / t.idx | Teams | Data+Index | ~9300 |
| r.dat / r.idx | Results/Records | Data+Index | ? |
| s.dat / s.idx | Schedule | Data+Index | ? |
| xs.dat / xs.idx | Extended schedule | Data+Index | ? |
| tr.dat / tr.idx | Trades | Data+Index | ? |
| df.dat / df.idx | Draft | Data+Index | ? |
| po.dat / po.idx | Play-offs | Data+Index | ? |
| sp.dat / sp.idx | Special data | Data+Index | ? |

### Data Block Format

Each `.dat` block contains **records in the same format as Stats DAT files:**

```
[offset]  fafa          (2 bytes, record marker)
[offset+2] u32 LE       (total size = payload_len + 18)
[offset+6] u32 LE       (payload length)
[offset+10] u32 LE      (record number)
[offset+14] u32 LE      (logical offset, unknown use)
[offset+18] [payload]   (payload_len bytes)
```

**Example (t.dat team record 0, recno=8, len=256 bytes):**
```
Offset 0x3a33: fa fa 00 01 00 00 c0 00 00 00 08 00 00 00 ...
  total=256 (0x100), payload_len=256 (0xc0), recno=8
  payload: 01 1d 1d 1d a6 01 01 01 01 01 01 01 1d 1d f9 f9 f9 f9 ...
```

### Index Block Format

Each `.idx` block appears to be **default/template data:**

```
[offset]  u32 LE = 0x0001ed (~493 bytes)
[offset+4] ... (all blocks show same size and likely same template)
```

All `.idx` blocks observed are 0x0001ed bytes and contain uniform placeholder data. Likely used as default/template during initialization.

---

## Payload Encoding

**Status:** UNVERIFIED - likely encoded or partially encrypted.

### Observations

1. **Heavy padding:** Byte 0x1d appears frequently (>50% of payload in team records)
2. **Patternal data:** Some bytes repeat in fixed positions across records (e.g., 0x1d, 0xf9)
3. **Mixed content:** Metadata records (recno=0) contain plaintext filenames ("d.dat", "t.dat", etc.)
4. **Binary structure:** Actual team/league data is not plain ASCII; likely encoded like PYR (substitution table?) or compressed

### Payload Structure (Team Records, Hypothesis)

```
Byte 0: Team ID (0x01-0x1d for 29 teams in MLB)
Bytes 1-9: Team metadata (unknown)
Bytes 10-50: Possible name/abbreviation (unconfirmed, possibly encoded)
Bytes 51-256: Stats, ratings, schedule references (unknown structure)
```

**Unconfirmed:** Whether encoding uses a per-file substitution table (like PYR) or a fixed cipher.

---

## Team and League Names (Not Yet Found)

**Expected content (from game screenshot, 1997 MLBPA Opening Day):**

National League teams: ATL, HOU, CHI, FLA, COL, CIN, NYN, SD, PHI, LAD, STL, MON (12)
American League teams: NYY, BAL, TB, TOR, BOS, DET, CWS, KC, MIN, TEX, OAK, SEA, ANA (13)
Total: 25 teams (but records show ~30, likely including non-MLB or historical teams)

**Search result:** No plaintext team abbreviations or city names found in ASN file. Suggests:
1. Names are encoded/encrypted
2. Teams are identified by numeric IDs only in ASN; names stored elsewhere (e.g., SHELL.VOL resources)
3. Game engine has hardcoded team name table

---

## Known Offsets and Byte Positions

### Directory Entries (first 50 bytes of each filename location)

```
Offset 0x0325 (a.dat):     "a.dat" + zeros + 0x0000ff (offset)
Offset 0x0466 (l.dat):     "l.dat" + zeros + 0x001743 (offset)
Offset 0x043e (d.dat):     "d.dat" + zeros + 0x002783 (offset)
Offset 0x04cb (t.dat):     "t.dat" + zeros + 0x003a33 (offset)
```

### First Records

- **a.dat record 0:** offset 0x001743 (league config?, recno=4, 46 bytes)
- **l.dat record 0:** offset 0x001743 (league data, recno=4, 46 bytes)
- **d.dat record 0:** offset 0x002783 (division data, recno=6, 30 bytes)
- **t.dat record 0:** offset 0x003a33 (team data, recno=8, 256 bytes)

### Metadata Records

Records with recno=0 in various blocks contain filenames:
- t.dat recno=0: "t.dat" (192 bytes, padded)
- t.idx recno=0: "t.idx" (192 bytes, padded)
- d.dat recno=0: "d.dat" (192 bytes, padded)
- d.idx recno=0: "d.idx" (192 bytes, padded)

---

## Outstanding Questions

1. **Encoding mechanism:** Is it per-file substitution table (like PYR) or fixed cipher? How to recover?
2. **Team name location:** Are team names in this ASN file or stored in SHELL.VOL resources?
3. **Record structure:** What do bytes 1-30 of a team record represent? (IDs? stats? attributes?)
4. **Index usage:** What do .idx blocks do? Are they lookup tables or templates?
5. **Records >30:** Why are there ~9300 records when only ~29 MLB teams exist? (Historical seasons? duplicates? other data?)

---

## Next Steps

1. **Attempt decryption:** Check if a per-file substitution table can be built from metadata or from the game's memory (bbtrace.log)
2. **Cross-reference game display:** Compare game-displayed team names/divs against encoded bytes using known offset(s)
3. **Check SHELL.VOL:** Extract and examine MENU.REQ, DIAL.REQ for team name resources
4. **Examine decompiled code:** Search FPS_CT._all.c and BBShell._all.c for ASN file parsing logic
5. **Test round-trip:** Once decoding is confirmed, write round-trip test to verify encode/decode
6. **Write asn_read.py:** Produce a full parser that outputs league/division/team structure matching game display

---

## Verification Status

**Unverified:** This analysis is based on file structure and record format only. No actual team/league names have been confirmed against game display. Encoding status unknown.

**Confidence levels:**
- File block directory structure: HIGH (plaintext filenames confirmed)
- Record format (fafa markers): HIGH (matches Stats DAT format)
- Payload encoding: LOW (structure unknown, no decoding key found)
- Team name locations: VERY LOW (not yet found)

---
## CORRECTION AND VERIFIED FINDINGS (Claude, 2026-10-06, re-run by hand; supersedes anything above that conflicts)
- The earlier claim "about 9300 records in every block" is WRONG. 9310 is the count of raw fafa byte pairs in the whole file, mostly false positives. Parsing each table region with the validated record rule (total == payload_len + 18) gives:
  - t.dat (0x3902..0x66f8): 28 team records of 256 bytes (28 = the 1997 MLB team count), plus t.idx (192) and a 494-byte header record.
  - l.dat: 2 records of 46 bytes (leagues), 2 index records of 192, 1 of 494.
  - d.dat: 6 records of 30 bytes (divisions: 2 leagues x 3), plus the same index and header pattern.
- Container is a FairCom c-tree style ISAM: library FPS_CT.dll is the engine. Record writer FUN_64001d70 stores marker 0xfafa (variable/extended record) or 0xfbbf, then u32 total, u32 len, recno, offset. Record framing is therefore CONFIRMED for ASN, same as Stats DAT.
- Payload bytes are NOT plain. Padding or zero fields appear as 0x1d and 0x01, and the same plaintext gives the same byte, which looks like a fixed byte substitution or a field encoding, not a stream cipher. The 256-byte permutation tables found in BBSIM/FastSim (0x8bda0, 0xb6e00) are identity tables and are NOT the cipher. Reader code to disassemble next: the FPS_CT field-level decode (callers of FUN_64001d70 and the DODA-style schema), then BBShell team load.
- Status: framing DECODED, payload encoding UNKNOWN. Not claimed beyond that.
