RENAMES=[("BBShell.dll",a,n) for a,n in [
 (0x6800ec00,"StatsGrid_CellCallback"),
 (0x6805c930,"StatsGrid_FillRowCells"),
 (0x6805cb20,"StatsGrid_InitHeaders"),
 (0x6800d300,"StatsScreen_InitGadgets"),
 (0x680428a0,"HallOfFame_DataLayout"),
 (0x6803a3a0,"FrontOffice_RegisterAndCreateWindow"),
 (0x6805c780,"StatSets_LoadAll"),
 (0x6805d7d0,"StatSet_LoadFile"),
 (0x6805d8e0,"StatSet_SaveFile"),
 (0x6805da80,"ChangeColumns_Init"),
 (0x6805db20,"ChangeColumns_Show"),
]]
LABELS=[("BBShell.dll",0x6808c2e8,"g_StatSets","StatSet","array of stat sets, stride 0x80 (set index = this+0xe4); per view +0x28*view in the first 0x50 bytes. ids[view*10]=count, ids 1..9 = stat ids"),
 ("BBShell.dll",0x6808dd10,"g_GadgetMgr",None,"gadget manager object; this for FUN_680436c0/68043400/68043640 (thiscall, 2 stack args, ret 8)")]
STRUCT_BINARIES=["BBShell.dll"]
def STRUCTS(b,p):
    if b!="BBShell.dll": return
    dtm=p.getDataTypeManager(); cat=CategoryPath('/BBPro98')
    def add(s): dtm.addDataType(s,DataTypeConflictHandler.REPLACE_HANDLER)
    u8,u16,u32=ByteDataType.dataType,UnsignedShortDataType.dataType,UnsignedIntegerDataType.dataType
    def chars(n): return ArrayDataType(CharDataType.dataType,n,1)
    # StatSet: 0x80 stride; ids at +0 (2 blocks of [count=3, 9 stat ids]), name +0x50, name2 +0x5d (matches STS file: u32 ver, name2[33], 0x50 bytes ids)
    s=StructureDataType(cat,'StatSet',0x80)
    s.replaceAtOffset(0,ArrayDataType(u32,20,4),0x50,'ids','2 views x [count, 9 stat ids]; stat id = SPRPLYR third-table index + 13')
    s.replaceAtOffset(0x50,chars(13),13,'name','13-char file/set name')
    s.replaceAtOffset(0x5d,chars(33),33,'name2','33-byte display name (STS name field)')
    add(s)
    # Stats DAT record stream (mlbpa97.DAT), NOTES_stats_format.md
    h=StructureDataType(cat,'StatsDatRecHeader',18)
    for off,dt,n in [(0,u16,'magic_fafa'),(2,u32,'total_len'),(6,u32,'payload_len'),(10,u32,'recno'),(14,u32,'logical_off')]: h.replaceAtOffset(off,dt,dt.getLength(),n,None)
    add(h)
    bat=['AB','H1B','H2B','H3B','HR','RBI','BB','SO','IBB_or_HBP','HBP_or_IBB','SH','SF','G','R','SB','CS','GIDP']
    b=StructureDataType(cat,'StatsDatBatting40',40)
    for i,n in enumerate(['scope','kind','player_id']): b.replaceAtOffset(2*i,u16,2,n,None)
    for i,n in enumerate(bat): b.replaceAtOffset(6+2*i,u16,2,'c%d_%s'%(i,n),'H = H1B+H2B+H3B+HR (not stored)' if i==1 else None)
    add(b)
    pit={17:'unk',18:'OUTS',19:'BF',20:'W',21:'L',22:'SV',23:'SHO_q',25:'GS_or_CG',26:'ER'}
    q=StructureDataType(cat,'StatsDatPitching70',70)
    for i,n in enumerate(['scope','kind','player_id']): q.replaceAtOffset(2*i,u16,2,n,None)
    for i in range(32):
        n=bat[i] if i<17 else pit.get(i,'unk')
        if i==12 or i==16: n='G_app'
        q.replaceAtOffset(6+2*i,u16,2,'c%d_%s'%(i,n),'opponent line vs pitcher for c0..c16' if i==0 else None)
    add(q)
    # PYR player record, 192 bytes (notes_formats.md; every byte passes through the per-file substitution table)
    y=StructureDataType(cat,'PyrRecord',192)
    y.replaceAtOffset(0,u16,2,'id','100+index')
    y.replaceAtOffset(26,u32,4,'birth_daynum',None)
    y.replaceAtOffset(30,chars(17),17,'first_name',None)
    y.replaceAtOffset(47,chars(17),17,'last_name',None)
    for off,n in [(64,'years'),(65,'bats'),(66,'throws'),(68,'pos')]: y.replaceAtOffset(off,u8,1,n,None)
    y.replaceAtOffset(70,ArrayDataType(u8,23,1),23,'ratings',None)
    y.replaceAtOffset(93,ArrayDataType(u8,23,1),23,'potentials',None)
    y.replaceAtOffset(116,ArrayDataType(u8,25,1),25,'splits',None)
    add(y)
