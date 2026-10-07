# Round-Trip Test Results (Tier 2, 2026-10-06)

## Test Procedure

For each format with both reader AND writer, execute: read file → decode → write to temp → compare bytes.

## PYR Format (Player Roster Files)

**Status: PASS (4/4 tests)**

Reader: `/home/will/bbpro98/BBPRO98_package/research/dump_pyr.py` + `pyr_io.py::read()`
Writer: `/home/will/bbpro98/BBPRO98_package/research/pyr_io.py::write()`

### Test Results

```
python3 test_roundtrip.py

Testing PYR: /home/will/seasons/s5/Assn/MLBPA97.PYR
  File size: 385536 bytes
  PASS: byte-identical round-trip (records=2007)

Testing PYR: /home/will/seasons/s10/Assn/MLBPA97.PYR
  File size: 466176 bytes
  PASS: byte-identical round-trip (records=2427)

Testing PYR: /home/will/seasons/s5/Assn/_DEFAULT.PYR
  File size: 228864 bytes
  PASS: byte-identical round-trip (records=1191)

Testing PYR: /home/will/seasons/s10/Assn/_DEFAULT.PYR
  File size: 228864 bytes
  PASS: byte-identical round-trip (records=1191)

============================================================
ROUNDTRIP TEST SUMMARY (PYR)
============================================================
PASS | s5              | /home/will/seasons/s5/Assn/MLBPA97.PYR
PASS | s10             | /home/will/seasons/s10/Assn/MLBPA97.PYR
PASS | s5-default      | /home/will/seasons/s5/Assn/_DEFAULT.PYR
PASS | s10-default     | /home/will/seasons/s10/Assn/_DEFAULT.PYR

Passed: 4/4
```

### Test Details

| Test Label | File | Size (bytes) | Records | Result |
|------------|------|-------------|---------|--------|
| s5 MLBPA97 | /home/will/seasons/s5/Assn/MLBPA97.PYR | 385536 | 2007 | PASS |
| s10 MLBPA97 | /home/will/seasons/s10/Assn/MLBPA97.PYR | 466176 | 2427 | PASS |
| s5 DEFAULT | /home/will/seasons/s5/Assn/_DEFAULT.PYR | 228864 | 1191 | PASS |
| s10 DEFAULT | /home/will/seasons/s10/Assn/_DEFAULT.PYR | 228864 | 1191 | PASS |

### Verification

Each test:
1. Reads original file bytes
2. Decodes using pyr_io.read() (inverts per-file substitution table)
3. Writes decoded records back using pyr_io.write()
4. Compares output bytes (original == roundtrip)
5. Confirms byte-identical match

All files passed byte-identical comparison, confirming the PYR format is fully understood and can be round-tripped without loss.

---

## mlbpa97.DAT Format (Stats Container)

**Status: NO WRITER EXISTS**

Reader exists: `/home/will/bbpro98/work/parse_stats.py` + `lib.py` filter
Writer: NONE (not yet implemented)

Action: Cannot test round-trip until a writer is implemented. Current reader is read-only and has been verified against game screen output (NOTES_stats_format.md, 2026-10-06).

---

## Other Formats

| Format | Reader | Writer | Round-Trip Status |
|--------|--------|--------|-------------------|
| SHELL.VOL, SHELL1.VOL, SHELL2.VOL | volcodec.py | YES | byte round-trip all three (2026-10-07) |
| SIM.DAT | NO | NO | Cannot test |
| ASN | (in progress) | NO | (pending TASK 4) |
| bb.cfg | NO | NO | Cannot test |

---

## Conclusion

**PYR is VERIFIED as fully decoded and round-trippable.** The 4-test suite covers 3 distinct file snapshots (s5 MLBPA97, s10 MLBPA97, both DEFAULT) with 2007, 2427, and 1191 records respectively, all of which pass byte-identical comparison.

No other formats currently have both a reader and a writer, so round-trip testing is not possible until writers are implemented.
