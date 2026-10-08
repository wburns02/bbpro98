# Target config for re/targets/drive.sh (Claude-owned, sourced by the driver; never mounted writable).
DECODER=req.py
REFEREE=(python3 -I -B "$RE/targets/reqref.py" "$T")
AUDIT=text
HOLDOUT=1            # synthetic files built from the real requesters of both files (mixed, shuffled, perturbed)
EXTRA_RO=(/mnt/nvme/bbpro98/targets_data/req /mnt/nvme/bbpro98/index)
LEAK_RE='targets_data|/mnt/nvme|/home/will|\.\./'
declare -A FOCUS=(
  [code]="Your primary route is the CODE: BBShell FUN_680442b0 reads a requester (seeks the 'REQ:' tag with FUN_68063450, reads 16 bytes of the header, then calls the vtable slots +0x28 / +0x2c / +0x30 of the requester object); follow those, find where the GAD: section is read and the gadget factory that switches on the type byte and the class byte, and name every header and gadget field from the members it fills and where they are used (draw, hit test, focus order, list columns, ...). EZShell, LineUp and Upstats read the same format. Use the files only to confirm."
  [data]="Your primary route is the DATA: dump every gadget grouped by (type, class) across both files and work out each field from its values (screen coordinates on 640x480, colors, fonts, links to other gadget ids = tab/focus order or column chains, string table ids); do the same for the requester header fields (title, size, child lists). Confirm in BBShell (FUN_680442b0 reads a requester) when stuck."
)
AUDIT_RULES='This is a summary of what a decoder reports for the UI layout files of a 1997 baseball game (requesters = screens and dialogs on a 640x480 display, each a list of gadgets = buttons, labels, list boxes, edit fields, check boxes, scroll bars, ...), followed by the decoder source. Real decoding: gadget kinds are named (button, label, list column, ...), every field has a name that says what it is (position, size, font, color, style flags, linked gadget id, string id, ...), lengths/counts/offsets are derived ("_" keys) recomputed by the encoder, and the code parses the tag/record layout generically. FAIL-worthy: placeholder names for most fields, header or gadget bytes kept as opaque blobs or numbered word lists, hard-coded content or offsets, or an encoder that patches the original bytes instead of rebuilding. Judge the summary and the code.'
