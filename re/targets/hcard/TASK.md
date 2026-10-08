# Task: a semantic read/write codec for the H-file lineup card (FPS Baseball Pro '98)

You are the codec builder. Work only inside your lane workspace `$LANE/`. Read `progress.md` there first if it exists,
continue from it, and append to it before you stop (what you tried, what you learned, the current referee output).

## Why
Every played game leaves a box-score file `Stats/MLBPA97.Hxx`. Its plaintext tables (batting rows, pitching rows) are
solved. The FIRST table, 2698 bytes, is enciphered and holds the game's lineup card: both teams, every player on the
active roster with the positions he played, the pitchers used, the batting order, and game facts (date, home city,
probably weather, attendance, time, ...). A codec that turns it into editable JSON and back unlocks editing any box
score's card.

## Format facts (verified by Claude, build on them)
- File: `02 65 | ff ff | 01 00 | 8a 0a | seed[2] | ciphertext[2696]`, then the plaintext box tables (`02 65 ...`).
- Cipher (`/home/will/bbpro98/work/fpscipher.py`, algorithm in `re/targets/cipher/lanes/data/CIPHER.md`): the two
  seed bytes build a substitution table; plain = inverse(table)[cipher]. Encipher the edited body with the SAME seed.
- Deciphered body: side 0 (the AWAY team) at 0x000, side 1 (HOME) at 0x533, each 0x533 bytes; a game tail from 0xa66.
  Per side: +0x00 team id (box-score tid, 1..28), +0x02 association name, +0x0b team name, +0x2d abbrev,
  +0x32 40 player slots of 21 bytes (u16 pid, 0 = empty; u16 at slot+2 = bitmask of positions played,
  bit 0 P, 1 C, 2 1B, 3 2B, 4 3B, 5 SS, 6 LF, 7 CF, 8 RF; higher bits are flags still to be named), then lists of pids
  (count byte + u16s) that look like the batting order and the pitchers used, and more.
- Tail: home city (8 chars), u32 day serial at 0xa72 (+1 per calendar day), then unknown bytes (weather? attendance?).
- Box tables in the same file: rec 40 = batting rows, rec 70 = pitching rows, u16 word 2 = pid (bit 15 = home side,
  < 100 = team row). `re/hfiles/lanes/data/hdecode.py` reads them.

## Goal
Write `$LANE/hcard.py` (Python 3 stdlib only, under 200 KB; it runs alone in a jail, so INLINE the cipher, never
import or open other files) with two commands:
```
python3 hcard.py decode in.H out.json
python3 hcard.py encode in.H edited.json out.H
```
`decode` writes at least:
```
{"game": {"month": int, "day": int, ...},
 "sides": [{"side": "away", "team_id": int, "abbrev": str, "name": str,
            "players": [{"pid": int, "positions": ["p","c","1b","2b","3b","ss","lf","cf","rf" subset], ...}
                        one per occupied player slot],
            "pitchers": [pids], ...},
           {"side": "home", ...}],
 ...}
```
- Name EVERY other field you can (batting order, starter / sub flags, the mask's high bits, per-slot extra words,
  the lists, home city, year, weather, ...) with real names and say what you know in FORMAT.md. Placeholder names
  (f12, byte_3a, unk7) for most fields fail the audit.
- `encode` rebuilds the file from `in.H` with game.month/day, each side's abbrev/name and each player's positions
  taken from `edited.json` (more editable fields are welcome), changing only the bytes those fields own and
  re-enciphering with the file's seed. `encode(x, decode(x))` must equal `x` byte for byte, so preserve flag bits.

## The referee (do not edit it)
`python3 /home/will/bbpro98/re/targets/hcardref.py /home/will/bbpro98/re/targets/hcard $LANE [-v]`
Files (read only): `/mnt/nvme/bbpro98/targets_data/stats/day01 .. day09/` (consecutive sim days: `MLBPA97.ASN`,
`mlbpa97.DAT`, the H files). Day k's new games = H names present on day k but not on day k-1. For every new game it
checks team ids vs the box tables, abbrev/name vs the league file, month/day vs that day's newly played schedule game,
players vs the occupied slots and the box-score players and the team roster, pitchers vs the box-score pitchers,
positions vs the slot masks and vs the stats database's fielding-line changes; round trip on every distinct H file;
an edit test on day05 and day09 (one player's positions, the away abbrev, the day +1). PASS = all visible checks.
Then a model audits your code and a decode summary, and the same checks run on a held-out day. Decode generically:
never special-case a file, game, team or date.

## Tools and budget
- Trusted helpers you may run (not import into hcard.py): `python3 /home/will/bbpro98/work/league.py decode ASN out.json`,
  `python3 /home/will/bbpro98/work/stats.py decode DAT out.json`, `python3 /home/will/bbpro98/work/fpscipher.py hblob H out.bin`.
- Decompiles: `/mnt/nvme/bbpro98/index/{BBSIM,BBShell,Upstats,...}/_all.c`.
- You are GLM-5.3-Flash. For a hard sub-problem you may ask DeepSeek: write a self-contained task file (paste all data
  it needs; it cannot see files) and run `cloud-code --file <task.txt> --mode full --llm-service hive --model deepseek/deepseek-v4.1-flash`.
- Do not run Wine or the game. Do not edit anything outside `$LANE/`. Do not git push.
- Document the format in `$LANE/FORMAT.md` (every field, its offset, the evidence).

Stop when the referee prints PASS, or when you are out of ideas for this round. Always leave `hcard.py` runnable and `progress.md` updated.

## Parallel lanes
Several GLM lanes work on this at once in `/home/will/bbpro98/re/targets/hcard/lanes/<lane>/`. At the start of every
round read the other lanes' `progress.md` and `FORMAT.md` (read-only to you) and reuse anything verified.
