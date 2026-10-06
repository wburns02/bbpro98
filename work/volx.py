import re,struct,sys,os
# usage: volx.py FILE.VOL OUTDIR  -- crude VOLM unpacker (offsets parsed from directory)
f,out=sys.argv[1],sys.argv[2]; d=open(f,'rb').read(); os.makedirs(out,exist_ok=True)
i=d.index(b'\\\0')+2; cnt=struct.unpack_from('<H',d,i)[0]; i+=2
ents=[]; off=struct.unpack_from('<I',d,i)[0]; i+=4
for k in range(cnt):
    j=d.index(b'\0',i); name=d[i:j].decode(); i=j+1
    if k<cnt-1:
        # gap until next offset: take bytes up to next name start; find next printable name start
        m=re.compile(rb'[\x20-\x7e]{3,}\x00').search(d,i+4)  # next name at least after 4 bytes
        gap=d[i:m.start()]; nxt=struct.unpack_from('<I',gap[-4:])[0]
        ents.append((name,off,gap)); off_next=nxt
        i=m.start()
        ents[-1]=(name,off,gap); off=off_next
    else:
        ents.append((name,off,d[i:i+8]))
print(cnt,len(ents))
for k,(n,o,g) in enumerate(ents):
    e=ents[k+1][1] if k+1<len(ents) else len(d)
    print('%-16s off=%8d size=%8d tag=%s'%(n,o,e-o,g[:-4].hex() if k+1<len(ents) else g.hex()))
    open(os.path.join(out,n),'wb').write(d[o:e])
