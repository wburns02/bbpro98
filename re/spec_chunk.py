import re,sys
sys.argv=['x']; src=open('/mnt/nvme/bbpro98/re/spec_draft.py').read().split("order=sorted")[0]
exec(src)
A='68044cbd'
body=annotate(funcs[A]).split('\n'); n=len(body); k=4; parts=[]
for i in range(k):
    parts.append('\n'.join(body[i*n//k:(i+1)*n//k]))
pl='\n'.join(f'{pb[i][0]} default={pb[i][1]}' for i in sorted(byfn[A]))
outs=[]
def one(i):
    user=f"Function {A} (FastSim relief pitcher / pinch hit decision logic), PART {i+1} of {k} of its decompile (consecutive lines; variables carry over between parts). Parameters it reads overall:\n{pl}\n\nPART:\n{parts[i]}"
    sysm=SYS.replace("Write a spec:","Write a spec for THIS PART only:")
    for _ in range(3):
        try:
            out,u=cc.call_hive(key,'z-ai/glm-5.3-flash',sysm,user,temperature=0.1,max_tokens=24000,timeout_s=900)
            if len(out)>200: return out
        except Exception as e: time.sleep(5)
    return 'FAILED PART'
with cf.ThreadPoolExecutor(4) as ex: outs=list(ex.map(one,range(k)))
open(O+f'FUN_{A}.md','w').write(f'# FUN_{A} params={len(byfn[A])} relief/pinch-hit decision (chunked)\n\nDRAFT (GLM-Flash, unaudited, 4 parts)\n\n'+'\n\n=====\n\n'.join(outs)+'\n')
print('ok',[len(o) for o in outs])
