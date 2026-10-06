# Tool notes (static analysis)
- NAMESF.NEW: 3848 lines plain ASCII CRLF, one first name per line; NAMESL.NEW: 57474 lines, one surname per line, <=12 chars. BBNAMES.EXE (16-bit DOS, Borland C++, Rudy Kamman) reads them + SHELL.VOL in BBPRO dir, rewrites rookie name pools in SHELL.VOL. Max 65500 names each. Undo: restore SHELL.VOL from CD.
- BBNAM.EXE = zip containing byte-identical BBNAMES.EXE.
- BBDRAFT.EXE: 16-bit DOS MZ (Borland C++ 1991); usage: bbdraft <leaguefile-without-ext> from BBPRO dir; reads assn\<name>.asn.
- BBEdit98: VB6 PE32; needs MSVBVM60, COMCTL32.OCX, COMDLG32.OCX, DAO 3.5/Jet 3.5; CAB lists 28 files.
