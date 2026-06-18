import struct
import sys

path = r'C:\Program Files\LANDESK\Shavlik Protect Agent\STServiceProcess.dll'
with open(path, 'rb') as f:
    d = f.read()

pe = struct.unpack_from('<I', d, 0x3c)[0]
opt = pe + 4 + 20
magic = struct.unpack_from('<H', d, opt)[0]
dd_start = opt + (96 if magic == 0x10b else 112)
export_rva = struct.unpack_from('<I', d, dd_start)[0]

ns = struct.unpack_from('<H', d, pe + 4 + 2)[0]
soh = struct.unpack_from('<H', d, pe + 4 + 16)[0]
sh = pe + 4 + 20 + soh

for i in range(ns):
    x = sh + i * 40
    vr = struct.unpack_from('<I', d, x + 12)[0]
    vs = struct.unpack_from('<I', d, x + 8)[0]
    pr = struct.unpack_from('<I', d, x + 20)[0]
    if vr <= export_rva < vr + vs:
        eo = pr + (export_rva - vr)
        nn = struct.unpack_from('<I', d, eo + 0x14)[0]
        an = struct.unpack_from('<I', d, eo + 0x20)[0]
        names = []
        for j in range(nn):
            nr = struct.unpack_from('<I', d, pr + (an - vr) + j * 4)[0]
            no = pr + (nr - vr)
            end = d.index(b'\x00', no)
            names.append(d[no:end].decode())
        sys.stdout.write('\n'.join(names))
        sys.stdout.flush()
        break
