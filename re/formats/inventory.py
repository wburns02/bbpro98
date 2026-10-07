#!/usr/bin/env python3
"""
FPS Baseball Pro '98 data file inventory.
Scans all non-image, non-audio, non-executable files.
Output: TSV with path, size, first 16 bytes hex, magic ASCII, Shannon entropy (first 64KB),
         divisibility by [512,256,128,100,64], and guess class.
"""
import os, struct, sys, math
from pathlib import Path

BBPRO_ROOT = Path("/home/will/.bbpro98_prefix/drive_c/Sierra/BBPRO_98")

# Skip patterns
SKIP_EXTS = {'.bmp', '.wav', '.mp3', '.ttf', '.dll', '.exe', '.hlp', '.ico', '.exp', '.lib'}
SKIP_DIRS = {'Music', 'Videos', 'Preview', 'Assn', 'Archive', 'StatSets', 'Stats', 'Sshell', 'Stadia', 'tapes'}
SKIP_FILES = {'bbfix.log', 'bbtrace.log'}

def shannon_entropy(data, chunk_size=65536):
    """Compute Shannon entropy of first chunk_size bytes."""
    chunk = data[:chunk_size]
    if not chunk:
        return 0.0
    freq = [0] * 256
    for byte in chunk:
        freq[byte] += 1
    entropy = 0.0
    for f in freq:
        if f > 0:
            p = f / len(chunk)
            entropy -= p * math.log2(p)
    return entropy

def magic_ascii(data):
    """Try to extract printable ASCII magic from first 16 bytes."""
    result = ""
    for b in data[:16]:
        if 32 <= b <= 126:
            result += chr(b)
        elif b in (0, 10, 13):
            result += ' '
        else:
            result += '.'
    return result.strip()

def divisibility(size):
    """Check divisibility by common record sizes."""
    divisors = [512, 256, 128, 100, 64]
    result = []
    for d in divisors:
        if size % d == 0:
            result.append(str(d))
    return ','.join(result) if result else '-'

def guess_class(data, size, path):
    """Guess file class based on structure."""
    if size < 100:
        return "small"

    # Check for common patterns
    if data[:2] == b'\xfa\xfa':
        return "record-stream"
    if data[:4] == b'VOLM':
        return "paged-archive"
    if data[:2] == b'PK':
        return "zip-archive"
    if data[:4] == b'\x00\x00\x00\x00':
        return "paged-container"

    # Check if mostly zeros (sparse/paged)
    if len(data) >= 512:
        chunk = data[:512]
        zero_ratio = chunk.count(b'\x00') / len(chunk)
        if zero_ratio > 0.5:
            return "paged-container"

    # Check entropy: text is low, compressed/encrypted is high
    ent = shannon_entropy(data)
    if ent < 2.5:
        return "text"
    elif ent > 7.0:
        return "compressed/encrypted"
    else:
        return "fixed-record"

def should_skip(rel_path, is_dir):
    """Return True if file should be skipped."""
    parts = rel_path.parts

    # Skip if any directory component is in SKIP_DIRS
    for part in parts:
        if part in SKIP_DIRS:
            return True

    if not is_dir:
        # Skip by extension
        if Path(rel_path).suffix.lower() in SKIP_EXTS:
            return True
        # Skip by filename
        if rel_path.name in SKIP_FILES:
            return True

    return False

def main():
    rows = []

    for root, dirs, files in os.walk(BBPRO_ROOT):
        # Filter dirs in-place to skip SKIP_DIRS
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for fname in files:
            fpath = Path(root) / fname
            rel_path = fpath.relative_to(BBPRO_ROOT)

            if should_skip(rel_path, False):
                continue

            try:
                size = fpath.stat().st_size
                with open(fpath, 'rb') as f:
                    data = f.read()

                hex_head = ' '.join(f'{b:02x}' for b in data[:16])
                magic = magic_ascii(data)
                entropy = shannon_entropy(data)
                divisors = divisibility(size)
                guess = guess_class(data, size, str(rel_path))

                row = [
                    str(rel_path),
                    str(size),
                    hex_head,
                    magic,
                    f'{entropy:.2f}',
                    divisors,
                    guess
                ]
                rows.append(row)
            except Exception as e:
                print(f"Error processing {rel_path}: {e}", file=sys.stderr)

    # Print TSV header
    print('\t'.join(['path', 'size', 'first_16_hex', 'magic_ascii', 'entropy_64kb', 'divisible_by', 'guess_class']))

    # Print rows sorted by path
    for row in sorted(rows, key=lambda x: x[0]):
        print('\t'.join(row))

if __name__ == '__main__':
    main()
