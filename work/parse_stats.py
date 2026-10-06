import struct,collections,sys
def records(path):
    d=open(path,'rb').read(); out=[]; i=0; n=len(d)
    while i<n-20:
        if d[i]==0xfa and d[i+1]==0xfa:
            tot,pl,rn,off=struct.unpack_from('<IIII',d,i+2)
            if tot==pl+18 and 0<pl<2000 and i+2+16+pl<=n:
                out.append((i,rn,off,d[i+18:i+18+pl])); i+=18+pl; continue
        i+=1
    return out
if __name__=='__main__':
    r=records(sys.argv[1]); print(len(r))
    c=collections.Counter((len(p),struct.unpack_from('<HH',p,0)) for _,_,_,p in r if len(p)>=4)
    for k,v in sorted(c.items(),key=lambda x:-x[1])[:25]: print(k,v)
