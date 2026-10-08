"""Semantic read/write codec for the DATA chunks of SIM.DAT and Stadia/*.DAT (+ .DT) of
FPS Baseball Pro '98 (chunk containers have magic 00 01 06 07; see work/chunkdat.py).

Each chunk id picks a layout (the id is stable per chunk role across all stadium files):

  e957  MI   stadium info: "STA:" + u32 restSize + fullName[64] [+ shortName[30] +
             park traits [102..136] + park geometry tail: foul/pole points and the
             fence line. The .DT variant is "STA:" + u32 + u8 kind + fullName[65].]
             Traits block: 12 x u16 observed (marker 6, roofed 66 = HOUSTON Astrodome,
             surface, wallStyle, screenSet, 4 palette ids, turfTint/Pattern, crowd)
             + 5 zero u16.
  e1a4  MI   SIM.DAT injury text: 22 u16 section offsets, 19 parameter sub-tables
             (u16 count + count*(u16,u16) pairs), 205 injury records (96 bytes:
             part u16, daysOut u16, stage u16, bodyPart[30], specificPart[30],
             severity[30]), 46 phase records (16 bytes), 12 outcome records (8 bytes).
  5200  PB   SIM.DAT in-game UI strings: u16 1, u16 count, count u16 offsets from the
             end of the offset table, then NUL-terminated strings.
  e6e7  @C   SIM.DAT camera views: named views plus camera anchor/position records.
  ce8c  @W   stadium walls: "GID:" + u32 len + u32 version + s16 left-field foul-line x +
             s16 center-field depth + s16 n/k/m + n*6 s16 wall records (checksum? no -
             (slope dummy, x, y, wallHeightA, wallHeightB, flag)) + trailing blocks
             (u16 flag, u16 kind, 4 x u16 pad).
  cb7c  WT   wall texture atlas: u32 pair faceCount + global dims + (faceCount-1) 30-byte
             records (dataOffset, width, height, unpacked = width*height) + a 6-byte
             closing record + the face bitmaps back to back (palette indices).
  7709  XT   texture atlas: same record style, LZ-packed faces (each face's stored
             byte count = the previous record's last u32; face 0's = header[7]).
  947d  HS   stadium big table: "DAT:" + u32 size + 17 u32 offsets + 16 sections of
             16-byte labels + (u32 marker, u16 count, u16 recsize) tables of s16 words.
  6be6  OL   SIM.DAT offense logic: u16 header + sections of 9-byte play records
             (each byte = a base-destination / fielder code 0..13).
  b0e7  UN   SIM.DAT uniform table: 756 sprite rows of (kind u16, frame u16, x s16, y s16);
             kind 0xffff = an unused row.
  bb43  MS   SIM.DAT misc: 6 u16 values.

usage: voldat.py decode NAME in.bin out.json
       voldat.py encode NAME in.bin edited.json out.bin
"""
import json
import struct
import sys


def rd_u16(d, o):
    return struct.unpack_from('<H', d, o)[0]


def rd_s16(d, o):
    return struct.unpack_from('<h', d, o)[0]


def rd_u32(d, o):
    return struct.unpack_from('<I', d, o)[0]


def cstr(d, o, n):
    """NUL-terminated (or fixed-width) string from d[o:o+n]."""
    end = d.find(b'\x00', o, o + n)
    if end < 0:
        end = o + n
    return d[o:end].decode('latin-1')


def enc_str(s, n):
    """String to n bytes NUL-padded."""
    b = s.encode('latin-1')
    if len(b) > n:
        b = b[:n]
    return b + b'\x00' * (n - len(b))


def all_pad_zero(b):
    return not b.strip(b'\x00')


# ---------------------------------------------------------------- e957 stadium info

def e957_decode(d):
    ln = rd_u32(d, 4)
    out = {
        '_format': 'stadium info',
        '_size_bytes': ln,
    }
    if len(d) <= 74:
        # .DT variant: "STA:" magic, u32 rest-size (its low byte 0x42 'B' reads as a printable
        # run with the magic), u8 flag, then a single name field
        tag = ''
        for c in d[:8].decode('latin-1'):
            if not (' ' <= c <= '~'):
                break
            tag += c
        out['asciiTag'] = tag
        out['_dt_flag'] = d[8]
        out['name'] = cstr(d, 9, 63)
        out['variantFlag'] = d[72]
        out['domeFlag'] = d[73]
        return out
    out['name'] = cstr(d, 8, 63)
    out['domeFlag'] = d[71]
    out['shortName'] = cstr(d, 72, 30)
    traits = [rd_u16(d, 102 + 2 * i) for i in range(12)]
    out['parkTraits'] = {
        'marker': traits[0],
        'roofed': traits[1],
        'surface': traits[2],
        'wallStyle': traits[3],
        'screenSet': traits[4],
        'paletteA': traits[5],
        'paletteB': traits[6],
        'paletteC': traits[7],
        'paletteD': traits[8],
        'turfTint': traits[9],
        'turfPattern': traits[10],
        'crowdDensity': traits[11],
    }
    geo = [rd_s16(d, 136 + 2 * i) for i in range(16)]
    out['parkGeometry'] = {
        'leftFieldPoleX': geo[4],
        'leftFieldPoleY': geo[5],
        'rightFieldPoleX': geo[6],
        'rightFieldPoleY': geo[7],
        'foulLinePointAX': geo[8],
        'foulLinePointAY': geo[9],
        'foulLinePointBX': geo[10],
        'foulLinePointBY': geo[11],
        'cornerPointAX': geo[12],
        'cornerPointAY': geo[13],
        'cornerPointBX': geo[14],
        'cornerPointBY': geo[15],
    }
    n = rd_s16(d, 168)
    pts = []
    for k in range(n):
        o = 170 + 6 * k
        if o + 6 > len(d):
            break
        pts.append({
            'x': rd_s16(d, o),
            'y': rd_s16(d, o + 2),
            'flag': rd_s16(d, o + 4),
        })
    g = out['parkGeometry']
    g['_fencePointCount'] = n
    g['fencePoints'] = pts
    return out


def e957_encode(doc, d):
    if len(d) <= 74 and doc.get('_dt_flag') is not None:
        # "STA:" + u32 rest-size + u8 flag + name; the tag's byte 4 = the size low byte
        tag = doc.get('asciiTag', 'STA:B').encode('latin-1')
        head = bytearray(d[:8])
        look = tag[:4]
        head[0:len(look)] = look
        head[5:5 + max(0, len(tag) - 5)] = tag[5:min(len(tag), 8)]
        return (bytes(head) + bytes([doc['_dt_flag']]) + enc_str(doc['name'], 63)
                + bytes([doc.get('variantFlag', 0), doc.get('domeFlag', 0)]))
    body = b''
    body += enc_str(doc['name'], 63)
    body += bytes([doc.get('domeFlag', 0)])
    body += enc_str(doc['shortName'], 30)
    t = doc['parkTraits']
    # traits record at 102..136: 17 u16s = 12 observable + 5 unused slots the game reads as 0
    body += struct.pack('<12H', t['marker'], t['roofed'], t['surface'], t['wallStyle'],
                        t['screenSet'], t['paletteA'], t['paletteB'], t['paletteC'],
                        t['paletteD'], t['turfTint'], t['turfPattern'], t['crowdDensity'])
    body += struct.pack('<5H', 0, 0, 0, 0, 0)
    g = doc['parkGeometry']
    # geometry tail from 136: 4 zero words, then 12 words (LF pole, RF pole, foul-line
    # feature pair, corner pair), then fencePointCount, then n * (x, y, flag) words
    body += struct.pack('<4h', 0, 0, 0, 0)
    body += struct.pack('<12h', g['leftFieldPoleX'], g['leftFieldPoleY'],
                        g['rightFieldPoleX'], g['rightFieldPoleY'],
                        g['foulLinePointAX'], g['foulLinePointAY'],
                        g['foulLinePointBX'], g['foulLinePointBY'],
                        g['cornerPointAX'], g['cornerPointAY'],
                        g['cornerPointBX'], g['cornerPointBY'])
    body += struct.pack('<h', len(g['fencePoints']))
    for p in g['fencePoints']:
        body += struct.pack('<3h', p['x'], p['y'], p['flag'])
    return d[:4] + struct.pack('<I', len(body)) + body


# ---------------------------------------------------------------- e1a4 injury text

def e1a4_decode(d):
    offs = [rd_u16(d, 2 * i) for i in range(22)]
    params = []
    for k in range(19):
        s = offs[k]
        n = rd_u16(d, s)
        pairs = []
        for j in range(n):
            pairs.append([rd_u16(d, s + 2 + 4 * j), rd_u16(d, s + 4 + 4 * j)])
        params.append({'_offset': s, '_count': n, 'pairs': pairs})
    injuries = []
    for k in range(205):
        o = 3948 + 96 * k
        injuries.append({
            'bodyPart': cstr(d, o + 6, 30),
            'specificPart': cstr(d, o + 36, 30),
            'severity': cstr(d, o + 66, 30),
            'daysOut': rd_u16(d, o + 2),
            'stage': rd_u16(d, o + 4),
            '_partIndex': rd_u16(d, o),
        })
    phases = []
    for k in range(46):
        o = 23628 + 16 * k
        phases.append({
            '_index': rd_u16(d, o),
            'stageA': rd_u16(d, o + 2),
            'stageB': rd_u16(d, o + 4),
            'rollA': rd_s16(d, o + 6),
            'rollB': rd_u16(d, o + 8),
            'rollC': rd_u16(d, o + 10),
            'outcomeDays': rd_u16(d, o + 12),
            'outcomeStage': rd_u16(d, o + 14),
        })
    outcomes = []
    for k in range(12):
        o = 24364 + 8 * k
        outcomes.append({
            '_index': rd_u16(d, o),
            'phase': rd_u16(d, o + 2),
            'stage': rd_u16(d, o + 4),
            'days': rd_u16(d, o + 6),
        })
    # 19 tuning words between the offset table and the first sub-table (offsets/knobs)
    tuning = [rd_s16(d, 44 + 2 * i) for i in range(19)]
    return {
        '_format': 'injury text',
        '_sectionOffsets': offs,
        'tuningWords': tuning,
        'paramTables': params,
        'injuries': injuries,
        'phases': phases,
        'outcomes': outcomes,
    }


def e1a4_encode(doc, d):
    # header: 22 u16 offsets + 19 tuning words + 19 sub-tables (sizes recomputed)
    blobs = []
    for t in doc['paramTables']:
        b = struct.pack('<H', len(t['pairs']))
        for a, b2 in t['pairs']:
            b += struct.pack('<2H', a, b2)
        blobs.append(b)
    # original order of sub-tables = ascending offsets; rebuild the same order
    src = doc['_sectionOffsets']
    order = sorted(range(19), key=lambda k: src[k])
    start = 82
    new_offs = {}
    for k in order:
        new_offs[k] = start
        start += len(blobs[k])
    out = bytearray()
    for k in range(19):
        out += struct.pack('<H', new_offs[k])
    out += struct.pack('<HHH', 3948, 23628, 24364)
    out += struct.pack('<19h', *doc['tuningWords'])
    assert len(out) == 82, len(out)
    body = bytes(out)
    for k in order:
        body += blobs[k]
    assert len(body) == 3948, len(body)
    for inj in doc['injuries']:
        body += struct.pack('<3H', inj['_partIndex'], inj['daysOut'], inj['stage'])
        body += enc_str(inj['bodyPart'], 30)
        body += enc_str(inj['specificPart'], 30)
        body += enc_str(inj['severity'], 30)
    for ph in doc['phases']:
        body += struct.pack('<8H', ph['_index'], ph['stageA'], ph['stageB'],
                            ph['rollA'] & 0xFFFF, ph['rollB'], ph['rollC'],
                            ph['outcomeDays'], ph['outcomeStage'])
    for oc in doc['outcomes']:
        body += struct.pack('<4H', oc['_index'], oc['phase'], oc['stage'], oc['days'])
    return body


# ---------------------------------------------------------------- 5200 UI strings

def pb5200_decode(d):
    n = rd_u16(d, 2)
    base = 6 + 2 * n  # after flag+count, offsets, and the total-size u16
    strings = []
    for k in range(n):
        o = base + rd_u16(d, 4 + 2 * k)
        strings.append(cstr(d, o, len(d) - o))
    return {'_format': 'game text', '_flag': rd_u16(d, 0), 'strings': strings}


def pb5200_encode(doc, d):
    strs = [s.encode('latin-1') + b'\x00' for s in doc['strings']]
    n = len(strs)
    # layout: flag u16, count u16, n offsets, u16 strings-block size, then the strings;
    # the size = bytes after the size u16 itself
    total = sum(len(s) for s in strs)
    body = struct.pack('<2H', doc['_flag'], n)
    offs = []
    pos = 0
    for s in strs:
        offs.append(pos)
        pos += len(s)
    body += struct.pack('<%dH' % n, *offs)
    body += struct.pack('<H', total)
    body += b''.join(strs)
    return body


# ---------------------------------------------------------------- bb43 misc

def ms_decode(d):
    return {'_format': 'misc', 'values': [rd_u16(d, 2 * i) for i in range(6)]}


def ms_encode(doc, d):
    return struct.pack('<6H', *doc['values'])


# ---------------------------------------------------------------- ce8c walls

def w_decode(d):
    n = rd_s16(d, 20)
    kd = rd_s16(d, 22)
    m = rd_s16(d, 24)
    recs = []
    for k in range(n):
        o = 26 + 12 * k
        recs.append({
            'slope': rd_s16(d, o),
            'x': rd_s16(d, o + 2),
            'y': rd_s16(d, o + 4),
            'wallHeightFront': rd_s16(d, o + 6),
            'wallHeightBack': rd_s16(d, o + 8),
            'flag': rd_s16(d, o + 10),
        })
    blocks = []
    o = 26 + 12 * n
    while o + 10 <= len(d):
        blocks.append({
            'flag': rd_s16(d, o),
            'blockKind': rd_s16(d, o + 2),
            'pads': [rd_u16(d, o + 4 + 2 * j) for j in range(3)],
        })
        o += 10
    tail = b''
    if o < len(d):
        tail = d[o:]
    out = {
        '_format': 'stadium walls',
        '_magic': d[:4].decode('latin-1'),
        '_size': rd_u32(d, 4),
        '_version': rd_u32(d, 8),
        'leftFieldFoulLineX': rd_s16(d, 16),
        'centerFieldDepth': rd_s16(d, 18),
        '_wallPointCount': n,
        '_blockCount': kd,
        '_tailCount': m,
        'wallPoints': recs,
    }
    if len(blocks) == kd:
        out['blocks'] = blocks
    else:
        out['blocks'] = blocks
        out['_tailHex'] = tail.hex()
    return out


def w_encode(doc, d):
    body = d[:4] + struct.pack('<I', doc['_size']) + struct.pack('<I', doc['_version'])
    body += struct.pack('<HH', 0, 0)  # two reserved zero words reserved
    body += struct.pack('<2h', doc['leftFieldFoulLineX'], doc['centerFieldDepth'])
    body += struct.pack('<3h', len(doc['wallPoints']), doc['_blockCount'], doc['_tailCount'])
    for w in doc['wallPoints']:
        body += struct.pack('<6h', w['slope'], w['x'], w['y'],
                            w['wallHeightFront'], w['wallHeightBack'], w['flag'])
    for bl in doc['blocks']:
        body += struct.pack('<2H3H', bl['flag'], bl['blockKind'], *bl['pads'])
    if doc.get('_tailHex'):
        body += bytes.fromhex(doc['_tailHex'])
    return body


# ---------------------------------------------------------------- cb7c wall texture
#
# Header: 8 u32 = [faceCount, faceCount, bitmapWidth, bitmapHeight, 0, 0,
#                   bytesPerFace, bytesPerFace].  Then (faceCount-1) records of
# 30 bytes + a 6-byte closing record: each record is u16 lead (0) + u32 data
# offset + u32 width + u32 height + u32 0 + u32 0 + u32 bytesPerFace +
# u32 bytesPerFace.  The bitmap data of face k starts at its record's data
# offset; face k's byte count = faceCount == header[0] (# wall segments: 7 for
# most parks, 8 for Kansas City's waterfalls) * bytesPerFace trailing bytes,
# except CHICAGON (Wrigley) whose first two faces are 32x15 (480 bytes each).

def wt_decode(d):
    face_count = rd_u32(d, 0)
    faces = []
    offs = [rd_u32(d, 32 + 30 * k + 2) for k in range(face_count)]
    for k in range(face_count):
        o = 32 + 30 * k
        off = offs[k]
        w = rd_u32(d, o + 6)
        h = rd_u32(d, o + 10)
        nbytes = (offs[k + 1] - off) if k + 1 < face_count else len(d) - off
        data = d[off:off + nbytes]
        rows = []
        for r in range(0, len(data) - len(data) % 8, 8):
            rows.append([data[r + j] for j in range(8)])
        face = {'_dataOffset': off, '_recordBytes': nbytes, 'paletteIndexGroups': rows}
        if k == face_count - 1:
            # the last record is only 6 bytes (lead + offset): no dims are
            # stored for the last face (holds for all 28 parks)
            face['_width'] = w
            face['_height'] = h
        else:
            face['width'] = w
            face['height'] = h
        faces.append(face)
    head = [rd_u32(d, 4 * i) for i in range(8)]
    return {
        '_format': 'wall texture atlas',
        '_headWidth': rd_u32(d, 8),
        '_headHeight': rd_u32(d, 12),
        'faces': faces,
    }


def wt_encode(doc, d):
    face_count = len(doc['faces'])
    base = 32 + (face_count - 1) * 30 + 6
    offs = []
    sizes = []
    pos = base
    for f in doc['faces']:
        offs.append(pos)
        sizes.append(len(f['paletteIndexGroups']) * 8)
        pos += sizes[-1]
    f0 = doc['faces'][0]
    out = struct.pack('<8I', face_count, face_count, doc['_headWidth'], doc['_headHeight'],
                      0, 0, f0['width'] * f0['height'], f0['width'] * f0['height'])
    recs = b''
    for k, f in enumerate(doc['faces']):
        off = offs[k]
        if k == face_count - 1:
            # the closing record is only 6 bytes; no dims are stored for it
            recs += struct.pack('<HI', 0, off)
        else:
            # o3/o4 = the face's unpacked size (width * height)
            recs += struct.pack('<H7I', 0, off, f['width'], f['height'],
                                0, 0, f['width'] * f['height'], f['width'] * f['height'])
    for f in doc['faces']:
        if len(f['paletteIndexGroups']) * 8 > f['_recordBytes']:
            raise ValueError('face rows exceed the stored byte count')
    flat = []
    for f in doc['faces']:
        for g in f['paletteIndexGroups']:
            flat += [v & 0xFF for v in g]
    body = out + recs + bytes(flat)
    return body


# ---------------------------------------------------------------- 6be6 offense logic

def ol_decode(d):
    start = rd_u16(d, 0)
    ends = [rd_u16(d, 2 + 2 * i) for i in range(4)]
    secs = []
    bounds = [start] + ends + [len(d)]
    for i in range(5):
        s, e = bounds[i], bounds[i + 1]
        recs = []
        for o in range(s, e, 9):
            rec = d[o:o + 9]
            recs.append({
                'leadCodes': [rec[0], rec[1], rec[2]],
                'midCodes': [rec[3], rec[4], rec[5]],
                'lastCodes': [rec[6], rec[7], rec[8]],
            })
        secs.append({'_start': s, '_end': e, '_recordCount': len(recs), 'records': recs})
    return {'_format': 'offense logic', 'sections': secs}


def ol_encode(doc, d):
    secs = doc['sections']
    head = struct.pack('<H', 10)
    body_blobs = []
    for sec in secs:
        b = b''
        for r in sec['records']:
            b += bytes(r['leadCodes'] + r['midCodes'] + r['lastCodes'])
        body_blobs.append(b)
    # first 4 sections have offsets in the header; the last is the tail
    pos = 10
    ends = []
    for i, b in enumerate(body_blobs[:4]):
        pos += len(b)
        ends.append(pos)
    out = head + struct.pack('<4H', *ends) + b''.join(body_blobs)
    return out


# ---------------------------------------------------------------- b0e7 uniform table

def un_decode(d):
    rows = []
    for k in range(len(d) // 8):
        o = 8 * k
        rows.append({
            'spriteKind': rd_u16(d, o),
            'frame': rd_u16(d, o + 2),
            'posX': struct.unpack_from('<h', d, o + 4)[0],
            'posY': struct.unpack_from('<h', d, o + 6)[0],
        })
    return {'_format': 'positions', 'rows': rows}


def un_encode(doc, d):
    out = b''
    for r in doc['rows']:
        out += struct.pack('<4H', r['spriteKind'] & 0xFFFF, r['frame'],
                           r['posX'] & 0xFFFF, r['posY'] & 0xFFFF)
    return out


# ---------------------------------------------------------------- e6e7 cameras

def cam_decode(d):
    n_view_slots = rd_u16(d, 0)
    # 15 anchor records of 26 bytes from 28 to 418
    anchors = []
    for k in range(15):
        o = 28 + 26 * k
        anchors.append({
            'head': rd_u16(d, o),
            'x': struct.unpack_from('<i', d, o + 2)[0],
            'y': struct.unpack_from('<i', d, o + 6)[0],
            'z': struct.unpack_from('<i', d, o + 10)[0],
            'params': [struct.unpack_from('<h', d, o + 14 + 2 * j)[0] for j in range(6)],
        })
    views = []
    for k in range(10):
        o = 418 + 64 * k
        views.append({'name': cstr(d, o, 64)})
    # 1058..1192: inter-view layout block (counts, orbit params; semantics unresolved)
    layout = d[1058:1192]
    lw = [struct.unpack_from('<h', layout, 2 * i)[0] for i in range(4)]
    groups = []
    pos, last = 1192, 5066  # 149 full 26-byte records, then a truncated final position
    while pos + 15 * 26 <= last:
        recs = []
        for k in range(15):
            o = pos + 26 * k
            recs.append({
                'head': rd_u16(d, o),
                'x': struct.unpack_from('<i', d, o + 2)[0],
                'y': struct.unpack_from('<i', d, o + 6)[0],
                'z': struct.unpack_from('<i', d, o + 10)[0],
                'params': [struct.unpack_from('<h', d, o + 14 + 2 * j)[0] for j in range(6)],
            })
        groups.append(recs)
        pos += 15 * 26
    # records of the final (short) group
    final_recs = []
    while pos + 26 <= last:
        o = pos
        final_recs.append({
            'head': rd_u16(d, o),
            'x': struct.unpack_from('<i', d, o + 2)[0],
            'y': struct.unpack_from('<i', d, o + 6)[0],
            'z': struct.unpack_from('<i', d, o + 10)[0],
            'params': [struct.unpack_from('<h', d, o + 14 + 2 * j)[0] for j in range(6)],
        })
        pos += 26
    le = len(d)
    tail = {
        'head': rd_u16(d, pos) if pos + 2 <= le else 0,
        'x': struct.unpack_from('<i', d, pos + 2)[0] if pos + 6 <= le else 0,
        'y': struct.unpack_from('<i', d, pos + 6)[0] if pos + 10 <= le else 0,
        # z: only the low word may fit (the file ends with a half-written s32)
        'z': struct.unpack_from('<h', d, pos + 10)[0] if pos + 12 <= le else 0,
        '_tailBytes': le - pos,
    }
    return {
        '_format': 'camera views',
        '_slotCount': n_view_slots,
        'defaults': anchors,
        'views': views,
        '_layoutHex': layout.hex(),
        '_layoutHeadWords': lw,
        'viewGroups': [{'records': g} for g in groups],
        'finalGroup': final_recs,
        'finalPosition': tail,
    }


def cam_encode(doc, d):
    # preserve the 28-byte verbatim head (slot count + view dims + 4 tuning s32s)
    out = bytearray(d[:28])
    struct.pack_into('<H', out, 0, doc['_slotCount'])
    for a in doc['defaults']:
        out += struct.pack('<H3i', a['head'], a['x'], a['y'], a['z'])
        for p in a['params']:
            out += struct.pack('<h', p)
    for v in doc['views']:
        out += enc_str(v['name'], 64)
    out += bytes.fromhex(doc.get('_layoutHex', ''))
    for g in [x['records'] for x in doc['viewGroups']] + doc.get('finalGroup', []):
        recs = g if isinstance(g, list) else [g]
        for a in recs:
            out += struct.pack('<H3i', a['head'], a['x'], a['y'], a['z'])
            for p in a['params']:
                out += struct.pack('<h', p)
    t = doc['finalPosition']
    nb = t.get('_tailBytes', 14)
    out += struct.pack('<H', t['head'])
    if nb >= 6:
        out += struct.pack('<i', t['x'])
    if nb >= 10:
        out += struct.pack('<i', t['y'])
    if nb >= 12:
        out += struct.pack('<h', t['z'])  # truncated low word of the s32 z
        if nb >= 14:
            out += struct.pack('<h', (t['z'] >> 16) & 0xFFFF)
    return bytes(out)


# ---------------------------------------------------------------- 947d stadium table

def hs_decode(d):
    # "DAT:" + u32 size + 17 u32 offsets + 16 sections. Each section body after the 16-byte
    # label is a walk of (u16 kind, u16 nbytes) blocks of s16 words; sections whose body does
    # not start with such a block header are decoded as plain s16 word groups of 8.
    offs = [rd_u32(d, 8 + 4 * i) for i in range(17)]
    sections = []
    for i in range(16):
        s = offs[i]
        e = offs[i + 1] if i < 15 else len(d)
        seg = d[s:e]
        label = seg[:16]
        o = s + 16
        blocks = []
        while o + 4 <= e:
            kind = rd_u16(d, o)
            nbytes = rd_u16(d, o + 2)
            if kind not in (1, 2) or o + 4 + nbytes > e:
                break
            body = d[o + 4:o + 4 + nbytes]
            wv = [struct.unpack_from('<h', body, j)[0]
                  for j in range(0, len(body) // 2 * 2, 2)]
            groups = [wv[r:r + 8] for r in range(0, len(wv), 8)]
            tailb = body[len(body) // 2 * 2:]
            blocks.append({'_kind': kind, '_nbytes': nbytes,
                           'wordGroups': groups,
                           '_tailBytes': list(tailb)})
            o += 4 + nbytes
        if blocks:
            rest = seg[o - s:]
            rw = [struct.unpack_from('<h', rest, j)[0]
                  for j in range(0, len(rest) // 2 * 2, 2)]
            sections.append({'_label': label.hex(), '_offset': s,
                             'blocks': blocks,
                             'restWordGroups': [rw[r:r + 8] for r in range(0, len(rw), 8)],
                             '_restTail': list(rest[len(rest) // 2 * 2:])})
        else:
            # no block structure: plain s16 words in groups of 8
            wv = [struct.unpack_from('<h', seg, j)[0]
                  for j in range(16, len(seg) // 2 * 2, 2)]
            sections.append({'_label': label.hex(), '_offset': s,
                             'wordGroups': [wv[r:r + 8] for r in range(0, len(wv), 8)],
                             '_tailBytes': list(seg[len(seg) // 2 * 2:])})
    return {'_format': 'stadium table', 'sections': sections}


def hs_encode(doc, d):
    offs = [rd_u32(d, 8 + 4 * i) for i in range(17)]
    body = bytearray(d[:offs[0]])
    for i, sec in enumerate(doc['sections']):
        s = offs[i]
        e = offs[i + 1] if i < 15 else len(d)
        chunk = bytearray()
        chunk += bytes.fromhex(sec['_label'])
        if sec.get('blocks'):
            for bl in sec['blocks']:
                chunk += struct.pack('<2H', bl['_kind'], bl['_nbytes'])
                for g in bl['wordGroups']:
                    chunk += struct.pack('<%dh' % len(g), *g)
                tb = bl.get('_tailBytes', [])
                if tb:
                    chunk += bytes(tb)
            for g in sec.get('restWordGroups', []):
                chunk += struct.pack('<%dh' % len(g), *g)
            chunk += bytes(sec.get('_restTail', []))
        else:
            for g in sec['wordGroups']:
                chunk += struct.pack('<%dh' % len(g), *g)
            chunk += bytes(sec.get('_tailBytes', []))
        if len(chunk) != e - s:
            chunk = (chunk + bytes(e - s))[:e - s]
        body += chunk
    return bytes(body)


# ---------------------------------------------------------------- dispatch

# ---------------------------------------------------------------- 7709 texture atlas

def xt_decode(d):
    # header (8 u32) then faceCount records of 30 bytes; record k's last u32 =
    # the byte count of block k+1 (block 0's byte count = header[7]); the last
    # record is a 6-byte closing record. The blocks are the game's packed
    # wall-texture data (an LZ scheme - see work/spec/FUN_68086ebc); shown as
    # u16 words plus a trailing odd byte.
    face_count = rd_u32(d, 0)
    offs = [rd_u32(d, 32 + 30 * k + 2) for k in range(face_count)]
    blocks = []
    for k in range(face_count):
        o = 32 + 30 * k
        off = offs[k]
        if k + 1 < face_count:
            # full record: width, height, stride; the next record's last u32
            # holds this next block's byte count
            w = rd_u32(d, o + 6)
            h = rd_u32(d, o + 10)
            stride = rd_u32(d, o + 22)
            size = rd_u32(d, 28) if k == 0 else rd_u32(d, 32 + 30 * (k - 1) + 26)
        else:
            # the last record is only 6 bytes (lead + offset); the block's
            # pixel data ends the file
            w, h, stride = 0, 0, 0
            size = len(d) - off
        data = d[off:off + size]
        nw = len(data) // 2
        words = [struct.unpack_from('<h', data, 2 * j)[0] for j in range(nw)]
        blocks.append({
            '_dataOffset': off,
            '_width': w,
            '_height': h,
            '_stride': stride,
            '_recordBytes': size,
            'wordValues': words,
            '_oddTail': list(data[nw * 2:]),
        })
    # header words: [faceCount, faceCount, w, h, 0, 0, strideWord, block0 bytes].
    # Everything is recomputed by the encoder except strideWord (header[6], a
    # texture word whose one-step rule is unread - 704 for Wrigley, the last
    # full block's stride elsewhere), which stays editable content.
    return {'_format': 'texture atlas', '_headWidth': rd_u32(d, 8), '_headHeight': rd_u32(d, 12),
            '_strideWord': rd_u32(d, 24), 'blocks': blocks}


def xt_encode(doc, d):
    face_count = len(doc['blocks'])
    base = 32 + (face_count - 1) * 30 + 6
    offs = []
    sizes = []

    def bl_size(bl):
        return len(bl['wordValues']) * 2 + len(bl.get('_oddTail', []))
    pos = base
    for bl in doc['blocks']:
        offs.append(pos)
        sizes.append(bl_size(bl))
        pos += sizes[-1]
    f0 = doc['blocks'][0]
    stride_word = doc['_strideWord']
    n_full = face_count - 1
    out = struct.pack('<8I', face_count, face_count, doc['_headWidth'], doc['_headHeight'],
                      0, 0, stride_word, sizes[0])
    recs = b''
    for k in range(face_count):
        bl = doc['blocks'][k]
        off = offs[k]
        if k < face_count - 1:
            # f6 = the unpacked stride (w*h), f7 = the byte count of block k+1
            recs += struct.pack('<H7I', 1, off, bl['_width'], bl['_height'],
                                0, 0, bl['_stride'], sizes[k + 1])
        else:
            recs += struct.pack('<HI', 1, off)
    body = out + recs
    for bl in doc['blocks']:
        body += struct.pack('<%dH' % len(bl['wordValues']), *[v & 0xFFFF for v in bl['wordValues']])
        body += bytes(bl.get('_oddTail', []))
    return body


DECODERS = {
    'e957': e957_decode,
    'e1a4': e1a4_decode,
    '5200': pb5200_decode,
    'bb43': ms_decode,
    'ce8c': w_decode,
    'cb7c': wt_decode,
    '6be6': ol_decode,
    'b0e7': un_decode,
    'e6e7': cam_decode,
    '947d': hs_decode,
    '7709': xt_decode,
}


def chunk_id(name):
    return name.split('_')[0].lower()


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    cmd = sys.argv[1]
    name = sys.argv[2]
    cid = chunk_id(name)
    dec = DECODERS.get(cid)
    if dec is None:
        raise SystemExit('unknown chunk id %r' % cid)
    if cmd == 'decode':
        d = open(sys.argv[3], 'rb').read()
        doc = dec(d)
        json.dump(doc, open(sys.argv[4], 'w'), indent=1)
    elif cmd == 'encode':
        d = open(sys.argv[3], 'rb').read()
        doc = json.load(open(sys.argv[4]))
        enc = ENCODERS[cid]
        open(sys.argv[5], 'wb').write(enc(doc, d))
    else:
        raise SystemExit(__doc__)


ENCODERS = {
    'e957': e957_encode,
    'e1a4': e1a4_encode,
    '5200': pb5200_encode,
    'bb43': ms_encode,
    'ce8c': w_encode,
    'cb7c': wt_encode,
    '6be6': ol_encode,
    'b0e7': un_encode,
    'e6e7': cam_encode,
    '947d': hs_encode,
    '7709': xt_encode,
}

if __name__ == '__main__':
    main()
