#!/usr/bin/env python3
"""
Round-trip test for FPS Baseball Pro '98 data formats.
Tests read -> write -> compare for formats with both reader and writer.
"""
import sys, os, tempfile
sys.path.insert(0, '/home/will/bbpro98/BBPRO98_package/research')
sys.path.insert(0, '/home/will/bbpro98/BBPRO98_package/mods')

import pyr_io as PYR

def test_pyr_roundtrip(pyr_path):
    """Test PYR format: read, write, compare bytes."""
    print(f'\nTesting PYR: {pyr_path}')
    print(f'  File size: {os.path.getsize(pyr_path)} bytes')

    # Read original
    with open(pyr_path, 'rb') as f:
        original = f.read()

    # Read, write, read back
    hdr, plain_recs, fwd = PYR.read(pyr_path)
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pyr') as tmp:
        tmp_path = tmp.name
    try:
        PYR.write(tmp_path, hdr, plain_recs, fwd)
        with open(tmp_path, 'rb') as f:
            roundtrip = f.read()
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    # Compare
    if original == roundtrip:
        print(f'  PASS: byte-identical round-trip (records={len(plain_recs)})')
        return True
    else:
        print(f'  FAIL: byte mismatch')
        print(f'    Original:  {len(original)} bytes')
        print(f'    Roundtrip: {len(roundtrip)} bytes')
        # Find first diff
        for i, (a, b) in enumerate(zip(original, roundtrip)):
            if a != b:
                print(f'    First diff at byte {i}: {a:02x} vs {b:02x}')
                break
        return False

def main():
    tests = [
        ('/home/will/seasons/s5/Assn/MLBPA97.PYR', 's5'),
        ('/home/will/seasons/s10/Assn/MLBPA97.PYR', 's10'),
        ('/home/will/seasons/s5/Assn/_DEFAULT.PYR', 's5-default'),
        ('/home/will/seasons/s10/Assn/_DEFAULT.PYR', 's10-default'),
    ]

    results = []
    for path, label in tests:
        if os.path.exists(path):
            passed = test_pyr_roundtrip(path)
            results.append((label, passed, path))
        else:
            print(f'\nSkipping {label}: file not found')

    print('\n' + '='*60)
    print('ROUNDTRIP TEST SUMMARY (PYR)')
    print('='*60)
    for label, passed, path in results:
        status = 'PASS' if passed else 'FAIL'
        print(f'{status:4s} | {label:15s} | {path}')

    passed_count = sum(1 for _, p, _ in results if p)
    total_count = len(results)
    print(f'\nPassed: {passed_count}/{total_count}')
    return 0 if passed_count == total_count else 1

if __name__ == '__main__':
    sys.exit(main())
