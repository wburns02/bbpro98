# progress.md — lane `code` (round 5)

## Status: dmp.py written, referee PASS (visible + all 4 holdout synth files)

## What was done this round

Rounds 1-4 wrote nothing (GLM 429 rate-limit deaths; same for both Explore
subagents I spawned this round — the Z.AI quota kills anything parallel, so all
work below was done serially in-lane).

1. **Loader** (`FUN_68024001`, caller `FUN_680037a7` passes expected count 0x42=66;
   FastSim twin `FS_FUN_6801ccf1`): container confirmed as
   `u16 n | u32 offsets[n+1] | n blobs`, each blob copied into a 0xf86 path object.
2. **Path object** (`FUN_68023f28`): 6-byte header (`u16 keyframe_count` at +0,
   two u16 at +2/+4) + 64 frame elements of 0x3e bytes (`_vector_constructor_iterator_(this+6, 0x3e, 0x40, FUN_68024340)`).
3. **Keyframe** (`FUN_68024340`): 10 six-byte point objects + trailing u16 member
   initialised to 0 -> 10 (x,y,z) s16 points + 1 event word (word 31).
4. **Event word decoded**: Sync.cpp (`FUN_68071312`, table built by `FUN_68071888`,
   66 x 42-byte records) tests the trailing u16 of each keyframe with
   `FUN_68072730/68072760/68072790` = AND 0x1/0x2/0x4 via `FUN_68002c20`
   (`(*p & bits) == bits`); the getters error "Invalid catch/throw/tag frame".
   Bits: **0x1 = catch keyframe, 0x2 = throw keyframe, 0x4 = tag keyframe**.
   At those keyframes it stores point 2 (catch, tag) and point 1 (throw) as the
   play's sync points -> identifies point 1 = throw hand, point 2 = glove hand.
5. **Body segments**: pairwise distances across every keyframe of every path show
   5 rigid pairs: (0,5) 56.8, (1,6) 33.7, (2,7) 33.8, (3,8) 49.2, (4,9) 49.5
   (sd ~1 unit) -> word order = [pelvis, throw hand, glove hand, throw-side foot,
   glove-side foot, head, throw elbow, glove elbow, throw-side knee,
   glove-side knee]; segment i = points (i, i+5).
6. **Axes**: z = height (feet ~0, standing head ~147, never negative);
   y = clip-forward (pitch/delivery clips stride +y); x = across, negated by the
   engine mirror bit (`FUN_68003c86`/`FUN_68003a26` negate when `FUN_68006410`
   fires). Throw-hand side is +x in 63/64 non-empty shipped paths.
7. **Playback**: movers hold path id (+0x1e), step +0x2a (+1/-1 ping-pong),
   keyframe cursor +0x2e; `FUN_680063b0(manager, id)` selects the path,
   `FUN_680060c0` reads its count, `FUN_680060e0`/`FUN_68006210`/`FUN_68006310`
   read points by (frame, point).
8. **Header words +2/+4**: zero in all 66 paths; every caller of the path getter
   in both decompiles checked (`FUN_68003a26, FUN_68003c86, FUN_68004037,
   FUN_68006530, FUN_6805d3f0, FUN_68071888`; FastSim `FS_FUN_68003a0e,
   68003c6e, 6800401f, 680064e0, 6804aee0, 6805b4a8`) — no reader found.
   Named `unused_header_word_a/b` with a factual note rather than inventing a meaning.

## Referee output (visible file)

    {"file": "DMP.DAT", "ok": true, "paths": 66}
    PASS

Holdout (`--holdout`): synth0..synth3 all `ok: true`, PASS.

## Environment caveat (important for the driver)

This box has no systemd (`/run/user` missing, "System has not been booted with
systemd as init system"), so `dmpref.py`'s jail (`jailutil.jail`:
`systemd-run --user --scope ... bwrap ...`) cannot run here for ANY lane — it
fails with "Failed to connect to user scope bus". I did not touch the referee;
for local verification I copied `dmpref.py` + `jailutil.py` to /tmp and patched
the copy to drop only the `systemd-run` prefix (bwrap + prlimit flags verbatim).
The codec itself was also smoke-tested under the exact bwrap/prlimit/clearenv
jail flags the referee uses (decode, encode, byte-identical round trip).

## Deliverables

- `dmp.py` — decode/encode, stdlib only, ~18 KB. `encode(decode(x)) == x` byte-exact;
  rebuilds from JSON (resize/value edits verified by the referee's trusted parser).
- `FORMAT.md` — full format doc with code addresses and the 66-path census
  (frames, catch/throw/tag keyframes, duplicate map).

## Ideas for a later round

- Which play state selects which path id lives in the play data (numdbm*.dat /
  arcdbm*.dat pair with the same 66 slots), not in DMP.DAT — a data lane could
  correlate the sync records with numdbm to name the 66 plays.
- Exact world scale (~1.2 cm/unit estimate) needs the renderer transform, which
  is outside the DMP readers.
- `FUN_68002930(catch_y - 60, 0)` in the sync record (+0x10) may be a
  y->tick conversion; unverified.
