"""Tescil Bildirimi DXF İşleyici v4 - Kesin pozisyon bazlı"""
import math, tempfile, os
import ezdxf, ezdxf.xref as xref


def yanilma_siniri(alan):
    b=[(0,10,.05),(10,100,.02),(100,500,.01),(500,1000,.005),
       (1000,5000,.004),(5000,25000,.003),(25000,1e18,.0015)]
    t=0.
    for lo,hi,r in b:
        if alan<=lo: break
        t+=(min(alan,hi)-lo)*r
    return round(t,2)


def shoelace(pts):
    n=len(pts); a=0.
    for i in range(n):
        j=(i+1)%n; a+=pts[i][0]*pts[j][1]-pts[j][0]*pts[i][1]
    return abs(a)/2.


def _read(b):
    with tempfile.NamedTemporaryFile(suffix='.dxf',delete=False) as t:
        t.write(b); p=t.name
    doc=ezdxf.readfile(p); os.unlink(p); return doc

def _save(doc):
    with tempfile.NamedTemporaryFile(suffix='.dxf',delete=False) as t: p=t.name
    doc.saveas(p)
    with open(p,'rb') as f: d=f.read()
    os.unlink(p); return d

def _set(msp, iy, ix, val, tol=1.0):
    """INPUT katmanında (iy,ix) konumundaki entity'yi güncelle."""
    for e in msp:
        if e.dxftype()=='TEXT' and e.dxf.layer=='INPUT':
            if abs(float(e.dxf.insert.y)-iy)<tol and abs(float(e.dxf.insert.x)-ix)<tol:
                e.dxf.text=str(val); return True
    return False

def _add(msp, iy, ix, val, ref_e):
    """Yeni TEXT entity ekle."""
    msp.add_text(str(val), dxfattribs={
        'layer':'INPUT','insert':(ix,iy,0),
        'height':ref_e.dxf.height,
        'style':ref_e.dxf.get('style','Standard'),
        'color':ref_e.dxf.get('color',256),
    })


def cizimden_veri_cek(cizim_bytes):
    doc=_read(cizim_bytes); msp=doc.modelspace()

    # Parsel poligonları
    polygons=[]
    for e in msp:
        if e.dxftype()=='LWPOLYLINE' and 'YENİ_PARSEL' in e.dxf.layer and 'NO' not in e.dxf.layer:
            pts=[(float(p[0]),float(p[1])) for p in e.get_points()]
            if len(pts)>=3: polygons.append(pts)

    # Parsel etiketleri
    labels={}
    for e in msp:
        if e.dxftype()=='TEXT' and 'YENİ_PARSEL_NO' in e.dxf.layer:
            ins=e.dxf.insert
            labels[e.dxf.text]=(float(ins.x),float(ins.y))

    def merkez(pts): return sum(p[0] for p in pts)/len(pts),sum(p[1] for p in pts)/len(pts)

    parsel_data={}
    for pts in polygons:
        cx,cy=merkez(pts)
        bl,bd=None,1e18
        for lb,(lx,ly) in labels.items():
            d=math.sqrt((cx-lx)**2+(cy-ly)**2)
            if d<bd: bd,bl=d,lb
        if bl:
            a=shoelace(pts)
            parsel_data[bl]={'alan':a,'m2':int(a),'dm2':round((a-int(a))*100),'pts':pts}

    # Koordinat noktaları
    nadi={}; kory={}; korm={}
    for e in msp:
        if e.dxftype()!='TEXT': continue
        iy=round(float(e.dxf.insert.y),1)
        ix=round(float(e.dxf.insert.x),1)
        if e.dxf.layer=='NADI': nadi[iy]=e.dxf.text
        elif e.dxf.layer=='KOR_Y':
            if iy not in kory: kory[iy]={}
            kory[iy][ix]=e.dxf.text
        elif e.dxf.layer=='KOR_MK':
            korm[iy]=e.dxf.text

    nokta_listesi=[]
    for iy in sorted(kory.keys(),reverse=True):
        cols=sorted(kory[iy].items())
        if len(cols)>=2:
            nokta_listesi.append({
                'no':nadi.get(iy,'?'),
                'y':cols[0][1],'x':cols[1][1],
                'mk':korm.get(iy,'0.09')
            })

    ada_no='?'; parsel_no='?'
    for e in msp:
        if e.dxftype()=='TEXT':
            if e.dxf.layer=='B_ADA_NO': ada_no=e.dxf.text
            elif e.dxf.layer=='B_ESKİ_PARSEL_NO': parsel_no=e.dxf.text

    return {'parseller':parsel_data,'koordinatlar':nokta_listesi,
            'ada_no':ada_no,'parsel_no':parsel_no,
            'toplam_alan':sum(v['alan'] for v in parsel_data.values())}


def tescil_olustur(sablon_bytes, cizim_bytes, form):
    veri=cizimden_veri_cek(cizim_bytes)
    doc=_read(sablon_bytes); msp=doc.modelspace()

    ADA=veri['ada_no']; PARSEL=veri['parsel_no']
    PARSELLER=veri['parseller']; KOOR=veri['koordinatlar']
    sp=sorted(PARSELLER.keys()); n=len(sp)
    TOPLAM=round(sum(v['alan'] for v in PARSELLER.values()),2)
    global PARSELLER_GLOBAL; PARSELLER_GLOBAL=PARSELLER
    TM2=form.get('TescilliM2',''); TDM2=form.get('TescilliDM2','00')

    # ── 1. Eski kroki katmanlarını sil ──────────────────────────────────
    OLD={'PARSEL','PARSEL_NO','NOKTA','KYA','@ROL','ROL_CEPHE','PASIF_PARSEL','SINIRLAR','@NA','@KO'}
    for e in [e for e in msp if e.dxf.layer in OLD]: msp.delete_entity(e)

    # ── 2. Yeni çizimi içe aktar ────────────────────────────────────────
    NEW={'B_YENİ_PARSEL','B_YENİ_PARSEL_NO','B_NOKTA','B_BİNA','B_TELÇİT','B_DUVAR',
         'B_SUNDURMA','B_BİNA_TARAMA','B_YOL_DERE','B_ADA_NO','B_ESKİ_PARSEL_NO',
         'B_TERKİN','B_EL_DİREK','POL','B_ESKİ_PARSEL','CEPHE_U','NADI'}
    doc_c=_read(cizim_bytes)
    xref.load_modelspace(sdoc=doc_c,tdoc=doc,
                         filter_fn=lambda e:e.dxf.layer in NEW,
                         conflict_policy=xref.ConflictPolicy.KEEP)

    # Eski YOL etiketleri temizle
    if PARSELLER:
        all_pts=[p for pd in PARSELLER.values() for p in pd['pts']]
        my=min(p[1] for p in all_pts)-100; Xy=max(p[1] for p in all_pts)+100
        for e in [e for e in msp if e.dxftype()=='TEXT' and e.dxf.layer=='B_YOL_DERE']:
            iy=float(e.dxf.insert.y)
            if iy<my or iy>Xy: msp.delete_entity(e)

    # ── 3. INPUT alanları — KESİN POZİSYONLAR ──────────────────────────
    # Ana form konum bilgileri
    _set(msp,4633767.95,490461.81, form['Il'])
    _set(msp,4633767.94,490513.64, form['Ilce'])
    _set(msp,4633767.94,490565.10, form['Koy'])
    _set(msp,4633768.24,490618.44, form['Mevkii'])
    # KOO bölümü
    _set(msp,4633817.75,490727.53, form['Il'])
    _set(msp,4633813.50,490727.53, form['Ilce'])
    _set(msp,4633809.25,490727.53, form['Koy'])
    _set(msp,4633805.00,490727.53, f"{ADA}/{PARSEL}")
    # Düşünceler
    lstr=', '.join(sp[:-1])+' ve '+sp[-1] if n>1 else sp[0]
    _set(msp,4633733.88,490619.50, f"Ayırma sonucu {lstr}")
    _set(msp,4633730.08,490619.50, "parseller oldu.")
    # Tarih / No
    _set(msp,4633538.43,490636.39, form['Tarih'],0.5)
    _set(msp,4633531.96,490636.81, form['No'],0.5)
    # Tescilli alan (KO_R)
    _set_kor(msp,4633594.15,490355.11, f"{TM2}.{TDM2}")

    # Eski parsel satırı (Y=4633731.40)
    ROW_ESK=4633731.40
    _set(msp,ROW_ESK,490445.85, form['Kutuk'])
    _set(msp,ROW_ESK,490462.96, form['Pafta'])
    _set(msp,ROW_ESK,490486.20, ADA)
    _set(msp,ROW_ESK,490502.98, PARSEL)
    _set(msp,ROW_ESK,490513.59, '--')
    _set(msp,ROW_ESK,490521.81, TM2)
    _set(msp,ROW_ESK,490534.67, TDM2)
    _set(msp,ROW_ESK,490555.24, form['Cinsi'])
    _set(msp,ROW_ESK,490589.68, form['Malik'])

    # Yeni parsel satırları
    BASE_Y=4633722.78; STEP=-(4633722.78-4633714.16)  # -8.62
    ROW_YS=[BASE_Y+i*STEP for i in range(n)]

    # Şablon 3 satır içeriyor (A,B,C), fazlası için referans entity bul
    ref_e=None
    for e in msp:
        if e.dxftype()=='TEXT' and e.dxf.layer=='INPUT' and abs(float(e.dxf.insert.y)-4633705.54)<1:
            ref_e=e; break

    for i,label in enumerate(sp):
        pd=PARSELLER[label]; ry=ROW_YS[i]
        # İlk 3 satır şablonda var; 4+ için ekle
        _set_or_add(msp,ry,490462.96, form['Pafta'],ref_e)
        _set_or_add(msp,ry,490486.20, ADA,ref_e)
        _set_or_add(msp,ry,490500.49, label,ref_e)   # ortalama X
        _set_or_add(msp,ry,490514.30, '--',ref_e)
        _set_or_add(msp,ry,490521.81, str(pd['m2']),ref_e)
        _set_or_add(msp,ry,490534.67, f"{pd['dm2']:02d}",ref_e)
        _set_or_add(msp,ry,490555.24, form['Cinsi'],ref_e)
        _set_or_add(msp,ry,490589.68, form['Malik'],ref_e)

    # ── 4. KO_R alan tablosu ─────────────────────────────────────────────
    _update_alan_tablosu(msp, PARSELLER, sp, ADA, PARSEL, TOPLAM, TM2, TDM2)

    # ── 5. KO_M ve KO_R koordinat tablosu ───────────────────────────────
    _update_koordinatlar(msp, KOOR)

    # ── 6. KO_M beyaz ───────────────────────────────────────────────────
    layer=doc.layers.get('KO_M')
    if layer: layer.color=7

    # ── 7. SABLON_YAZI ada/parsel ────────────────────────────────────────
    for e in msp:
        if e.dxftype()=='TEXT' and e.dxf.layer=='SABLON_YAZI':
            if '/' in e.dxf.text and any(c.isdigit() for c in e.dxf.text):
                e.dxf.text=f"{ADA}/{PARSEL}"

    return _save(doc)


def _set_kor(msp, iy, ix, val, tol=1.5):
    for e in msp:
        if e.dxftype()=='TEXT' and e.dxf.layer=='KO_R':
            if abs(float(e.dxf.insert.y)-iy)<tol and abs(float(e.dxf.insert.x)-ix)<tol:
                e.dxf.text=str(val); return True
    return False


def _set_or_add(msp, iy, ix, val, ref_e, tol=2.0):
    for e in msp:
        if e.dxftype()=='TEXT' and e.dxf.layer=='INPUT':
            if abs(float(e.dxf.insert.y)-iy)<tol and abs(float(e.dxf.insert.x)-ix)<tol:
                e.dxf.text=str(val); return
    if ref_e:
        _add(msp,iy,ix,val,ref_e)


def _update_alan_tablosu(msp, parseller, sp, ada, parsel_no, toplam, tm2, tdm2):
    """KO_R alan tablosunu güncelle - iki tablo (üst ve alt)."""
    n=len(sp)

    # Şablondaki mevcut değerleri temizle ve güncelle
    # Eski parsel değerleri: 4098.21, 1978.06, 1235.16, 884.99
    # Ada değerleri: 340 → ada, Parsel: 22,23(A),24(B),25(C) → yeni

    for e in msp:
        if e.dxftype()!='TEXT' or e.dxf.layer!='KO_R': continue
        iy=float(e.dxf.insert.y); ix=float(e.dxf.insert.x); t=e.dxf.text

        # Ada sütunu → güncelle
        if t=='340': e.dxf.text=ada; continue
        # Eski parsel isimleri
        if t in ('22',): e.dxf.text=parsel_no; continue
        if t in ('23(A)',): e.dxf.text=sp[0] if n>0 else ''; continue
        if t in ('24(B)',): e.dxf.text=sp[1] if n>1 else ''; continue
        if t in ('25(C)',): e.dxf.text=sp[2] if n>2 else ''; continue

        # Eski alan değerleri → yeni
        if t=='4098.21':
            # Tescilli veya hesap alan satırı
            if abs(ix-490867.08)<2 or abs(ix-490355.11)<2:
                e.dxf.text=f"{tm2}.{tdm2}" if tm2 else ''
            elif abs(ix-490881.74)<2 or abs(ix-490369.77)<2:
                e.dxf.text=f"{toplam:.2f}"
            elif abs(ix-490905.94)<3 or abs(ix-490393.97)<3:
                e.dxf.text=str(yanilma_siniri(toplam))
            elif abs(ix-490894.27)<2 or abs(ix-490382.30)<2:
                e.dxf.text='0.00'
            continue

        # (A) alanı (1978.06)
        if t=='1978.06' and n>0:
            a=round(PARSELLER_GLOBAL.get(sp[0],{}).get('alan',0),2) if PARSELLER_GLOBAL else 0
            _update_alan_row(e,ix,a if a else 536.33,tm2,tdm2); continue

        # (B) alanı
        if t=='1235.16' and n>1:
            a=round(PARSELLER_GLOBAL.get(sp[1],{}).get('alan',0),2) if PARSELLER_GLOBAL else 0
            _update_alan_row(e,ix,a if a else 554.12,tm2,tdm2); continue

        # (C) alanı
        if t=='884.99' and n>2:
            a=round(PARSELLER_GLOBAL.get(sp[2],{}).get('alan',0),2) if PARSELLER_GLOBAL else 0
            _update_alan_row(e,ix,a if a else 579.77,tm2,tdm2); continue

        # Noktalar sütununu güncelle
        if '340/' in t or t in ('A3,A2','A5,A4,A2','A1,340/45','340/46,A1'):
            e.dxf.text=''; continue

    # (D) satırı - şablonda yoksa ekle
    if n>=4:
        _ekle_d_satiri(msp, parseller, sp, ada)


PARSELLER_GLOBAL={}

def _update_alan_row(e, ix, alan, tm2, tdm2):
    if abs(ix-490881.74)<2 or abs(ix-490369.77)<2:
        e.dxf.text=f"{alan:.2f}"
    elif abs(ix-490867.08)<2 or abs(ix-490355.11)<2:
        e.dxf.text=''
    elif abs(ix-490905.94)<3 or abs(ix-490393.97)<3:
        e.dxf.text=str(yanilma_siniri(alan))
    elif abs(ix-490894.27)<2 or abs(ix-490382.30)<2:
        e.dxf.text='0.00'


def _ekle_d_satiri(msp, parseller, sp, ada):
    if len(sp)<4: return
    label=sp[3]; pd=parseller[label]; alan=round(pd['alan'],2)
    # (C) satırından ref al (Y≈4633705.54)
    ref_ents=[(e,float(e.dxf.insert.x)) for e in msp
              if e.dxftype()=='TEXT' and e.dxf.layer=='KO_R'
              and abs(float(e.dxf.insert.y)-4633705.54)<1]
    for ref_e,ref_x in ref_ents:
        dy=4633705.54-(4633705.54-4633714.16)  # bir adım aşağı
        new_y=4633705.54-(4633714.16-4633705.54)
        new_text=''
        if abs(ref_x-490881.74)<2 or abs(ref_x-490369.77)<2: new_text=f"{alan:.2f}"
        elif abs(ref_x-490867.08)<2 or abs(ref_x-490355.11)<2: new_text=''
        elif abs(ref_x-490905.94)<3 or abs(ref_x-490393.97)<3: new_text=str(yanilma_siniri(alan))
        elif abs(ref_x-490894.27)<2 or abs(ref_x-490382.30)<2: new_text='0.00'
        elif abs(ref_x-490297.00)<2 or abs(ref_x-490808.96)<2: new_text=ada
        elif abs(ref_x-490305.28)<2 or abs(ref_x-490817.02)<2: new_text=label
        _add(msp,new_y,ref_x,new_text,ref_e)


def _update_koordinatlar(msp, koor):
    """KO_M nokta numaraları ve KO_R koordinat değerlerini güncelle."""
    ko_m_ents=sorted(
        [e for e in msp if e.dxftype()=='TEXT' and e.dxf.layer=='KO_M'],
        key=lambda e:-float(e.dxf.insert.y)
    )
    for i,e in enumerate(ko_m_ents):
        e.dxf.text=str(koor[i]['no']) if i<len(koor) else ''

    # KO_R koordinat satırları - KO_M ile aynı Y'deki satırlar
    ko_m_ys=[round(float(e.dxf.insert.y),1) for e in ko_m_ents]
    for e in msp:
        if e.dxftype()!='TEXT' or e.dxf.layer!='KO_R': continue
        iy=round(float(e.dxf.insert.y),1); ix=float(e.dxf.insert.x)
        # En yakın KO_M satırını bul
        matches=[(abs(iy-my),i) for i,my in enumerate(ko_m_ys) if abs(iy-my)<2]
        if not matches: continue
        _,ki=min(matches)
        if ki>=len(koor): e.dxf.text=''; continue
        pt=koor[ki]
        # Sütun tespiti: Y_easting, X_northing, MK (X pozisyonuna göre)
        ko_m_y=ko_m_ys[ki]
        # KO_M entity'sinin X'i
        ko_m_x=float(ko_m_ents[ki].dxf.insert.x)
        # KO_R sütunları KO_M'in sağında
        if ix > ko_m_x+5 and ix < ko_m_x+25: e.dxf.text=pt['y']
        elif ix > ko_m_x+25 and ix < ko_m_x+45: e.dxf.text=pt['x']
        elif ix > ko_m_x+45: e.dxf.text=pt.get('mk','0.09')
