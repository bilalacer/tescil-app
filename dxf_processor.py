"""Tescil Bildirimi DXF İşleyici v5 - Kesin pozisyon haritası"""
import math, tempfile, os
import ezdxf, ezdxf.xref as xref

# ─── Yardımcı fonksiyonlar ────────────────────────────────────────────────
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

def _ent(msp, layer, iy, ix, tol=1.5):
    """Belirli katman ve konumdaki TEXT entity'yi döndür."""
    for e in msp:
        if e.dxftype()=='TEXT' and e.dxf.layer==layer:
            if abs(float(e.dxf.insert.y)-iy)<tol and abs(float(e.dxf.insert.x)-ix)<tol:
                return e
    return None

def _set(msp, layer, iy, ix, val, tol=1.5):
    e=_ent(msp,layer,iy,ix,tol)
    if e: e.dxf.text=str(val); return True
    return False

def _add_text(msp, layer, iy, ix, val, ref_e):
    msp.add_text(str(val), dxfattribs={
        'layer':layer,'insert':(ix,iy,0),
        'height':ref_e.dxf.height,
        'style':ref_e.dxf.get('style','Standard'),
        'color':ref_e.dxf.get('color',256),
    })

# ─── Çizimden veri çekme ─────────────────────────────────────────────────
def cizimden_veri_cek(cizim_bytes):
    doc=_read(cizim_bytes); msp=doc.modelspace()

    # Parsel poligonları
    polygons=[]
    for e in msp:
        if e.dxftype()=='LWPOLYLINE' and 'YENİ_PARSEL' in e.dxf.layer and 'NO' not in e.dxf.layer:
            pts=[(float(p[0]),float(p[1])) for p in e.get_points()]
            if len(pts)>=3: polygons.append(pts)

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

    # Koordinat noktaları (NADI + KOR_Y katmanları)
    nadi={}; kory_rows={}
    for e in msp:
        if e.dxftype()!='TEXT': continue
        iy=round(float(e.dxf.insert.y),1); ix=round(float(e.dxf.insert.x),1)
        if e.dxf.layer=='NADI': nadi[iy]=e.dxf.text
        elif e.dxf.layer=='KOR_Y':
            if iy not in kory_rows: kory_rows[iy]={}
            kory_rows[iy][ix]=e.dxf.text
        elif e.dxf.layer=='KOR_MK':
            if iy not in kory_rows: kory_rows[iy]={}
            kory_rows[iy]['mk']=e.dxf.text

    nokta_listesi=[]
    for iy in sorted(kory_rows.keys(),reverse=True):
        cols=kory_rows[iy]
        # KOR_Y sütunları X pozisyonuna göre sıralı: no, Y_easting, X_northing, MK
        sorted_cols=sorted([(x,v) for x,v in cols.items() if x!='mk'])
        if len(sorted_cols)>=3:
            nokta_listesi.append({
                'no':sorted_cols[0][1],   # nokta no (1,2,3...)
                'y': sorted_cols[1][1],   # Y easting (490xxx)
                'x': sorted_cols[2][1],   # X northing (4633xxx)
                'mk':sorted_cols[3][1] if len(sorted_cols)>3 else cols.get('mk','0.09')
            })
        elif len(sorted_cols)==2:
            # Eski format: NADI'den no, KOR_Y'den koordinatlar
            nokta_listesi.append({
                'no':nadi.get(iy,'?'),
                'y': sorted_cols[0][1],
                'x': sorted_cols[1][1],
                'mk':cols.get('mk','0.09')
            })

    ada_no='?'; parsel_no='?'
    for e in msp:
        if e.dxftype()=='TEXT':
            if e.dxf.layer=='B_ADA_NO': ada_no=e.dxf.text
            elif e.dxf.layer=='B_ESKİ_PARSEL_NO': parsel_no=e.dxf.text

    return {'parseller':parsel_data,'koordinatlar':nokta_listesi,
            'ada_no':ada_no,'parsel_no':parsel_no,
            'toplam_alan':sum(v['alan'] for v in parsel_data.values())}

# ─── Ana işlev ───────────────────────────────────────────────────────────
def tescil_olustur(sablon_bytes, cizim_bytes, form):
    veri=cizimden_veri_cek(cizim_bytes)
    doc=_read(sablon_bytes); msp=doc.modelspace()

    ADA=veri['ada_no']; PARSEL=veri['parsel_no']
    P=veri['parseller']; KOOR=veri['koordinatlar']
    sp=sorted(P.keys()); n=len(sp)
    TOPLAM=round(sum(v['alan'] for v in P.values()),2)
    TM2=form.get('TescilliM2',''); TDM2=form.get('TescilliDM2','00')

    # 1. ŞABLONDAKİ KROKİ ENTİTYLERİNİ SİL
    DEL_LAYERS={'PARSEL','PARSEL_NO','NOKTA','KYA','@ROL','ROL_CEPHE',
                'PASIF_PARSEL','SINIRLAR','@NA','@KO',
                'B_YENİ_PARSEL','B_YENİ_PARSEL_NO','B_ADA_NO','B_ESKİ_PARSEL_NO',
                'B_NOKTA','B_ESKİ_PARSEL','B_YOL_DERE','B_BİNA','B_TELÇİT',
                'B_DUVAR','B_SUNDURMA','B_BİNA_TARAMA','B_TERKİN','B_EL_DİREK',
                'POL','CEPHE_U','NADI'}
    for e in [e for e in msp if e.dxf.layer in DEL_LAYERS]:
        msp.delete_entity(e)

    # 2. YENİ ÇİZİMİ İÇE AKTAR
    NEW={'B_YENİ_PARSEL','B_YENİ_PARSEL_NO','B_NOKTA','B_BİNA','B_TELÇİT',
         'B_DUVAR','B_SUNDURMA','B_BİNA_TARAMA','B_YOL_DERE','B_ADA_NO',
         'B_ESKİ_PARSEL_NO','B_TERKİN','B_EL_DİREK','POL','B_ESKİ_PARSEL',
         'CEPHE_U','NADI'}
    doc_c=_read(cizim_bytes)
    xref.load_modelspace(sdoc=doc_c,tdoc=doc,
                         filter_fn=lambda e:e.dxf.layer in NEW,
                         conflict_policy=xref.ConflictPolicy.KEEP)

    # 3. INPUT - KESİN POZİSYONLAR (TESCİL_BİLDİRİMİ_örnek.dxf'ten alındı)
    # Ana form
    _set(msp,'INPUT',4633767.95,490461.81, form['Il'])
    _set(msp,'INPUT',4633767.94,490513.64, form['Ilce'])
    _set(msp,'INPUT',4633767.94,490565.10, form['Koy'])
    _set(msp,'INPUT',4633768.24,490618.44, form['Mevkii'])
    # KOO bölümü
    _set(msp,'INPUT',4633817.75,490727.53, form['Il'])
    _set(msp,'INPUT',4633813.50,490727.53, form['Ilce'])
    _set(msp,'INPUT',4633809.25,490727.53, form['Koy'])
    _set(msp,'INPUT',4633805.00,490727.53, f"{ADA}/{PARSEL}")
    # Düşünceler
    lstr=', '.join(sp[:-1])+' ve '+sp[-1] if n>1 else sp[0]
    _set(msp,'INPUT',4633733.88,490619.50, f"Ayırma sonucu {lstr}")
    _set(msp,'INPUT',4633730.08,490619.50, "parseller oldu.")
    # Tarih / No
    _set(msp,'INPUT',4633538.43,490636.39, form['Tarih'],0.5)
    _set(msp,'INPUT',4633531.96,490636.81, form['No'],0.5)
    # Tescilli alan (INPUT layer - alt tablo)
    _set(msp,'INPUT',4633594.15,490355.11, f"{TM2}.{TDM2}",2)

    # Eski parsel satırı (Y=4633731.40)
    EY=4633731.40
    _set(msp,'INPUT',EY,490445.85, form['Kutuk'])
    _set(msp,'INPUT',EY,490462.96, form['Pafta'])
    _set(msp,'INPUT',EY,490486.20, ADA)
    _set(msp,'INPUT',EY,490502.98, PARSEL)
    _set(msp,'INPUT',EY,490513.59, '--')
    _set(msp,'INPUT',EY,490521.81, TM2)
    _set(msp,'INPUT',EY,490534.67, TDM2)
    _set(msp,'INPUT',EY,490555.24, form['Cinsi'])
    _set(msp,'INPUT',EY,490589.68, form['Malik'])

    # Yeni parsel satırları (3 satır şablonda var: A,B,C)
    PARSEL_ROW_YS=[4633722.78, 4633714.16, 4633705.54]
    PARSEL_COLS={
        'pafta':490462.96,'ada':490486.20,'parsel':490500.49,
        'ha':490514.30,'m2':490521.81,'dm2':490534.67,
        'cinsi':490555.24,'malik':490589.68
    }
    for i,label in enumerate(sp):
        pd=P[label]
        if i < len(PARSEL_ROW_YS):
            ry=PARSEL_ROW_YS[i]
            _set(msp,'INPUT',ry,PARSEL_COLS['pafta'], form['Pafta'])
            _set(msp,'INPUT',ry,PARSEL_COLS['ada'],   ADA)
            _set(msp,'INPUT',ry,PARSEL_COLS['parsel'],label,2)
            _set(msp,'INPUT',ry,PARSEL_COLS['ha'],    '--')
            _set(msp,'INPUT',ry,PARSEL_COLS['m2'],    str(pd['m2']))
            _set(msp,'INPUT',ry,PARSEL_COLS['dm2'],   f"{pd['dm2']:02d}")
            _set(msp,'INPUT',ry,PARSEL_COLS['cinsi'], form['Cinsi'])
            _set(msp,'INPUT',ry,PARSEL_COLS['malik'], form['Malik'])
        else:
            # Ekstra satır ekle (4. parsel ve sonrası)
            ref=_ent(msp,'INPUT',4633705.54,490462.96,2)
            if ref:
                STEP=4633705.54-4633714.16  # -8.62
                ry=4633705.54+(i-2)*STEP
                for col,cx in PARSEL_COLS.items():
                    if col=='pafta': val=form['Pafta']
                    elif col=='ada': val=ADA
                    elif col=='parsel': val=label
                    elif col=='ha': val='--'
                    elif col=='m2': val=str(pd['m2'])
                    elif col=='dm2': val=f"{pd['dm2']:02d}"
                    elif col=='cinsi': val=form['Cinsi']
                    elif col=='malik': val=form['Malik']
                    _add_text(msp,'INPUT',ry,cx,val,ref)

    # Parsel noktalarını hesapla
    def parsel_noktalar(label):
        if label not in P or not KOOR: return ''
        pts = P[label]['pts']
        nos = []
        for px,py in pts:
            best_no,best_d='?',1e9
            for pt in KOOR:
                try:
                    ky=float(pt['y']); kx=float(pt['x'])
                    d=math.sqrt((px-ky)**2+(py-kx)**2)
                    if d<best_d: best_d,best_no=d,pt['no']
                except: pass
            if best_d<5 and best_no!='?': nos.append(str(best_no))
        # Tekrarları kaldır, sırayı koru
        seen=set(); result=[]
        for no in nos:
            if no not in seen: seen.add(no); result.append(no)
        return ','.join(result)

    # Tüm noktalar (eski parsel)
    tum_noktalar=','.join(str(pt['no']) for pt in KOOR)

    # 3b. Eski devam satırlarını (continuation rows) temizle
    # Bunlar şablondaki uzun noktalar listesinin ikinci satırları
    CONT_ROWS=[
        # Alt tablo continuation Y'leri (uzun noktalar listesi 2. satırları)
        4633590.89, 4633581.64,
        # Üst tablo continuation Y'leri
        4633756.07, 4633746.82,
    ]
    for e in msp:
        if e.dxftype()=='TEXT' and e.dxf.layer=='KO_R':
            iy=float(e.dxf.insert.y)
            for cy in CONT_ROWS:
                if abs(iy-cy)<0.3:
                    e.dxf.text=''
                    break

    # 4. KO_R ALAN TABLOSU - EXACT Y POZİSYONLARI
    # Alt tablo satır Y'leri (şablondan):
    ALT_ROWS={
        4633594.15: ('ESK', None),
        4633584.90: ('YEN', sp[0] if n>0 else ''),
        4633576.87: ('YEN', sp[1] if n>1 else ''),
        4633570.59: ('YEN', sp[2] if n>2 else ''),
    }
    # Üst tablo satır Y'leri:
    UST_ROWS={
        4633759.33: ('ESK', None),
        4633750.08: ('YEN', sp[0] if n>0 else ''),
        4633742.05: ('YEN', sp[1] if n>1 else ''),
        4633735.77: ('YEN', sp[2] if n>2 else ''),
    }

    def update_alan_row(msp, row_y, tip, label, tol=0.5,
                          tum_noktalar=tum_noktalar, parsel_noktalar=parsel_noktalar):
        """Tek alan tablosu satırını güncelle."""
        if tip=='ESK':
            alan=TOPLAM; tesc=f"{TM2}.{TDM2}" if TM2 else ''; lbl=PARSEL; ada_val=ADA
        else:
            if not label or label not in P: return
            alan=round(P[label]['alan'],2); tesc=f"{alan:.2f}"; lbl=label; ada_val=ADA

        ys=yanilma_siniri(alan)

        # Her iki tablonun sütun X'leri farklı - ikisini de tara
        for e in msp:
            if e.dxftype()!='TEXT' or e.dxf.layer!='KO_R': continue
            iy=float(e.dxf.insert.y); ix=float(e.dxf.insert.x)
            if abs(iy-row_y)>tol: continue
            t=e.dxf.text

            # Ada sütunu
            if abs(ix-490808.96)<1 or abs(ix-490297.00)<1: e.dxf.text=ada_val
            # Parsel sütunu
            elif abs(ix-490817.02)<2 or abs(ix-490305.28)<2 or abs(ix-490818.30)<2 or abs(ix-490306.33)<2:
                e.dxf.text=lbl
            # Noktalar sütunu
            elif abs(ix-490827.16)<2 or abs(ix-490315.19)<2:
                if tip=='ESK': e.dxf.text=tum_noktalar
                else: e.dxf.text=parsel_noktalar(lbl) if lbl else ''
            # Tescilli alan (yeni parseller için hesap alan ile aynı)
            elif abs(ix-490867.08)<2 or abs(ix-490355.11)<2 or abs(ix-490868.60)<2 or abs(ix-490356.63)<2:
                e.dxf.text=tesc if tesc else (f"{alan:.2f}" if tip=='YEN' else '')
            # Hesap alan
            elif abs(ix-490881.74)<2 or abs(ix-490369.77)<2 or abs(ix-490883.26)<2 or abs(ix-490371.29)<2:
                e.dxf.text=f"{alan:.2f}"
            # Fark
            elif abs(ix-490894.27)<2 or abs(ix-490382.30)<2:
                e.dxf.text='0.00'
            # Yanılma sınırı
            elif abs(ix-490905.94)<3 or abs(ix-490393.97)<3 or abs(ix-490907.46)<3 or abs(ix-490395.49)<3:
                e.dxf.text=str(ys)

    for row_y,(tip,label) in ALT_ROWS.items():
        update_alan_row(msp,row_y,tip,label)
    for row_y,(tip,label) in UST_ROWS.items():
        update_alan_row(msp,row_y,tip,label)

    # D satırı ekle (4. parsel varsa)
    if n>=4:
        label_d=sp[3]; pd_d=P[label_d]; alan_d=round(pd_d['alan'],2); ys_d=yanilma_siniri(alan_d)
        STEP_ALT=4633570.59-4633576.87; STEP_UST=4633735.77-4633742.05
        for base_y, step, x_map in [
            (4633570.59, STEP_ALT, {
                490297.00:ADA, 490305.20:label_d,
                490315.19:parsel_noktalar(label_d),
                490355.11:f"{alan_d:.2f}", 490369.77:f"{alan_d:.2f}",
                490382.30:'0.00', 490393.97:str(ys_d)
            }),
            (4633735.77, STEP_UST, {
                490808.96:ADA, 490816.94:label_d,
                490827.16:parsel_noktalar(label_d),
                490867.08:f"{alan_d:.2f}", 490881.74:f"{alan_d:.2f}",
                490894.27:'0.00', 490905.94:str(ys_d)
            }),
        ]:
            new_y=base_y+step
            ref=None
            for e in msp:
                if e.dxftype()=='TEXT' and e.dxf.layer=='KO_R' and abs(float(e.dxf.insert.y)-base_y)<0.5:
                    ref=e; break
            if ref:
                for cx,val in x_map.items():
                    _add_text(msp,'KO_R',new_y,cx,val,ref)

    # 5. KOORDİNAT TABLOSU GÜNCELLEMESİ
    # Alt tablo KO_R nokta adları (X=490231.24): A1,A2,A3,A4,A5
    ALT_KOR_ROWS=[4633593.93,4633590.74,4633587.56,4633584.37,4633581.19]
    # Alt tablo KO_M nokta adları (X=490231.24): 340/2,340/3,...
    ALT_KOM_ROWS=[4633578.01,4633574.82,4633571.64,4633568.46,4633565.27,4633562.09,4633558.90]
    # Üst tablo KO_R nokta adları (X=490743.20): A1-A5 (not shown in output but similar)
    UST_KOM_ROWS=[4633743.18,4633740.00,4633736.82,4633733.63,4633730.45,4633727.26,4633724.08]

    # KOR_Y sütun X değerleri
    ALT_Y_X=490250.65; ALT_X_X=490269.65; ALT_MK_X=490288.09
    UST_Y_X=490762.61; UST_X_X=490781.61; UST_MK_X=490800.06

    all_nokta_rows=ALT_KOR_ROWS+ALT_KOM_ROWS  # 12 slot, ilk 5 KO_R, son 7 KO_M

    for i,(row_y,layer,label_x) in enumerate(
        [(y,'KO_R',490231.24) for y in ALT_KOR_ROWS] +
        [(y,'KO_M',490231.24) for y in ALT_KOM_ROWS]
    ):
        if i<len(KOOR):
            pt=KOOR[i]
            # Nokta adı
            _set(msp,layer,row_y,label_x, pt['no'])
            # Koordinatlar (KO_R layer)
            _set(msp,'KO_R',row_y,ALT_Y_X, pt['y'],0.5)
            _set(msp,'KO_R',row_y,ALT_X_X, pt['x'],0.5)
            _set(msp,'KO_R',row_y,ALT_MK_X,pt.get('mk','0.09'),0.5)
            _set(msp,'KO_M',row_y,ALT_MK_X,pt.get('mk','0.09'),0.5)
        else:
            _set(msp,layer,row_y,label_x,'')
            for cx in [ALT_Y_X,ALT_X_X,ALT_MK_X]:
                _set(msp,'KO_R',row_y,cx,'',0.5)

    # Üst tablo KO_M güncellemesi (A1-A5 = 5 slot sonrası devam)
    UST_KOR_A_OFFSET = 5  # len(UST_KOR_A_ROWS)
    for i,row_y in enumerate(UST_KOM_ROWS):
        ki = i + UST_KOR_A_OFFSET  # 340/2→nokta6, 340/3→nokta7 ...
        if ki<len(KOOR):
            pt=KOOR[ki]
            _set(msp,'KO_M',row_y,490743.20, pt['no'])
            _set(msp,'KO_R',row_y,UST_Y_X,  pt['y'],0.5)
            _set(msp,'KO_R',row_y,UST_X_X,  pt['x'],0.5)
            _set(msp,'KO_R',row_y,UST_MK_X, pt.get('mk','0.09'),0.5)
        else:
            _set(msp,'KO_M',row_y,490743.20,'')
            for cx in [UST_Y_X,UST_X_X,UST_MK_X]:
                _set(msp,'KO_R',row_y,cx,'',0.5)

    # KO_R'daki A1-A5 etiketleri güncelle (üst tablo X=490743.20)
    UST_KOR_A_ROWS=[4633759.10,4633755.92,4633752.74,4633749.55,4633746.37]
    for i,row_y in enumerate(UST_KOR_A_ROWS):
        if i<len(KOOR):
            pt=KOOR[i]
            _set(msp,'KO_R',row_y,490743.20, pt['no'],0.5)
            _set(msp,'KO_R',row_y,UST_Y_X,  pt['y'],0.5)
            _set(msp,'KO_R',row_y,UST_X_X,  pt['x'],0.5)
            _set(msp,'KO_R',row_y,UST_MK_X, pt.get('mk','0.09'),0.5)
        else:
            _set(msp,'KO_R',row_y,490743.20,'',0.5)

    # 5a. Alan tablosu dikey çizgilerini ekle/düzelt
    ALT_D_BOT = 4633570.59 + (4633570.59-4633576.87)  # ≈4633563.97 (D alt)
    UST_D_BOT = 4633735.77 + (4633735.77-4633742.05)  # ≈4633729.49 (D alt üst)
    ALT_HDR = 4633597.47  # Alt tablo header altı
    UST_HDR = 4633762.65  # Üst tablo header altı

    # Mevcut dikey çizgileri sil - SADECE alan tablosu bölgesi
    # (Koordinat tablosu çizgileri: alt X<490296, üst X<490808 - dokunma)
    ALT_ALAN_X_MIN = 490296.0  # Alan tablosu sol sınırı (koordinat tablo sağ sınırı)
    UST_ALAN_X_MIN = 490808.0
    to_del_v=[]
    for e in msp:
        if e.dxftype()=='LINE' and e.dxf.layer=='KO_C':
            sx,sy=float(e.dxf.start.x),float(e.dxf.start.y)
            ex,ey=float(e.dxf.end.x),float(e.dxf.end.y)
            if abs(sx-ex)<0.1 and abs(sy-ey)>3:  # dikey
                # Sadece alan tablosu bölgesi
                if ALT_ALAN_X_MIN<=sx<=490420 or UST_ALAN_X_MIN<=sx<=490925:
                    to_del_v.append(e)
    for e in to_del_v: msp.delete_entity(e)

    # Yeni dikey çizgiler - header altından D alt sınırına kadar
    bot_alt = ALT_D_BOT if n>=4 else 4633569.55
    bot_ust = UST_D_BOT if n>=4 else 4633734.72
    for vx in [490296.26,490302.36,490314.17,490350.77,490366.24,490380.74,490389.76,490407.13]:
        msp.add_line((vx,ALT_HDR,0),(vx,bot_alt,0),dxfattribs={'layer':'KO_C','color':256})
    for vx in [490808.23,490814.33,490826.14,490862.74,490878.20,490892.71,490901.72,490919.10]:
        msp.add_line((vx,UST_HDR,0),(vx,bot_ust,0),dxfattribs={'layer':'KO_C','color':256})

    # 5b. (D) satırı alt yatay çizgi
    if n>=4:
        msp.add_line((490296.26,ALT_D_BOT,0),(490407.13,ALT_D_BOT,0),
                     dxfattribs={'layer':'KO_C','color':3})
        msp.add_line((490808.23,UST_D_BOT,0),(490919.10,UST_D_BOT,0),
                     dxfattribs={'layer':'KO_C','color':3})

    # 5c. Boş koordinat satırlarının MK değerlerini temizle (0.09 kalıntıları)
    # ALT: KO_M MK sütunu X=490288.09
    all_alt_rows = ALT_KOR_ROWS + ALT_KOM_ROWS
    for i,row_y in enumerate(all_alt_rows):
        if i >= len(KOOR):
            _set(msp,'KO_M',row_y,490288.09,'',0.5)
            _set(msp,'KO_R',row_y,490288.09,'',0.5)
    # UST: KO_M MK sütunu X=490800.06
    all_ust_rows = UST_KOR_A_ROWS + UST_KOM_ROWS
    for i,row_y in enumerate(all_ust_rows):
        if i >= len(KOOR):
            _set(msp,'KO_M',row_y,490800.06,'',0.5)
            _set(msp,'KO_R',row_y,490800.06,'',0.5)

    # 5c. Boş koordinat satırlarının MK değerlerini temizle
    all_alt_rows_all = ALT_KOR_ROWS + ALT_KOM_ROWS
    for i,row_y in enumerate(all_alt_rows_all):
        if i >= len(KOOR):
            _set(msp,'KO_M',row_y,490288.09,'',0.5)
            _set(msp,'KO_R',row_y,490288.09,'',0.5)
    all_ust_rows_all = UST_KOR_A_ROWS + UST_KOM_ROWS
    for i,row_y in enumerate(all_ust_rows_all):
        if i >= len(KOOR):
            _set(msp,'KO_M',row_y,490800.06,'',0.5)
            _set(msp,'KO_R',row_y,490800.06,'',0.5)

    # 6. KO_M beyaz
    layer=doc.layers.get('KO_M')
    if layer: layer.color=7

    # 7. SABLON_YAZI ada/parsel (340/22 → 100/1)
    for e in msp:
        if e.dxftype()=='TEXT' and e.dxf.layer=='SABLON_YAZI':
            if '/' in e.dxf.text and any(c.isdigit() for c in e.dxf.text) and len(e.dxf.text)<10:
                e.dxf.text=f"{ADA}/{PARSEL}"

    return _save(doc)
