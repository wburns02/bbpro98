# HMI HMP music (SIM.DAT .hmi chunks)

Codec: `work/hmp.py` (Claude, 2026-10-08). Extract and replace the chunks with `work/chunkdat.py unpack/pack`.

## In the game

SIM.DAT holds 13 chunks that start with `HMIMIDIP013195` (HMP version 2): directory slots 9-15 and 36-37 are named
in BBSIM's table at 0x680bb4b0 (13-byte entries: org1, org2, chgorg1-3, chgtpt1-4 .hmi), slots 1-4 have no name in
any binary.

Nothing plays them. BBSIM FUN_6803924e (charge cues) plays a WAV sound (FUN_6806ec17) for cue values 0-2 and calls
FUN_6806ed8b with name `0x680bb4b0 + (cue - 3) * 13` for cue values 3 and up. FUN_6806ed8b is an empty function in
the shipped binary (push ebp/ebx/esi/edi, jmp +0, pop, leave, ret): the DOS HMI SOS player was compiled out of the
Win95 build. Making the music audible needs a mod (src-latest/bbmod.h) that detours FUN_6806ed8b, loads the chunk
by name, converts it with this format and plays it through winmm.

## File

| Off | Size | JSON | Notes |
|---|---|---|---|
| 0x00 | 32 | version | "HMIMIDIP", then "013195" for version 2 ("" for version 1), zero filled |
| 0x20 | 4 | (derived) | length of header + tracks; the chunk can carry zero bytes after it (`pad`, 4-10 bytes) |
| 0x24 | 12 | at_0x24 | zero |
| 0x30 | 4 | (derived) | track count |
| 0x34 | 4 | division | ticks per quarter note, 192 |
| 0x38 | 4 | tick_rate | ticks per second, 120. A quarter lasts division / tick_rate = 1.6 s |
| 0x3c | 4 | seconds | floor(longest track's ticks / tick_rate), exact on all 13 |
| 0x40 | 16 x u32 | channel_priority | 0 for channel 0, 9 for 1-9, 0 above (not used by any code in the game) |
| 0x80 | 32 x 5 u32 | track_devices | per track, 5 HMI device ids (0xa002, 0xa005, 0xa007, 0xa00a seen) |
| 0x300 | 8 (v1) / 0x88 (v2) | header_tail | zero |
| 0x308 / 0x388 | | tracks | |

Track: u32 index, u32 length including this 12-byte header, u32 MIDI channel, then events. Each event = delta time
in HMP's own variable-length number (7 bits per byte, least significant group first, the last byte has bit 7 SET:
the reverse of standard MIDI), then a standard MIDI event with an explicit status byte. Meta (FF) and sysex lengths
use standard MIDI numbers. No running status and no non-canonical deltas occur; decode refuses both so encode stays
byte-exact. Track 0 holds only end-of-track on channel 9.

JSON events: `[delta, "hex bytes"]` per event. Encode checks each is exactly one MIDI event.

## Standard MIDI

`tomid`: SMF type 1, division as in the header, one MTrk per HMP track, the tempo meta `division * 1e6 / tick_rate`
microseconds per quarter (1,600,000) at the start of track 0. `frommid`: any type 0/1 SMF with PPQ timing; the first
tempo meta of track 0 sets tick_rate; `--template ORIG.hmi` keeps the original header tables, pad, track numbers and
channels, otherwise defaults are used and seconds is recomputed.

## Verification (2026-10-08)

- `hmp.py verify`: all 13 chunks byte-exact through JSON and through hmi -> mid -> hmi.
- The exported .mid files parse in mido (type 1, 192 PPQ) with lengths that match the header's seconds field.
- Edit test: transpose every note, insert a program change, encode/decode stable; template-free MIDI import gives the
  same events. Malformed events (missing data byte, truncated meta, bad delta) are refused.
