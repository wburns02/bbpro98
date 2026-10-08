import t3lib


def replay(o, r):
    obj = r['obj']
    fielders = [t3lib.u32(obj, 0xb + 4 * k) for k in range(9)]

    o.x(0x68039645)                      # iterator init (FUN_68039645)
    local_8 = 0                          # short: steps taken
    local_e9c = 0                        # chosen fielder pointer (0 = none)

    while True:
        while True:
            v, z = o.x2(0x6803997d)      # flight-path step (FUN_6803997d), z = s16 after the step
            z = t3lib.s16v(z)
            if not (v & 0xff) or (o.x(0x68002e30) & 0xff) != 0:
                return o.x(0x6802644a) & 0xffffffff   # fallback: nearest fielder (FUN_6802644a)
            local_8 = t3lib.s16v(local_8 + 1)
            blocked = o.x(0x68023be0) & 0xff          # point not reachable (FUN_68023be0)
            if not (blocked or z > 0xe0):
                break

        local_ea4 = 0                    # short: best score
        for k in range(9):
            ptr = fielders[k]
            d = o.x(0x68003988)          # fielder's time to the point (FUN_68003988)
            s = o.x(0x68021fca)          # fielder's reaction delay (FUN_68021fca)
            sVar2 = t3lib.s16v(t3lib.s16v(d) + t3lib.s16v(s))
            if sVar2 < local_8 and (local_e9c == 0 or sVar2 < local_ea4):
                local_ea4 = sVar2
                local_e9c = ptr

        if local_e9c != 0:
            return local_e9c & 0xffffffff
