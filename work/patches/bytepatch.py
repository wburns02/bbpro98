import os,sys; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__))); import liveguard
import sys,shutil,os
# usage: bytepatch.py DLL fileoff oldhex newhex   (asserts old bytes; use 'revert' via backup copy)
dll,off,old,new=sys.argv[1],int(sys.argv[2],16),bytes.fromhex(sys.argv[3]),bytes.fromhex(sys.argv[4])
b=bytearray(open(dll,'rb').read())
assert bytes(b[off:off+len(old)])==old,("mismatch",bytes(b[off:off+len(old)]).hex())
assert len(old)==len(new); b[off:off+len(old)]=new
open(dll,'wb').write(b); print("patched",hex(off))
