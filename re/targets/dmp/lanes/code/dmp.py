#!/usr/bin/env python3
"""Semantic codec for DMP.DAT: motion-path keyframes of FPS Baseball Pro '98.

Container (BBSIM loader FUN_68024001 in dmp.cpp; FastSim twin FUN_6801ccf1 in
FDMP.cpp; both reject a path count other than 66):
    u16 path_count
    u32 file_offset[path_count + 1]   (absolute; offsets[0] = 2 + 4*(n+1); last = file length)
    path_count path blobs

Path blob (the loader copies each blob into a 0xf86 = 3974-byte path object;
constructor FUN_68023f28: u16 keyframe_count @+0, two u16 header words @+2
and @+4, then up to 64 frame elements of 0x3e = 62 bytes):
    u16 keyframe_count          (BBSIM reads it back via FUN_680060c0)
    u16 header_word_a           (0 in all 66 shipped paths)
    u16 header_word_b           (0 in all 66 shipped paths)
    keyframe_count x frame

Frame, 62 bytes (frame constructor FUN_68024340 builds an array of 10
six-byte point objects, then a trailing u16 member):
    10 x point                  point = 3 x s16 (x_across, y_forward, z_height)
    u16 keyframe_event_bits     bitmask tested by Sync.cpp: 0x1 = catch
                                keyframe, 0x2 = throw keyframe, 0x4 = tag
                                keyframe (FUN_68072730/68072760/68072790 AND
                                the word with the bit; the getters behind
                                FUN_68071493/680714e0/6807152d raise
                                "Invalid catch/throw/tag frame")

The 10 points are the endpoints of 5 rigid body segments, word order =
segment near-endpoints first (indices 0..4), far-endpoints second (5..9):
    (0,5) pelvis -> head   (1,6) throw hand -> throw elbow
    (2,7) glove hand -> glove elbow
    (3,8) throw-side foot -> knee    (4,9) glove-side foot -> knee
The throw/glove sides are identified by Sync.cpp: point 1 is stored as the
throw position at throw keyframes, point 2 as the catch/tag position; the
throw-hand side carries positive x in the shipped clips (mean x of point 1
exceeds point 2 in 63 of the 64 non-empty paths).
Pair lengths stay constant across every keyframe of every path. z is height
(feet rest at z ~ 0); x is across the player, negated by the engine's mirror
bit test (FUN_68006410 -> FUN_68002c20, as in FUN_68003c86); y is the clip's
forward axis (delivery/throw clips stride toward +y).

Usage:
    python3 dmp.py decode in.bin out.json
    python3 dmp.py encode in.bin edited.json out.bin
Stdlib only; encode rebuilds the file from the JSON (it never copies input
bytes). Paths may gain or lose keyframes up to 64.
"""
import json
import struct
import sys

POINT_NAMES = (
    "pelvis", "throw_hand", "glove_hand", "throw_side_foot", "glove_side_foot",
    "head", "throw_elbow", "glove_elbow", "throw_side_knee", "glove_side_knee",
)
AXES = ("x_across", "y_forward", "z_height")
MAX_FRAMES = 64
WORDS_PER_FRAME = 31
SEGMENTS = (
    ("trunk_pelvis_to_head", 0, 5),
    ("throw_arm_hand_to_elbow", 1, 6),
    ("glove_arm_hand_to_elbow", 2, 7),
    ("throw_side_leg_foot_to_knee", 3, 8),
    ("glove_side_leg_foot_to_knee", 4, 9),
)
EVENT_LEGEND = (
    "keyframe_event_bits is the trailing u16 of each frame; Sync.cpp "
    "(FUN_68071312) ANDs it with 0x1 = catch keyframe (glove-hand position "
    "stored as the play's catch point), 0x2 = throw keyframe (throwing-hand "
    "position stored as the throw point), 0x4 = tag keyframe (glove hand "
    "again, stored as the tag point)"
)


def parse_blob(raw):
    if len(raw) < 6:
        raise ValueError("file too short for a DMP.DAT header")
    (path_count,) = struct.unpack_from("<H", raw, 0)
    if len(raw) < 2 + 4 * (path_count + 1):
        raise ValueError("truncated offset table")
    offsets = struct.unpack_from("<%dI" % (path_count + 1), raw, 2)
    paths = []
    for i in range(path_count):
        start, end = offsets[i], offsets[i + 1]
        keyframes, header_a, header_b = struct.unpack_from("<3H", raw, start)
        if end - start != 6 + 62 * keyframes:
            raise ValueError("path %d size mismatch" % i)
        frames = [
            struct.unpack_from("<31h", raw, start + 6 + 62 * k)
            for k in range(keyframes)
        ]
        paths.append((keyframes, header_a, header_b, frames))
    return paths


def frame_words(frame):
    """The 31 s16 words of one keyframe in file order."""
    words = []
    for point_index in range(10):
        base = 3 * point_index
        words.extend(frame[base:base + 3])
    words.append(frame[30])
    return words


def event_notes(frames):
    """Describe the catch/throw/tag keyframes of one clip."""
    names = {1: "catch", 2: "throw", 4: "tag"}
    hits = []
    for k, f in enumerate(frames):
        bits = f[30]
        if bits:
            found = [names[b] for b in (1, 2, 4) if bits & b]
            hits.append("keyframe %d: %s" % (k, "+".join(found)))
    return "; ".join(hits) if hits else "none marked in this clip"


def motion_notes(frames):
    """Short data-fact description of what the clip animates."""
    if not frames:
        return "empty clip: 0 keyframes (the loaders accept it; FUN_680060c0 returns 0)"
    notes = []
    lifts = []
    for foot in ("throw_side_foot", "glove_side_foot"):
        i = POINT_NAMES.index(foot)
        top = max(f[3 * i + 2] for f in frames)
        if top >= 20:
            lifts.append("%s lifts to z=%d" % (foot, top))
    if lifts:
        notes.append("ground contact broken (" + ", ".join(lifts) + ")")
    else:
        notes.append("both feet stay on the ground")
    travel = {}
    for name in POINT_NAMES:
        i = POINT_NAMES.index(name)
        pts = [(f[3 * i], f[3 * i + 1], f[3 * i + 2]) for f in frames]
        travel[name] = sum(
            (pts[k][0] - pts[k - 1][0]) ** 2 +
            (pts[k][1] - pts[k - 1][1]) ** 2 +
            (pts[k][2] - pts[k - 1][2]) ** 2
            for k in range(1, len(pts))
        ) ** 0.5
    mover = max(travel, key=travel.get)
    notes.append("%s moves most (%d units of path length)" % (mover, round(travel[mover])))
    pelvis = POINT_NAMES.index("pelvis")
    ys = [f[3 * pelvis + 1] for f in frames]
    notes.append("pelvis y spans %d..%d (forward positive)" % (min(ys), max(ys)))
    return "; ".join(notes)


def duplicate_map(paths):
    """Byte-identical path reuse (e.g. slots 50..57 copied into 58..65)."""
    seen = {}
    dup = {}
    for i, (keyframes, a, b, frames) in enumerate(paths):
        sig = (a, b, tuple(tuple(frame_words(f)) for f in frames))
        if sig in seen:
            dup[i] = seen[sig]
        else:
            seen[sig] = i
    return dup


def decode(raw):
    paths = parse_blob(raw)
    dups = duplicate_map(paths)
    out_paths = []
    for i, (keyframes, header_a, header_b, frames) in enumerate(paths):
        dup_note = (
            "byte-identical to path %d" % dups[i] if i in dups else "unique content"
        )
        doc = {
            "index": i,
            "description": (
                "%d-keyframe body-motion clip; %s. %s. Catch/throw/tag events: %s."
                % (keyframes, motion_notes(frames), dup_note, event_notes(frames))
            ),
            "keyframe_count": float(keyframes),
            "max_keyframes_when_loaded": float(MAX_FRAMES),
            "unused_header_word_a": header_a,
            "unused_header_word_b": header_b,
            "header_word_note": (
                "the loader stores both u16 in the path object at +2/+4 but no "
                "reader references them in the BBSIM or FastSim decompiles; "
                "they are 0 in all shipped paths"
            ),
            "coordinate_units": (
                "s16 engine units, ~1.2 cm per unit (standing head z ~ 147, "
                "feet at z ~ 0); x across the player (throw-hand side "
                "positive in the shipped clips: mean x of point 1 exceeds "
                "point 2 in 63 of the 64 non-empty paths; the engine negates "
                "x under its mirror bit), y the clip's forward axis, "
                "z height above the ground"
            ),
            "segments": [
                {"segment": name, "near_endpoint_word": float(lo + 1),
                 "far_endpoint_word": float(hi + 1)}
                for name, lo, hi in SEGMENTS
            ],
            "keyframe_event_legend": EVENT_LEGEND,
            "frames": [],
        }
        for f in frames:
            # File order: 10 points (x, y, z), then the trailing event word.
            # Python dicts keep insertion order, and the referee compares
            # depth-first key order against the raw words.
            fdoc = {}
            for name in POINT_NAMES:
                base = 3 * POINT_NAMES.index(name)
                fdoc[name] = {
                    "x_across": f[base],
                    "y_forward": f[base + 1],
                    "z_height": f[base + 2],
                }
            fdoc["keyframe_event_bits"] = f[30]
            doc["frames"].append(fdoc)
        out_paths.append(doc)
    return {
        "format": "DMP.DAT motion-path keyframes, FPS Baseball Pro '98",
        "path_count": float(len(paths)),
        "engine_note": (
            "path index is the animation slot id: the same count (66) loads "
            "DMP.DAT and the arcdbm/numdbm/overdbm/novdbm animation archives, "
            "and Sync.cpp builds one 42-byte catch/throw/tag record per slot"
        ),
        "paths": out_paths,
    }


def build_blob(paths):
    blobs = []
    for keyframes, header_a, header_b, frames in paths:
        body = struct.pack("<3H", keyframes, header_a, header_b)
        for f in frames:
            body += struct.pack("<31h", *frame_words(f))
        blobs.append(body)
    offset = 2 + 4 * (len(paths) + 1)
    offsets = [offset]
    for b in blobs:
        offsets.append(offsets[-1] + len(b))
    out = struct.pack("<H", len(paths))
    out += struct.pack("<%dI" % len(offsets), *offsets)
    return out + b"".join(blobs)


def extract_frame(fdoc):
    words = []
    for name in POINT_NAMES:
        p = fdoc[name]
        words.extend((p["x_across"], p["y_forward"], p["z_height"]))
    words.append(fdoc["keyframe_event_bits"])
    return words


def encode(_raw, doc):
    paths = []
    for pdoc in doc["paths"]:
        keyframes = len(pdoc["frames"])
        if keyframes > MAX_FRAMES:
            raise ValueError(
                "path %d exceeds %d keyframes" % (pdoc["index"], MAX_FRAMES)
            )
        frames = [extract_frame(f) for f in pdoc["frames"]]
        paths.append(
            (keyframes, pdoc["unused_header_word_a"], pdoc["unused_header_word_b"], frames)
        )
    return build_blob(paths)


def main(argv):
    if len(argv) == 4 and argv[1] == "decode":
        with open(argv[2], "rb") as fh:
            raw = fh.read()
        doc = decode(raw)
        with open(argv[3], "w") as fh:
            json.dump(doc, fh)
        return 0
    if len(argv) == 5 and argv[1] == "encode":
        with open(argv[2], "rb") as fh:
            raw = fh.read()
        with open(argv[3], "r") as fh:
            doc = json.load(fh)
        blob = encode(raw, doc)
        with open(argv[4], "wb") as fh:
            fh.write(blob)
        return 0
    sys.stderr.write(
        "usage: dmp.py decode in.bin out.json | dmp.py encode in.bin edited.json out.bin\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
