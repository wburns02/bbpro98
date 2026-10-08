import t3lib


def _s32(v):
    v &= 0xffffffff
    return v - 0x100000000 if v >= 0x80000000 else v


def replay(o, r):
    xf = t3lib.i32(r['xf'], 0)

    # FUN_6800f200, FUN_68056985(3), FUN_68056985(4): low bytes; sVar14 = (short)(bVar3 - bVar4)
    bVar2 = o.x(0x6800f200) & 0xff
    bVar3 = o.x(0x68056985, arg1=3) & 0xff
    bVar4 = o.x(0x68056985, arg1=4) & 0xff
    sVar14 = t3lib.s16v(bVar3 - bVar4)
    bVar3 = o.x(0x68002c80) & 0xff
    bVar4 = o.x(0x6800f1e0) & 0xff
    bVar5 = o.x(0x6800f1c0) & 0xff
    cVar6 = o.x(0x68039356) & 0xff
    iVar8 = _s32(o.x(0x68032ff0))
    iVar9 = _s32(o.x(0x6800f600))
    bVar15 = 1 if o.x(0x6800f640) != 0 else 0
    iVar10 = _s32(o.x(0x6802fd50))

    # alignment object state: mode, a[g], b[g], c[g] for g in (0, 1)
    st = {'mode': 0, 'a': [0, 0], 'b': [0, 0], 'c': [0, 0]}

    def align(a, b, c):
        o.align(a, b, c)
        g = st['mode']
        st['a'][g] = a
        st['b'][g] = b
        st['c'][g] = c

    def setmode(m):
        o.x(0x68019fba, arg1=m)
        st['mode'] = m

    def shift716():
        o.x(0x6801a716)
        g = st['mode']
        if st['c'][g] > 0:
            st['c'][g] -= 1

    def shift7e8():
        o.x(0x6801a7e8)
        g = st['mode']
        if st['c'][g] < 4:
            st['c'][g] += 1

    def shift50e():
        o.x(0x6801a50e)
        g = st['mode']
        if st['b'][g] < 3:
            st['b'][g] += 1

    def shift612():
        o.x(0x6801a612)
        g = st['mode']
        if st['b'][g] > 0:
            st['b'][g] -= 1

    def pbcmp_e90(pbi):
        # IsTracking (FUN_68038e90) compared with PB[pbi]: returns (getter, pb)
        return _s32(o.x(0x68038e90)), _s32(o.pb(pbi))

    setmode(0)
    if cVar6 == 0 or not bVar15 or sVar14 < -1 or 1 < bVar3:
        if cVar6 == 0 or (o.x(0x68038ed0) & 0xff) != 0:
            if iVar8 == 0 or 1 < bVar3:
                align(0, 2, 2)
            else:
                align(3, 2, 2)
        else:
            align(1, 2, 2)
    else:
        align(2, 2, 2)

    v11, v12 = pbcmp_e90(0x30)
    if v11 < v12:
        v11, v12 = pbcmp_e90(0x31)
        if v11 <= v12:
            if iVar10 == 1:
                shift716()
            else:
                shift7e8()
    elif iVar10 == 1:
        shift7e8()
    else:
        shift716()

    bVar1 = False
    setmode(1)
    if xf == 0 and 8 < bVar2 and bVar15 and sVar14 == 0 and bVar3 < 2:
        align(0, 0, 2)
    elif cVar6 == 0 or iVar9 == 0 or (-1 - bVar15) != sVar14:
        if cVar6 == 0 or iVar8 == 0 or ((-1 - bVar15) - (1 if iVar9 != 0 else 0)) != sVar14:
            align(0, 2, 2)
            v8 = _s32(o.x(0x68038e70))
            v9 = _s32(o.pb(0x35))
            if v9 < v8:
                v8 = _s32(o.x(0x68038e70))
                v9 = _s32(o.pb(0x34))
                if v9 <= v8:
                    shift50e()
            else:
                shift612()
            bVar1 = True
        else:
            align(0, 3, 2)
            v8 = _s32(o.x(0x68038e70))
            v9 = _s32(o.pb(0x35))
            if v8 <= v9:
                shift612()
            bVar1 = True
    else:
        align(0, 1, 2)

    v11, v12 = pbcmp_e90(0x30)
    if v11 < v12:
        v11, v12 = pbcmp_e90(0x31)
        if v11 <= v12:
            if iVar10 == 1:
                shift716()
            else:
                shift7e8()
    elif iVar10 == 1:
        shift7e8()
    else:
        shift716()

    if bVar1:
        v11, v12 = pbcmp_e90(0x32)
        if v11 < v12:
            v11, v12 = pbcmp_e90(0x33)
            if v11 <= v12:
                if iVar10 == 1:
                    shift716()
                else:
                    shift7e8()
        elif iVar10 == 1:
            shift7e8()
        else:
            shift716()
        if bVar4 + 1 < bVar5:
            shift50e()
        elif bVar5 + 1 < bVar4:
            shift612()

    o.x(0x68038dd0)

    return [st['mode'], st['a'][0], st['a'][1], st['b'][0], st['b'][1], st['c'][0], st['c'][1]]
