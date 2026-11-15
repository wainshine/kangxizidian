import os, json, sys, time
os.environ.setdefault("PADDLE_PDX_CACHE_HOME", "/Users/wainshine/newAI/kangxizidian/work/paddlex_cache")
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
for k in ("OMP_NUM_THREADS","MKL_NUM_THREADS","OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(k,"1")
import numpy as np, cv2, fitz
cv2.setNumThreads(1)
ROOT="/Users/wainshine/newAI/kangxizidian"
PDFMAP=json.load(open(os.path.join(ROOT,'work/t2/pdf_map.json'),encoding='utf-8'))
_rec=None
def rec():
    global _rec
    if _rec is None:
        from paddleocr import TextRecognition
        _rec=TextRecognition(model_name='PP-OCRv5_server_rec')
    return _rec
def work(item):
    vol,pg=item
    page_key=f"{vol}_{pg:04d}"
    try:
        boxes=json.load(open(os.path.join(ROOT,'work/lead/boxes300',page_key+'.json'),encoding='utf-8'))
    except Exception:
        return {'page':page_key,'error':'no boxes','labels':[],'large':[]}
    doc=fitz.open(os.path.join(ROOT,'康熙字典',PDFMAP[vol]))
    try:
        pix=doc[pg-1].get_pixmap(dpi=300,colorspace=fitz.csGRAY)
        img=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width)
    finally:
        doc.close()
    r=rec()
    labels=[]; large=[]
    for half in ('R','L'):
        for c in boxes.get('halves',{}).get(half,{}).get('cands',[]):
            b=c.get('box') or []
            if len(b)!=4: continue
            w=b[2]-b[0]; h=b[3]-b[1]
            if 18<=w<=70 and 18<=h<=65:
                x0,y0,x1,y1=[int(v*2) for v in b]; pad=6
                cr=img[max(0,y0-pad):y1+pad,max(0,x0-pad):x1+pad]
                if cr.size==0: continue
                if cr.ndim==2: cr=np.stack([cr]*3,-1)
                cr=cv2.resize(cr,None,fx=1.5,fy=1.5,interpolation=cv2.INTER_CUBIC)
                try:
                    out=r.predict(cr)[0]; d=out.json.get('res',{}) if hasattr(out,'json') else {}
                    t=(d.get('rec_text') or '').strip(); s=float(d.get('rec_score') or 0)
                except Exception:
                    t=''; s=0
                if t and s>0.4: labels.append({'half':half,'box':[round(v,1) for v in b],'text':t,'score':round(s,3)})
            elif w>=60 and h>=60:
                large.append({'half':half,'box':[round(v,1) for v in b]})
    # pair 古/文 (vertical adjacent) then variant large below
    pairs=[]
    for half in ('L','R'):
        ls=[x for x in labels if x['half']==half]
        for a in ls:
            ta=a['text']
            # 单标签直接含「古文/籀文/或作」
            if any(k in ta for k in ('古文','籀文','或作')):
                pairs.append((half,a,None)); continue
            for b in ls:
                if b is a or b['box'][1]<=a['box'][1]: continue
                ax=(a['box'][0]+a['box'][2])/2; bx=(b['box'][0]+b['box'][2])/2
                if abs(ax-bx)<=40 and 0<=b['box'][1]-a['box'][3]<=90:
                    ok=((a['text'].endswith(('古','籀')) and '文' in b['text']) or
                        (a['text'].endswith('或') and '作' in b['text']))
                    if ok: pairs.append((half,a,b))
    out=[]
    for half,a,b in pairs:
        bx=(a['box'][0]+a['box'][2])/2; by=(b['box'][1] if b else a['box'][3])
        best=None
        for lb in large:
            if lb['half']!=half: continue
            lbx=(lb['box'][0]+lb['box'][2])/2
            if abs(lbx-bx)<=70 and 0<=lb['box'][1]-by<=160:
                d=lb['box'][1]-by
                if best is None or d<best[0]: best=(d,lb)
        if best:
            out.append({'half':half,'label':[a['box'],(b['box'] if b else [])],'variant_block':best[1]['box'],'label_text':a['text']+((b['text']) if b else '')})
    return {'page':page_key,'vol':vol,'page_no':pg,'labels':labels,'large':large,'variants':out}
if __name__=='__main__':
    pages=json.load(open('/tmp/all_body_pages.json'))
    N=int(sys.argv[1]) if len(sys.argv)>1 else len(pages)
    W=int(sys.argv[2]) if len(sys.argv)>2 else 8
    pages=pages[:N]
    from multiprocessing import Pool
    t0=time.time(); results=[]
    with Pool(W) as pool:
        for i,r in enumerate(pool.imap_unordered(work,pages),1):
            results.append(r)
            if i%10==0: print('done',i,'/',len(pages),'elapsed',round(time.time()-t0,1),flush=True)
    with open('/tmp/guwen_local_all.jsonl','w',encoding='utf-8') as fo:
        for r in results: fo.write(json.dumps(r,ensure_ascii=False)+'\n')
    nv=sum(len(r.get('variants') or []) for r in results)
    print(json.dumps({'pages':len(results),'variants':nv,'elapsed_s':round(time.time()-t0,1)}))
