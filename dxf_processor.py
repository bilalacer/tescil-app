"""
Tescil Bildirimi DXF İşleyici - v3
Pozisyon bağımsız, içerik tabanlı güncelleme
"""
import math, tempfile, os
import ezdxf
import ezdxf.xref as xref


def yanilma_siniri(alan):
    brackets = [(0,10,0.05),(10,100,0.02),(100,500,0.01),(500,1000,0.005),
                (1000,5000,0.004),(5000,25000,0.003),(25000,float('inf'),0.0015)]
    total = 0.0
    for low, high, rate in brackets:
        if alan <= low: break
        total += (min(alan, high) - low) * rate
    return round(total, 2)


def shoelace(pts):
    n = len(pts); a = 0.0
    for i in range(n):
        j = (i+1)%n
        a += pts[i][0]*pts[j][1] - pts[j][0]*pts[i][1]
    return abs(a)/2.0


def _readfile(data_bytes):
    with tempfile.NamedTemporaryFile(suffix='.dxf', delete=False) as t:
        t.write(data_bytes); p = t.name
    doc = ezdxf.readfile(p)
    os.unlink(p)
    return doc


def _savefile(doc):
    with tempfile.NamedTemporaryFile(suffix='.dxf', delete=False) as t:
        p = t.name
    doc.saveas(p)
    with open(p,'rb') as f: data = f.read()
    os.unlink(p)
    return data


def cizimden_veri_cek(cizim_bytes):
    doc = _readfile(cizim_bytes)
    msp = doc.modelspace()

    # Parsel poligonları
    polygons = []
    for e in msp:
        if e.dxftype()=='LWPOLYLINE' and 'YENİ_PARSEL' in e.dxf.layer and 'NO' not in e.dxf.layer:
            pts = [(float(p[0]),float(p[1])) for p in e.get_points()]
            if len(pts) >= 3:
                polygons.append(pts)

    # Parsel etiketleri
    labels = {}
    for e in msp:
        if e.dxftype()=='TEXT' and 'YENİ_PARSEL_NO' in e.dxf.layer:
            ins = e.dxf.insert
            labels[e.dxf.text] = (float(ins.x), float(ins.y))

    def merkez(pts):
        return sum(p[0] for p in pts)/len(pts), sum(p[1] for p in pts)/len(pts)

    parsel_data = {}
    for pts in polygons:
        cx,cy = merkez(pts)
        best_label,best_d = None,float('inf')
        for label,(lx,ly) in labels.items():
            d = math.sqrt((cx-lx)**2+(cy-ly)**2)
            if d < best_d:
                best_d,best_label = d,label
        if best_label:
            alan = shoelace(pts)
            parsel_data[best_label] = {
                'alan':alan,'m2':int(alan),
                'dm2':round((alan-int(alan))*100),'pts':pts
            }

    # Koordinat noktaları - KOR_Y ve NADI katmanları
    # KOR_Y: Y ve X değerleri, NADI: nokta adları
    # Satırları Y pozisyonuna göre grupla
    kor_rows = {}  # row_y -> {col_x: text}
    for e in msp:
        if e.dxftype()=='TEXT' and e.dxf.layer in ('KOR_Y','NADI','KOR_MK'):
            iy = round(float(e.dxf.insert.y),1)
            ix = round(float(e.dxf.insert.x),1)
            if iy not in kor_rows: kor_rows[iy] = {}
            kor_rows[iy][ix] = (e.dxf.text, e.dxf.layer)

    # Nokta numarasını NADI katmanından al, koordinatları KOR_Y'dan
    nokta_listesi = []
    for row_y in sorted(kor_rows.keys(), reverse=True):
        cols = kor_rows[row_y]
        nadi_vals = [v for v,l in cols.values() if l=='NADI']
        kor_vals  = sorted([(x,v) for x,(v,l) in cols.items() if l=='KOR_Y'], key=lambda t:t[0])
        mk_vals   = [v for v,l in cols.values() if l=='KOR_MK']
        if nadi_vals and len(kor_vals)>=2:
            nokta_listesi.append({
                'no': nadi_vals[0],
                'y':  kor_vals[0][1],
                'x':  kor_vals[1][1],
                'mk': mk_vals[0] if mk_vals else '0.09',
            })

    # Ada/parsel
    ada_no='?'; parsel_no='?'
    for e in msp:
        if e.dxftype()=='TEXT':
            if e.dxf.layer=='B_ADA_NO': ada_no=e.dxf.text
            elif e.dxf.layer=='B_ESKİ_PARSEL_NO': parsel_no=e.dxf.text

    return {
        'parseller': parsel_data,
        'koordinatlar': nokta_listesi,
        'ada_no': ada_no,
        'parsel_no': parsel_no,
        'toplam_alan': sum(v['alan'] for v in parsel_data.values()),
    }


def tescil_olustur(sablon_bytes, cizim_bytes, form):
    veri   = cizimden_veri_cek(cizim_bytes)
    doc    = _readfile(sablon_bytes)
    msp    = doc.modelspace()

    ADA        = veri['ada_no']
    PARSEL     = veri['parsel_no']
    PARSELLER  = veri['parseller']
    KOORDINATLAR = veri['koordinatlar']
    sorted_parcels = sorted(PARSELLER.keys())
    n_parcels  = len(sorted_parcels)

    # ── 1. Eski çizim katmanlarını kaldır ─────────────────────────────────
    OLD = {'PARSEL','PARSEL_NO','NOKTA','KYA','@ROL','ROL_CEPHE',
           'PASIF_PARSEL','SINIRLAR','@NA','@KO'}
    for e in [e for e in msp if e.dxf.layer in OLD]:
        msp.delete_entity(e)

    # ── 2. Çizim katmanlarını içe aktar ───────────────────────────────────
    NEW = {'B_YENİ_PARSEL','B_YENİ_PARSEL_NO','B_NOKTA','B_BİNA','B_TELÇİT',
           'B_DUVAR','B_SUNDURMA','B_BİNA_TARAMA','B_YOL_DERE','B_ADA_NO',
           'B_ESKİ_PARSEL_NO','B_TERKİN','B_EL_DİREK','POL','B_ESKİ_PARSEL',
           'CEPHE_U','NADI'}
    doc_c = _readfile(cizim_bytes)
    xref.load_modelspace(sdoc=doc_c, tdoc=doc,
                         filter_fn=lambda e: e.dxf.layer in NEW,
                         conflict_policy=xref.ConflictPolicy.KEEP)

    # Eski YOL etiketleri temizle (çizim bbox dışındaki)
    if PARSELLER:
        all_pts = [p for pd in PARSELLER.values() for p in pd['pts']]
        min_y = min(p[1] for p in all_pts)-100
        max_y = max(p[1] for p in all_pts)+100
        for e in [e for e in msp if e.dxftype()=='TEXT' and e.dxf.layer=='B_YOL_DERE']:
            if float(e.dxf.insert.y)<min_y or float(e.dxf.insert.y)>max_y:
                msp.delete_entity(e)

    # ── 3. INPUT katmanını güncelle (içerik bazlı) ────────────────────────
    toplam = round(sum(v['alan'] for v in PARSELLER.values()),2)
    tescilli_m2 = form.get('TescilliM2','')
    tescilli_dm2 = form.get('TescilliDM2','00')

    # Tüm INPUT entity'lerini topla, X pozisyonuna göre sütun grupla
    input_ents = []
    for e in msp:
        if e.dxftype()=='TEXT' and e.dxf.layer=='INPUT':
            input_ents.append({'e':e,'ix':float(e.dxf.insert.x),'iy':float(e.dxf.insert.y)})

    # Sütunları X'e göre bul (yakın X'leri grupla)
    def find_col(target_ix, tol=3):
        return [i for i in input_ents if abs(i['ix']-target_ix)<tol]

    # X pozisyonlarını analiz et
    all_ix = sorted(set(round(i['ix']) for i in input_ents))

    # Satır Y pozisyonlarını bul (azalan sıra)
    all_iy = sorted(set(round(i['iy'],1) for i in input_ents), reverse=True)

    # INPUT alanlarını Y sırasına göre güncelle
    # Üst bölüm (yüksek Y): İl, İlçe, Köy, Mevkii
    # Orta bölüm: Tablo satırları
    # Alt bölüm (düşük Y): Tarih, No

    # Konum sütunlarını bul (geniş X aralığı = sola yakın = etiket/değer alanları)
    # En soldaki geniş sütun = Malik/Cinsi/Alan değerleri
    # En sağdaki = Tarih/No

    # İL - en üst satırlardan birinde
    # Grupları belirle: üst bilgi (İl,İlçe,Köy,Mevkii), tablo (parsel satırları), alt (Tarih,No)

    # Satır yüksekliklerine göre bölümlere ayır
    if all_iy:
        max_y = all_iy[0]
        min_y = all_iy[-1]
        y_range = max_y - min_y

        # Üst %30 = konum bilgileri
        ust_limit = max_y - y_range*0.15
        # Alt %15 = Tarih/No
        alt_limit = min_y + y_range*0.15

        ust_rows = [y for y in all_iy if y >= ust_limit]
        alt_rows = [y for y in all_iy if y <= alt_limit]
        orta_rows = [y for y in all_iy if alt_limit < y < ust_limit]

        # Üst satırları güncelle: İl, İlçe, Köy, Mevkii (soldan sağa sıralı sütunlar)
        ust_fields = [form['Il'], form['Ilce'], form['Koy'], form['Mevkii']]
        for row_y in ust_rows[:2]:  # ilk 2 satır = üst bilgi
            row_ents = sorted([i for i in input_ents if abs(i['iy']-row_y)<1], key=lambda i:i['ix'])
            for idx,item in enumerate(row_ents):
                if idx < len(ust_fields):
                    item['e'].dxf.text = ust_fields[idx]

        # Alt satırlar: Tarih, No
        if alt_rows:
            alt_ents_all = []
            for row_y in alt_rows:
                alt_ents_all += [i for i in input_ents if abs(i['iy']-row_y)<1]
            alt_ents_all.sort(key=lambda i:i['ix'])
            if len(alt_ents_all)>=1: alt_ents_all[0]['e'].dxf.text = form['Tarih']
            if len(alt_ents_all)>=2: alt_ents_all[1]['e'].dxf.text = form['No']

        # Orta satırlar: tablo satırları (eski + yeni parseller)
        # Satır sayısı: 1 eski + n_parcels yeni
        # Sütun yapısı (soldan sağa): Kütük, Pafta, Ada, Parsel, ha, m², dm², Cinsi, Malik
        orta_rows_sorted = sorted(orta_rows, reverse=True)

        # Her satır için sütunları bul
        def get_row_ents(row_y):
            return sorted([i for i in input_ents if abs(i['iy']-row_y)<1], key=lambda i:i['ix'])

        # Kaç sütun var?
        if orta_rows_sorted:
            sample_row = get_row_ents(orta_rows_sorted[0])
            n_cols = len(sample_row)

            # Sütun ataması: en çok 9 sütun
            # Tipik sıra: [Kütük, Pafta, Ada, Parsel, ha, m², dm², Cinsi, Malik, Düşünceler]
            COL_KUTUK=0; COL_PAFTA=1; COL_ADA=2; COL_PARSEL=3
            COL_HA=4; COL_M2=5; COL_DM2=6; COL_CINSI=7; COL_MALIK=8

            # Tüm tablo satırlarını güncelle
            # İlk satır = eski parsel
            for si, row_y in enumerate(orta_rows_sorted):
                row_ents = get_row_ents(row_y)
                if si == 0:
                    # Eski parsel satırı
                    vals = {
                        COL_KUTUK: form['Kutuk'],
                        COL_PAFTA: form['Pafta'],
                        COL_ADA:   ADA,
                        COL_PARSEL: PARSEL,
                        COL_HA:    '--',
                        COL_M2:    tescilli_m2,
                        COL_DM2:   tescilli_dm2,
                        COL_CINSI: form['Cinsi'],
                        COL_MALIK: form['Malik'],
                    }
                elif 1 <= si <= n_parcels:
                    label = sorted_parcels[si-1]
                    pd    = PARSELLER[label]
                    vals  = {
                        COL_PAFTA:  form['Pafta'],
                        COL_ADA:    ADA,
                        COL_PARSEL: label,
                        COL_HA:     '--',
                        COL_M2:     str(pd['m2']),
                        COL_DM2:    f"{pd['dm2']:02d}",
                        COL_CINSI:  form['Cinsi'],
                        COL_MALIK:  form['Malik'],
                    }
                else:
                    vals = {}
                    for item in row_ents: item['e'].dxf.text = ''

                for ci, item in enumerate(row_ents):
                    if ci in vals:
                        item['e'].dxf.text = vals[ci]

        # Düşünceler
        dusunceler_ents = [i for i in input_ents if
                           alt_limit < i['iy'] < ust_limit and
                           not any(abs(i['iy']-r)<1 for r in orta_rows_sorted)]
        if dusunceler_ents:
            dusunceler_ents.sort(key=lambda i:-i['iy'])
            label_str = ', '.join(sorted_parcels[:-1])+' ve '+sorted_parcels[-1] if n_parcels>1 else sorted_parcels[0]
            if len(dusunceler_ents)>=1: dusunceler_ents[0]['e'].dxf.text=f"Ayırma sonucu {label_str}"
            if len(dusunceler_ents)>=2: dusunceler_ents[1]['e'].dxf.text="parseller oldu."

    # ── 4. KO_R tablosunu güncelle (içerik bazlı) ─────────────────────────
    _update_kor_v2(msp, PARSELLER, KOORDINATLAR, ADA, PARSEL,
                   tescilli_m2, tescilli_dm2, sorted_parcels)

    # ── 5. KO_M beyaz ─────────────────────────────────────────────────────
    layer = doc.layers.get('KO_M')
    if layer: layer.color = 7

    # ── 6. SABLON_YAZI ─────────────────────────────────────────────────────
    for e in msp:
        if e.dxftype()=='TEXT' and e.dxf.layer=='SABLON_YAZI':
            t = e.dxf.text
            if '/' in t and any(c.isdigit() for c in t):
                e.dxf.text = f"{ADA}/{PARSEL}"

    return _savefile(doc)


def _update_kor_v2(msp, parseller, koordinatlar, ada, parsel,
                   tescilli_m2, tescilli_dm2, sorted_parcels):
    """KO_R ve KO_M tablolarını içerik bazlı güncelle."""

    # ── KO_M: koordinat tablosu nokta numaralarını güncelle ───────────────
    ko_m_ents = []
    for e in msp:
        if e.dxftype()=='TEXT' and e.dxf.layer=='KO_M':
            ko_m_ents.append(e)
    ko_m_sorted = sorted(ko_m_ents, key=lambda e:-float(e.dxf.insert.y))

    for i,e in enumerate(ko_m_sorted):
        if i < len(koordinatlar):
            e.dxf.text = str(koordinatlar[i]['no'])
        else:
            e.dxf.text = ''

    # ── KO_R: koordinat değerlerini güncelle ──────────────────────────────
    # Satırları Y'ye göre grupla (KO_R)
    kor_rows = {}
    for e in msp:
        if e.dxftype()=='TEXT' and e.dxf.layer=='KO_R':
            iy = round(float(e.dxf.insert.y),1)
            ix = round(float(e.dxf.insert.x),1)
            if iy not in kor_rows: kor_rows[iy]={}
            kor_rows[iy][ix] = e

    # KO_M ile aynı satır Y'lerini eşleştir
    ko_m_ys = sorted(set(round(float(e.dxf.insert.y),1) for e in ko_m_sorted), reverse=True)

    for i,row_y in enumerate(ko_m_ys):
        # En yakın KO_R satırını bul
        matching_kor_ys = [y for y in kor_rows if abs(y-row_y)<2]
        for kor_y in matching_kor_ys:
            kor_cols = sorted(kor_rows[kor_y].items())  # (ix, entity)
            # Sütunlar: [Y_easting, X_northing, MK] (soldan sağa)
            if i < len(koordinatlar):
                pt = koordinatlar[i]
                if len(kor_cols)>=1: kor_cols[0][1].dxf.text = pt['y']
                if len(kor_cols)>=2: kor_cols[1][1].dxf.text = pt['x']
                if len(kor_cols)>=3: kor_cols[2][1].dxf.text = pt.get('mk','0.09')
            else:
                for _,e in kor_cols: e.dxf.text=''

    # ── Alan tablosunu güncelle ───────────────────────────────────────────
    # Tüm KO_R entity'lerini tara, bilinen eski değerleri yenisiyle değiştir

    # Eski template parsel değerlerini tespit et ve değiştir
    # Ada sütunu: tek basamaklı rakam olmayan ada no → yeni ada
    # Parsel sütunu: eski parsel adları → yeni parsel adları

    toplam = round(sum(v['alan'] for v in parseller.values()),2)
    n_parcels = len(sorted_parcels)

    # Alan tablosu satırlarını tespit et
    # Strateji: KO_R'daki sayısal değer bloklarını bul
    # Her tabloda: başlık satırı + eski parsel + yeni parseller
    # Satırları Y'ye göre grupla, her grupta ada/parsel/noktalar/tescilli/hesap/fark/ys sütunları var

    # Tüm KO_R satırlarını bul (alan tablosu bölgesi = koordinat tablosu dışı)
    # Koordinat tablosu: KO_M ile aynı bölge
    # Alan tablosu: diğer bölge

    # KO_M Y aralığı
    if ko_m_ys:
        kom_min_y = min(ko_m_ys)-5
        kom_max_y = max(ko_m_ys)+5
    else:
        kom_min_y = kom_max_y = 0

    # Alan tablosu satırları: KO_M bölgesi dışındaki KO_R satırları
    alan_rows = {}
    for iy, cols in kor_rows.items():
        if not (kom_min_y <= iy <= kom_max_y):
            alan_rows[iy] = cols

    if not alan_rows:
        # Fallback: tüm KO_R satırları
        alan_rows = kor_rows

    # Alan tablosu satırlarını Y'ye göre sırala (her tablo için)
    # İki tablo olabilir (üst ve alt) - X koordinatına göre ayır
    # Tüm satırları X merkezine göre grupla
    if alan_rows:
        all_xs = []
        for cols in alan_rows.values():
            all_xs.extend(cols.keys())
        if all_xs:
            x_min,x_max = min(all_xs),max(all_xs)
            x_mid = (x_min+x_max)/2

            # İki grup: sol (x<mid) ve sağ (x>mid) - ya da tek grup
            sol_rows = {y:{x:e for x,e in cols.items() if x<x_mid}
                        for y,cols in alan_rows.items() if any(x<x_mid for x in cols)}
            sag_rows = {y:{x:e for x,e in cols.items() if x>=x_mid}
                        for y,cols in alan_rows.items() if any(x>=x_mid for x in cols)}

            for tbl_rows in [sol_rows, sag_rows]:
                if not tbl_rows: continue
                _update_alan_tablosu(tbl_rows, parseller, sorted_parcels,
                                     ada, parsel, toplam,
                                     tescilli_m2, tescilli_dm2)


def _update_alan_tablosu(tbl_rows, parseller, sorted_parcels,
                          ada, parsel_no, toplam,
                          tescilli_m2, tescilli_dm2):
    """Alan tablosu satırlarını güncelle."""
    n = len(sorted_parcels)
    # Satırları Y'ye göre sırala (azalan)
    sorted_rows = sorted(tbl_rows.items(), key=lambda t:-t[0])

    # Her satırda sütunları X'e göre sırala
    for si,(row_y,cols) in enumerate(sorted_rows):
        sorted_cols = sorted(cols.items())  # [(ix, entity), ...]
        nc = len(sorted_cols)
        if nc < 2: continue

        # Sütun ataması (soldan sağa):
        # 0:Ada, 1:Parsel, 2:Noktalar(geniş), -4:Tescilli, -3:Hesap, -2:Fark, -1:YS
        # nc>=7 bekleniyor

        def set_col(idx, val):
            if 0 <= idx < nc:
                sorted_cols[idx][1].dxf.text = str(val)

        def clear_row():
            for _,e in sorted_cols: e.dxf.text = ''

        if si == 0:
            # Eski parsel satırı
            set_col(0, ada)
            set_col(1, parsel_no)
            # Noktalar: tüm nokta numaraları
            set_col(2, ','.join(str(i+1) for i in range(
                sum(len(pd['pts']) for pd in parseller.values())//4 + 4)))
            if tescilli_m2:
                set_col(nc-4, f"{tescilli_m2}.{tescilli_dm2}")
            set_col(nc-3, f"{toplam:.2f}")
            set_col(nc-2, '0.00')
            set_col(nc-1, str(yanilma_siniri(toplam)))

        elif 1 <= si <= n:
            label = sorted_parcels[si-1]
            pd    = parseller[label]
            alan  = round(pd['alan'],2)
            set_col(0, ada)
            set_col(1, label)
            # Noktalar için köşe noktaları (varsayılan)
            set_col(nc-4, '')
            set_col(nc-3, f"{alan:.2f}")
            set_col(nc-2, '0.00')
            set_col(nc-1, str(yanilma_siniri(alan)))

        else:
            clear_row()
