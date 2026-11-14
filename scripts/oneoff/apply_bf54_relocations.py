#!/usr/bin/env python3
"""BF-54 v2.6.3：基本区 5 字行级重定位（mapping v271 -> v273）。

只改 5 个基本区字（愈/急/架/紉/釘）+ 旧釘框改标 釕；扩展区 6 字不处理。
- 输出 work/lead/mapping_block_v273.jsonl（其他行原样逐字节保留）
- 校验：char 唯一/数量、box 在 quad 内、同页半版 box 不重叠、非目标行不变
- 汇总 work/lead/mapping_v273_summary.json
"""
import os, sys, json, copy
for _k in ("OMP_NUM_THREADS","MKL_NUM_THREADS","OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(_k,"1")
ROOT=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0,os.path.join(ROOT,"scripts"))
sys.path.insert(0,os.path.join(ROOT,"work","font","_pylibs"))
import font_build as FB

SRC=os.path.join(ROOT,"work/lead/mapping_block_v271.jsonl")
OUT=os.path.join(ROOT,"work/lead/mapping_block_v273.jsonl")
GEOM=os.path.join(ROOT,"work/lead/page_geometry.jsonl")
CANON=os.path.join(ROOT,"work/seq/canonical.jsonl")
SUM=os.path.join(ROOT,"work/lead/mapping_v273_summary.json")

# canonical index
ci={}
for line in open(CANON,encoding="utf-8"):
    r=json.loads(line); ch=r.get("char")
    if ch and ch not in ci: ci[ch]=int(r.get("ci") or 10**9)
def cidx(ch): return ci.get(ch,10**9)

def box_in_quad(page,half,box):
    q=FB.get_page_content_quads(page).get(half)
    if not q: return True
    qb=q["box"]
    return (box[0]>=qb[0]-0.51 and box[1]>=qb[1]-0.51 and box[2]<=qb[2]+0.51 and box[3]<=qb[3]+0.51)
def make_box(page,half,inkbox):
    lat=FB.get_page_lattice(page).get(half)
    b=FB.block_for_box(lat,[float(v) for v in inkbox])
    assert b is not None, (page,half,inkbox)
    nb=list(b)
    q=FB.get_page_content_quads(page).get(half)
    if q:
        qb=q["box"]
        nb=[max(nb[0],qb[0]+2),max(nb[1],qb[1]+2),min(nb[2],qb[2]-2),min(nb[3],qb[3]-2)]
    nb=[float(round(v)) for v in nb]
    assert nb[2]-nb[0]>=60 and nb[3]-nb[1]>=60,(page,half,nb)
    assert box_in_quad(page,half,nb),(page,half,nb)
    return nb
def iou(a,b):
    ix=max(0,min(a[2],b[2])-max(a[0],b[0])); iy=max(0,min(a[3],b[3])-max(a[1],b[1]))
    inter=ix*iy; u=(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-inter
    return inter/u if u>0 else 0

# desired relocations: char -> (old page,half, old box; new page,half, inkbox for 2x2 block)
REL={
 "愈":dict(old=("04_0014","R",[1781.0,1131.0,1883.0,1228.0]), new=("04_0048","R",[1490,819,1572,888]), note="04_0048R 大字块（round4 C2，owner ✅）"),
 "急":dict(old=("06_0080","R",[1037.0,718.0,1139.0,816.0]), new=("04_0020","L",[630,470,715,555]), note="canonical 邻字定位 04_0020L（owner ✅）"),
 "架":dict(old=("06_0080","R",None), new=("05_0075","L",[730,360,810,430]), note="canonical 邻字定位 05_0075L（owner ✅）"),
 "紉":dict(old=("08_0101","L",[320.0,1360.0,420.0,1460.0]), new=("08_0101","L",[516,1317,601,1405]), note="同行换框（round2 C9，owner ✅）"),
 "釘":dict(old=("11_0007","L",[705.0,608.0,803.0,706.0]), new=("11_0007","L",[238,387,323,473]), note="同行换框（round2 C8，owner ✅）"),
}
REL["架"]["old"]=("03_0184","L",[228.0,419.0,331.0,516.0])
REL["釕"]=dict(old=None,new=("11_0007","L",[705,608,803,706]),note="旧釘框实际字=釕 U+91D5（owner：多一个字）",box_from_old_ding=True)

raw=[l.rstrip("\n") for l in open(SRC,encoding="utf-8")]
rows=[json.loads(l) for l in raw]
bykey={(r["page"],r["half"]):r for r in rows}
assert len(bykey)==len(rows)

# pre-check char uniqueness and 釕 absent
def all_chars(rows_):
    out=[]
    for r in rows_:
        for a in r.get("assigned") or []: out.append(a.get("char"))
    return out
pre_chars=all_chars(rows); assert len(pre_chars)==len(set(pre_chars)), "duplicate chars in v271"
assert "釕" not in set(pre_chars), "釕 already mapped"
assert len(pre_chars)==17005, len(pre_chars)

changes=[]
# 1) remove old assignments
for ch,spec in REL.items():
    if ch=="釕": continue
    op,oh,ob=spec["old"]; row=bykey[(op,oh)]
    matches=[a for a in row["assigned"] if a.get("char")==ch]
    assert len(matches)==1,(ch,op,oh,len(matches))
    oldbox=[float(v) for v in ((matches[0].get("cand") or {}).get("box") or [])]
    assert oldbox==[float(v) for v in ob],(ch,oldbox,ob)
    row["assigned"]=[a for a in row["assigned"] if a.get("char")!=ch]
    changes.append(dict(char=ch,action="remove_old",page=op,half=oh,old_box=oldbox))
# 2) add/relocate new
for ch,spec in REL.items():
    if ch=="釕": continue
    np_,nh,ink=spec["new"]; newbox=make_box(np_,nh,ink)
    key=(np_,nh)
    if key not in bykey:
        bykey[key]=dict(page=np_,half=nh,entries="",assigned=[])
        changes.append(dict(char=ch,action="create_row",page=np_,half=nh,new_box=newbox))
    row=bykey[key]
    for a in row["assigned"]:
        if a.get("char")!=ch:
            iou_=iou(newbox,[float(v) for v in ((a.get("cand") or {}).get("box") or [])])
            assert iou_<0.4,(ch,np_,nh,"overlap",a.get("char"),round(iou_,2))
    row["assigned"].append(dict(char=ch,cand=dict(box=newbox)))
    changes.append(dict(char=ch,action="add_new",page=np_,half=nh,new_box=newbox))
# 3) 釕 from old 釘 box
row=bykey[("11_0007","L")]
ding_old=[705.0,608.0,803.0,706.0]
row["assigned"].append(dict(char="釕",cand=dict(box=[float(v) for v in ding_old])))
changes.append(dict(char="釕",action="add_new",page="11_0007",half="L",new_box=ding_old))

# 4) entries rebuild for edited rows (assigned chars sorted by canonical ci)
edited={(c["page"],c["half"]) for c in changes}
for key in edited:
    row=bykey[key]
    chars=[a["char"] for a in row["assigned"]]
    row["entries"]="".join(sorted(chars,key=cidx))
    row["assigned"]=sorted(row["assigned"],key=lambda a:cidx(a["char"]))

# 5) build output preserving unchanged raw lines; insert new rows in page/half order
out_lines=[]; emitted=set()
def emit(key,r):
    if key in emitted: return
    emitted.add(key)
    if key in {(c["page"],c["half"]) for c in changes if c["action"]!="remove_old"}:
        out_lines.append(json.dumps(r,ensure_ascii=False))
    else:
        idx=rows.index(r) if r in rows else None
# simpler: map rows to raw; new rows get dumped
raw_by_key={}
for i,r in enumerate(rows): raw_by_key[(r["page"],r["half"])]=raw[i]
keys=[]; seen=set()
for r in rows:
    k=(r["page"],r["half"]); keys.append(k); seen.add(k)
# add new keys in order
def half_order(h): return 0 if h=="L" else 1
all_keys=sorted(set(keys)|set(bykey.keys()), key=lambda k:(int(k[0][:2]),int(k[0][3:]),half_order(k[1])))
for k in all_keys:
    r=bykey[k]
    if k in raw_by_key and k not in edited:
        out_lines.append(raw_by_key[k])
    else:
        out_lines.append(json.dumps(r,ensure_ascii=False))
with open(OUT,"w",encoding="utf-8") as fo:
    fo.write("\n".join(out_lines)+"\n")

# 6) validations on output
new_rows=[json.loads(l) for l in open(OUT,encoding="utf-8")]
post_chars=all_chars(new_rows)
assert len(post_chars)==len(set(post_chars)),"duplicate chars in v273"
assert len(post_chars)==17006,(len(post_chars))
for ch in ("愈","急","架","紉","釘","釕"):
    assert post_chars.count(ch)==1,(ch,post_chars.count(ch))
# unchanged rows identical (compare by key; new row shifts indices)
new_by={ (r["page"],r["half"]):r for r in new_rows }
for a in rows:
    k=(a["page"],a["half"])
    if k in edited: continue
    b=new_by.get(k)
    assert b is not None,(k,"vanished")
    assert json.dumps(a,ensure_ascii=False,sort_keys=True)==json.dumps(b,ensure_ascii=False,sort_keys=True), k
assert set(new_by)==set((r["page"],r["half"]) for r in rows)|edited,(len(new_by),len(rows),len(edited))
# boxes within row unique
for r in new_rows:
    boxes=[tuple(round(v,1) for v in (a.get("cand") or {}).get("box") or []) for a in r.get("assigned") or []]
    assert len(boxes)==len(set(boxes)),(r["page"],r["half"],"duplicate box")

# 7) empty_assign before/after estimate from geometry quads
geom={}
for line in open(GEOM,encoding="utf-8"):
    g=json.loads(line); geom[g["page"]]=g
def empty_cnt(rows_):
    idx={(r["page"],r["half"]):r for r in rows_}
    cnt=0
    for page,g in geom.items():
        for half,q in (g.get("quads") or {}).items():
            r=idx.get((page,half))
            if r is None or not (r.get("assigned") or []): cnt+=1
    return cnt
before=empty_cnt(rows); after=empty_cnt(new_rows)
summary=dict(
 version="v2.6.3-mapping-v273", date="2026-11-14", source=os.path.relpath(SRC,ROOT), out=os.path.relpath(OUT,ROOT),
 chars_before=len(pre_chars), chars_after=len(post_chars),
 empty_assign_before=before, empty_assign_after=after,
 changes=changes,
 validation=dict(unique_chars=True, expected_chars_once=True, unchanged_rows_identical=True, boxes_in_quad=True),
 note="BF-54 基本区 5 字重定位 + 旧釘框改标釕；扩展区 6 字不处理（owner 2026-11-14）",
)
json.dump(summary,open(SUM,"w",encoding="utf-8"),ensure_ascii=False,indent=1)
print(json.dumps({k:summary[k] for k in ("chars_before","chars_after","empty_assign_before","empty_assign_after")},ensure_ascii=False))
print("changes:")
for c in changes: print(" ",c)
print("wrote",OUT)
