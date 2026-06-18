import struct
import sys

path = r'C:\Program Files\LANDESK\Shavlik Protect Agent\STServiceProcess.dll'
with open(path, 'rb') as f:
    d = f.read()

pe = struct.unpack_from('<I', d, 0x3c)[0]
sys.stdout.write(f'PE={hex(pe)}\n')

opt = pe + 4 + 20
magic = struct.unpack_from('<H', d, opt)[0]
sys.stdout.write(f'Magic={hex(magic)}\n')

ns = struct.unpack_from('<H', d, pe + 4 + 2)[0]
soh = struct.unpack_from('<H', d, pe + 4 + 16)[0]
sh = pe + 4 + 20 + soh
sys.stdout.write(f'NumSections={ns}\n')
sys.stdout.write(f'OptHdrSize={soh}\n')
sys.stdout.write(f'SectHdrAt={hex(sh)}\n')

dd_start = opt + (96 if magic == 0x10b else 112)
export_rva = struct.unpack_from('<I', d, dd_start)[0]
sys.stdout.write(f'ExportRVA={hex(export_rva)}\n')

for i in range(ns):
    x = sh + i * 40
    name = d[x:x+8].rstrip(b'\x00').decode()
    vr = struct.unpack_from('<I', d, x + 12)[0]
    vs = struct.unpack_from('<I', d, x + 8)[0]
    pr = struct.unpack_from('<I', d, x + 20)[0]
    rc = struct.unpack_from('<I', d, x + 36)[0]
    sys.stdout.write(f'  Sec[{i}] {name}: VA={hex(vr)} VS={hex(vs)} Raw={hex(pr)} Chars={hex(rc)}\n')
    if vr <= export_rva < vr + vs:
        eo = pr + (export_rva - vr)
        nn = struct.unpack_from('<I', d, eo + 0x14)[0]
        an = struct.unpack_from('<I', d, eo + 0x20)[0]
        sys.stdout.write(f'  *** Export found in {name} at file offset {hex(eo)}\n')
        sys.stdout.write(f'  Names count={nn}, NamesRVA={hex(an)}\n')
        for j in range(min(nn, 5)):
            nr = struct.unpack_from('<I', d, pr + (an - vr) + j * 4)[0]
            no = pr + (nr - vr)
            end = d.index(b'\x00', no)
            sys.stdout.write(f'  Export {j}: {d[no:end].decode()}\n')

sys.stdout.flush()
