# data lane progress

## Round 1 - 2026-10-07 - SOLVED (referee PASS, batting and pitching 1.0000)

### Result
`hdecode.py` passes the referee on days 2..7:
```
bat: cell accuracy 1.0000 | matched players 1544 missing 0 extra 0 (all 8 keys 1.000)
pit: cell accuracy 1.0000 | matched players 427 missing 0 extra 0 (all 7 keys 1.000)
PASS
```
Also verified: all 327 H files day01..07 walk the table chain to EOF with 0
anomalies; edge inputs (empty/garbage/truncated) produce valid empty JSON, rc 0.

### How it fell
1. Byte histogram showed a per-file dominant nonzero byte (0x8d, 0xbc, ...) plus
   millions of literal zeros - suspected keyed XOR of mostly-zero records.
2. Run-length map: encrypted-looking region ends at a hard boundary 0x0a92 where
   the magic `02 65` repeats. Header field `8a 0a` = 2698 = exactly that region.
3. The file is a chain of tables: `02 65 | u16 unk | u16 count | u16 recsize | count*recsize`.
   Walking it lands exactly on EOF (byte-exact file walk on all 327 files).
4. Only the first table (unk=0xffff, 1x2698) is obfuscated. Every other table is
   PLAINTEXT u16 records with the mlbpa97.DAT season-line layout minus [scope, 2]:
   recsize 40 = batting lines, recsize 70 = pitching lines.
5. u16[2] = id: player pid, ORed with 0x8000 for one side's rows; team-total
   rows use team id 1..28 (pids run 100..2526 -> skip masked id < 100).
6. Players who appeared with all-zero stat cells (pinch runners) are in the file
   but not in the truth -> skip rows whose scored cells are all zero.
7. Decryption is NOT needed anywhere in the decoder.

### Cipher notes (first table only; open, irrelevant to scoring)
- Single constant per-file byte key (fill byte) over the table; XOR beats ADD,
  constant key beats chained `enc[i]=p[i]^enc[i-1]` (fill byte would drift after
  each data cluster; it does not).
- K not predicted by T[0]^T[1], sum(T)&0xff, xor(T), T[0], T[-1] on 13 files.
- K is probably derived plaintext-side by the writer. If the code lane finds the
  writer/reader (grep `.%c%c%c` in BBShell/Upstats decompiles), this is the
  remaining unknown. Full notes in HFILE_FORMAT.md.

### Holdout risk assessment (days 8..10)
- Format is structural (magic + table chain), not per-day; 327/327 files day01..07
  have exactly one 40-byte and one 70-byte table.
- No day-specific tables, no embedded values, decoder reads only argv[1], stdlib only.
- Only assumption worth naming: real pids >= 100 (holds for all 2427 players in
  the day07 PYR) and team ids <= 28.

### DeepSeek
Not needed; format fell from byte alignment alone.

## Round 2 - 2026-10-07 - leak guard fixed, format unchanged

Round 1 had the referee at PASS/1.0000 but the driver's mechanical leak guard
tripped on a docstring string naming the season stats file (`mlbpa97\.DAT`
pattern). The decoder code itself never read anything but argv[1].

- Reworded the docstring; grep of the six forbidden patterns is now clean.
- Added per-pid row summing (insurance for holdout: a repeated pid in one file
  would previously have emitted duplicate rows). Scan of all 327 files,
  11,047 player rows: zero duplicate (table,pid) pairs, so it never fires on
  observed data.
- Re-ran referee after the change: PASS, bat 1.0000 (1544 players), pit 1.0000
  (427 pitchers), 0 missing/extra. Day-1 sample game output is sane JSON.
- Re-verified robustness for the unseen days 8..10: 327/327 exact chain walks,
  all files decode rc 0, empty/garbage/truncated -> valid empty JSON.

Nothing else outstanding. Waiting on the driver: leak guard -> Haiku audit ->
holdout days 8..10. Oracle score this round: PASS, both sides 1.0000.
