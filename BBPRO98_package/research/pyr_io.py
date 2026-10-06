"""Round-trip writer for FPS Baseball Pro '98 .PYR files (uses each file's own substitution table)."""
import sys,struct
sys.path.insert(0,'../mods'); import dump_pyr as D
def read(path):
    d,recs,inv=D.load(path); fwd={v:k for k,v in inv.items()}
    assert len(inv)==256 and len(fwd)==256, 'substitution table incomplete'
    return bytearray(d),[bytearray(D.decode(r,inv)) for r in recs],fwd
def write(path,hdr,plain_recs,fwd):
    out=bytearray(hdr[:D.HDR])
    for p in plain_recs: out+=bytes(fwd[b] for b in p)
    open(path,'wb').write(out)
if __name__=='__main__':
    d,recs,fwd=read(sys.argv[1]); write('/tmp/rt.pyr',d,recs,fwd)
    print('byte-identical round trip:',open('/tmp/rt.pyr','rb').read()==bytes(d))
