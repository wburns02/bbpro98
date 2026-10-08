# Shell string tables (SHELL.VOL: ASNEWS, TMNEWS, PONEWS, ASSERTXT, BOXTEXT, PREFSCRN, PRINTTBL, PRINTTXT, ROSTEXT)

Codec: `work/strtable.py` (decode/encode JSON; strings and sections may grow, shrink, be added or removed). It
round-trips all nine files byte for byte and passes `re/targets/voldatref.py` both visible and `--holdout`.

Claude mapped the format from the BBShell reader FUN_68051ac0. It replaces the voltext GLM code lane's layout, which
had three problems:
- It read W[0] as a "section count" followed by byte pointers.
- It called the first string unreferenced.
- It glued ROSTEXT's last index bytes ("AJA") onto the first string to satisfy the coverage check. The referee now
  accepts a printable run whose tail is one whole decoded string.

## Layout

| Off | Field |
|---|---|
| 0 | u16 total = file length - 3 |
| 2 | u16 W[] word array (W[k] at file offset 2 + 2k) |
| | W[s], s < nsec: word index of section s's first string entry. Section 0 starts right after these words, so W[0] = nsec. |
| | W[nsec..]: one entry per string = file offset of the string - 2 |
| 2 + 2·len(W) | NUL-terminated latin-1 strings, back to back in entry order |
| end | 1 NUL |

## Reader

The reader is FUN_68051ac0(alloc, file, s, count, dest), opened by FUN_680510c0 (VOL entry or loose file):

1. A = W[s].
2. Start = W[A], end = W[A + count].
3. Read file[start+2 .. end+2) into one buffer.
4. dest[j] = buffer + W[A+j] - start, for j < count.
5. FUN_68051c50 turns every `\` into a newline, so a trailing `\` in a print template is a line break.

So every section read this way ends with an empty end-marker string that bounds the read. All files carry it except
ASSERTXT. The codec drops it from the JSON and adds it back (`_end_markers`).

## Sections and readers

| File | Sections (strings, without the end marker) | Read at (BBShell `_all.c` line) |
|---|---|---|
| ASNEWS | 1 × 305: news months, roster levels, transaction/injury/free-agent templates (`~4` field, `~5` team, `~6` plain colour codes) | 4736, count 0x131 |
| TMNEWS | 1 × 305: the ASNEWS set with team-news prompts | 33840, count 0x131 |
| PONEWS | 1 × 11: playoff news templates | 24994, count 0xb |
| BOXTEXT | 1 × 133: box-score labels, weekdays, months, ordinals, positions, stat labels, row templates (`\|1..\|9` column markers), game-data and wind lines | 11931, count 0x85 |
| ROSTEXT | 4: 4 data-view names; 11 handedness/status letters; 483 stat abbreviations; 483 matching full descriptions (sections 2 and 3 are parallel arrays) | 15325/15326, 10055/10057, 76742/76743 |
| PREFSCRN | 1 × 43: shell screen captions | 25566 (FUN_68051aa0) |
| PRINTTBL | 7 × 18: per-report column printf formats | 26156 |
| PRINTTXT | 8 report sections (11, 34, 8, 9, 9, 10, 8, 10): report templates | 9916, 14468, 2215, ... |
| ASSERTXT | 1 × 55, no end marker: startup and error messages | loader not located |

Limits: offsets are u16, so a table must stay under 64 KB (ROSTEXT is 16.7 KB).
