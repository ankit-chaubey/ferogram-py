import re, struct, zlib, random, collections

LINE = re.compile(r"^([\w.]+)#([0-9a-fA-F]+)\s*(.*?)\s*=\s*([\w.<>%]+)\s*;\s*$")
PRIM = {"int", "long", "double", "string", "bytes", "Bool", "int128", "int256", "true", "True", "#"}

class Ctor:
    __slots__ = ("name", "cid", "fields", "result", "is_func", "text")

def parse_tl(path):
    out = []
    is_func = False
    for raw in open(path, encoding="utf-8"):
        line = raw.strip()
        if line.startswith("---functions---"): is_func = True; continue
        if line.startswith("---types---"): is_func = False; continue
        if not line or line.startswith("//"): continue
        m = LINE.match(line)
        if not m: continue
        name, cid, body, result = m.groups()
        if name in ("vector", "int", "long", "double", "string", "bytes", "true", "boolFalse", "boolTrue", "null") and False: continue
        c = Ctor(); c.name = name; c.cid = int(cid, 16); c.result = result; c.is_func = is_func; c.text = line
        fields = []
        for tok in body.split():
            if tok.startswith("{") or tok in ("[", "]") or tok.endswith("}"): continue
            if ":" not in tok: continue
            fname, ftype = tok.split(":", 1)
            flag = None
            fm = re.match(r"^(flags\d*)\.(\d+)\?(.+)$", ftype)
            if fm: flag, ftype = (fm.group(1), int(fm.group(2))), fm.group(3)
            fields.append((fname, ftype, flag))
        c.fields = fields
        out.append(c)
    return out

def infer_id(text):
    s = text.split(";")[0]
    s = re.sub(r"#[0-9a-fA-F]+", "", s)
    s = s.replace("{", "").replace("}", "").replace(":bytes", ":string").replace("?bytes", "?string")
    s = s.replace("<", " ").replace(">", "")
    s = re.sub(r" \w+:\w+\.\d+\?true", "", s)
    s = " ".join(s.split())
    return zlib.crc32(s.encode()) & 0xFFFFFFFF

def pack_bytes(b):
    n = len(b)
    if n <= 253:
        r = bytes([n]) + b
    else:
        r = bytes([254, n & 255, (n >> 8) & 255, (n >> 16) & 255]) + b
    return r + b"\0" * ((-len(r)) % 4)

class Schema:
    def __init__(self, ctors):
        self.ctors = ctors
        self.by_name = {c.name: c for c in ctors}
        self.by_cid = {}
        self.by_type = collections.defaultdict(list)
        for c in ctors:
            if not c.is_func:
                self.by_cid[c.cid] = c
                self.by_type[c.result].append(c)
        self.cost = {}
        changed = True
        while changed:
            changed = False
            for t, cs in self.by_type.items():
                best = min((self._ccost(c) for c in cs), default=None)
                if best is not None and best < self.cost.get(t, 1e9):
                    self.cost[t] = best; changed = True
    def _ccost(self, c):
        total = 1
        for fname, ftype, flag in c.fields:
            if flag is not None: continue
            total += self._tcost(ftype)
        return total
    def _tcost(self, t):
        if t in PRIM: return 0
        if t.startswith(("Vector<", "vector<")): return 0
        return self.cost.get(t, 1e6)
    def cheapest(self, t):
        return min(self.by_type[t], key=self._ccost)

def enc_value(S, v, t):
    if t == "int": return struct.pack("<i", v)
    if t == "long": return struct.pack("<q", v)
    if t == "double": return struct.pack("<d", v)
    if t == "string": return pack_bytes(v.encode())
    if t == "bytes": return pack_bytes(v)
    if t == "Bool": return struct.pack("<I", 0x997275b5 if v else 0xbc799737)
    if t == "int128": return v.to_bytes(16, "little")
    if t == "int256": return v.to_bytes(32, "little")
    if t in ("true", "True"): return b""
    if t.startswith(("Vector<", "vector<")):
        inner = t[7:-1]
        return struct.pack("<II", 0x1cb5c415, len(v)) + b"".join(enc_value(S, x, inner) for x in v)
    return enc_obj(S, v)

def enc_obj(S, obj):
    c = S.by_name[obj["_"]]
    return struct.pack("<I", c.cid) + enc_fields(S, c, obj)

def present(obj, fname, ftype):
    v = obj.get(fname)
    if ftype in ("true", "True"):
        return v is True
    return v is not None

def enc_fields(S, c, obj):
    out = []
    flagvals = {}
    for fname, ftype, flag in c.fields:
        if flag is not None and present(obj, fname, ftype):
            flagvals[flag[0]] = flagvals.get(flag[0], 0) | (1 << flag[1])
    for fname, ftype, flag in c.fields:
        if ftype == "#":
            out.append(struct.pack("<I", flagvals.get(fname, 0)))
            continue
        if flag is not None:
            if not present(obj, fname, ftype) or ftype in ("true", "True"): continue
            out.append(enc_value(S, obj[fname], ftype))
        else:
            out.append(enc_value(S, obj[fname], ftype))
    return b"".join(out)

def rd_bytes(d, p):
    f = d[p]
    if f <= 253: n, s = f, p + 1
    else: n, s = d[p+1] | (d[p+2] << 8) | (d[p+3] << 16), p + 4
    e = s + n
    return d[s:e], e + ((-(e - p)) % 4)

def dec_value(S, d, p, t):
    if t == "int": return struct.unpack_from("<i", d, p)[0], p + 4
    if t == "long": return struct.unpack_from("<q", d, p)[0], p + 8
    if t == "double": return struct.unpack_from("<d", d, p)[0], p + 8
    if t == "string":
        b, p = rd_bytes(d, p); return b.decode("utf-8"), p
    if t == "bytes": return rd_bytes(d, p)
    if t == "Bool":
        c = struct.unpack_from("<I", d, p)[0]; return c == 0x997275b5, p + 4
    if t == "int128": return int.from_bytes(d[p:p+16], "little"), p + 16
    if t == "int256": return int.from_bytes(d[p:p+32], "little"), p + 32
    if t.startswith(("Vector<", "vector<")):
        inner = t[7:-1]
        assert struct.unpack_from("<I", d, p)[0] == 0x1cb5c415
        n = struct.unpack_from("<I", d, p + 4)[0]; p += 8; items = []
        for _ in range(n):
            x, p = dec_value(S, d, p, inner); items.append(x)
        return items, p
    return dec_obj(S, d, p)

def dec_obj(S, d, p):
    cid = struct.unpack_from("<I", d, p)[0]; p += 4
    c = S.by_cid[cid]
    obj = {"_": c.name}
    flagvals = {}
    for fname, ftype, flag in c.fields:
        if ftype == "#":
            flagvals[fname] = struct.unpack_from("<I", d, p)[0]; p += 4; continue
        if flag is not None:
            if not (flagvals[flag[0]] >> flag[1]) & 1: continue
            if ftype in ("true", "True"): obj[fname] = True; continue
        v, p = dec_value(S, d, p, ftype)
        obj[fname] = v
    return obj, p

def rnd_str(r):
    n = r.choice([0, 1, 5, 20, 253, 254, 255, 300, 1000])
    return "".join(r.choice("abcxyz é€😀0 \n") for _ in range(n))

def rnd_bytes(r):
    return bytes(r.getrandbits(8) for _ in range(r.choice([0, 1, 3, 4, 5, 252, 253, 254, 255, 256, 1000])))

def gen_value(S, r, t, depth):
    if t == "int": return r.choice([0, 1, -1, 2**31 - 1, -2**31, r.randint(-2**31, 2**31 - 1)])
    if t == "long": return r.choice([0, 1, -1, 2**63 - 1, -2**63, r.randint(-2**63, 2**63 - 1), r.randint(0, 2**31)])
    if t == "double": return r.choice([0.0, 1.5, -2.25, 1e300, r.uniform(-1e9, 1e9)])
    if t == "string": return rnd_str(r)
    if t == "bytes": return rnd_bytes(r)
    if t == "Bool": return r.random() < 0.5
    if t == "int128": return r.getrandbits(128)
    if t == "int256": return r.getrandbits(256)
    if t in ("true", "True"): return True
    if t.startswith(("Vector<", "vector<")):
        inner = t[7:-1]
        return [gen_value(S, r, inner, depth + 1) for _ in range(0 if depth >= 3 else r.choice([0, 1, 2, 3]))]
    cs = S.by_type.get(t)
    if not cs: raise KeyError(t)
    c = S.cheapest(t) if depth >= 2 else r.choice(cs)
    return gen_obj(S, r, c, depth + 1)

def gen_obj(S, r, c, depth):
    obj = {"_": c.name}
    groups = {}
    for fname, ftype, flag in c.fields:
        if ftype == "#": continue
        if flag is not None:
            if flag not in groups:
                groups[flag] = depth < 3 and r.random() < 0.5
            if not groups[flag]: continue
        obj[fname] = gen_value(S, r, ftype, depth)
    return obj

def shared_bits(c):
    seen = collections.Counter(f[2] for f in c.fields if f[2] is not None)
    return [k for k, n in seen.items() if n > 1]


def base_type(t):
    while t.startswith(("Vector<", "vector<")):
        t = t[7:-1]
    return t


def reach_paths(S, roots):
    parent = {root: None for root in roots}
    queue = collections.deque(roots)
    while queue:
        t = queue.popleft()
        for c in S.by_type.get(t, []):
            for fname, ftype, flag in c.fields:
                bt = base_type(ftype)
                if bt in S.by_type and bt not in parent:
                    parent[bt] = (t, c, fname)
                    queue.append(bt)
    return parent


def path_to(parent, t):
    steps = []
    while parent[t] is not None:
        pt, c, fname = parent[t]
        steps.append((c, fname))
        t = pt
    return t, list(reversed(steps))


def gen_forced(S, r, steps, target):
    if not steps:
        return gen_obj(S, r, target, 1)
    c, fname = steps[0]
    obj = {"_": c.name}
    present = {}
    for f, ftype, flag in c.fields:
        if f == fname and flag is not None:
            present[flag] = True
    for f, ftype, flag in c.fields:
        if ftype == "#":
            continue
        if flag is not None:
            if flag not in present:
                present[flag] = r.random() < 0.4
            if not present[flag]:
                continue
        if f == fname:
            sub = gen_forced(S, r, steps[1:], target)
            obj[f] = [sub] if ftype.startswith(("Vector<", "vector<")) else sub
        else:
            obj[f] = gen_value(S, r, ftype, 2)
    return obj
