"""
Tescil Bildirimi DXF İşleyici
Kadastro Ayırma İşlemi için Otomatik Form Doldurma
"""

import math
import ezdxf
import ezdxf.xref as xref
from io import BytesIO


# ─── Yanılma Sınırı (Madde 8 - Resmi Gazete 27.09.2022) ───────────────────
def yanilma_siniri(alan):
    """Kademeli formülle yanılma sınırı hesapla (m²)."""
    brackets = [
        (0,     10,    0.05),
        (10,    100,   0.02),
        (100,   500,   0.01),
        (500,   1000,  0.005),
        (1000,  5000,  0.004),
        (5000,  25000, 0.003),
        (25000, float('inf'), 0.0015),
    ]
    total = 0.0
    for low, high, rate in brackets:
        if alan <= low:
            break
        total += (min(alan, high) - low) * rate
    return round(total, 2)


# ─── Alan Hesabı (Shoelace) ────────────────────────────────────────────────
def shoelace(pts):
    """Poligon alanı hesapla (m²)."""
    n = len(pts)
    a = 0.0
    for i in range(n):
        j = (i + 1) % n
        a += pts[i][0] * pts[j][1] - pts[j][0] * pts[i][1]
    return abs(a) / 2.0


# ─── Çizim Verisi Çıkar ───────────────────────────────────────────────────
def cizimden_veri_cek(cizim_bytes):
    """
    CIZIM DXF'ten parsel poligonlarını, koordinatları ve
    parsel etiketlerini çıkarır.
    Döndürür: dict
    """
    doc = ezdxf.read(BytesIO(cizim_bytes))
    msp = doc.modelspace()

    # Yeni parsel poligonları
    polygons = []
    for e in msp:
        if e.dxftype() == 'LWPOLYLINE' and e.dxf.layer == 'B_YENİ_PARSEL':
            pts = [(float(p[0]), float(p[1])) for p in e.get_points()]
            polygons.append(pts)

    # Parsel etiketleri (merkez pozisyonlarıyla)
    labels = {}
    for e in msp:
        if e.dxftype() == 'TEXT' and e.dxf.layer == 'B_YENİ_PARSEL_NO':
            ins = e.dxf.insert
            labels[e.dxf.text] = (float(ins.x), float(ins.y))

    # Poligon → etiket eşleştir (en yakın merkez)
    def merkez(pts):
        return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)

    parsel_data = {}
    for pts in polygons:
        cx, cy = merkez(pts)
        best_label, best_d = None, float('inf')
        for label, (lx, ly) in labels.items():
            d = math.sqrt((cx - lx)**2 + (cy - ly)**2)
            if d < best_d:
                best_d, best_label = d, label
        if best_label:
            alan = shoelace(pts)
            parsel_data[best_label] = {
                'alan': alan,
                'm2': int(alan),
                'dm2': round((alan - int(alan)) * 100),
                'pts': pts,
            }

    # Koordinat tablosu (KOR_Y)
    koordinatlar = {}
    for e in msp:
        if e.dxftype() == 'TEXT' and e.dxf.layer == 'KOR_Y':
            ins = e.dxf.insert
            koordinatlar[(round(float(ins.x), 1), round(float(ins.y), 1))] = e.dxf.text

    # KOR_Y satırlarını nokta bazında grupla
    # Her satır: No, Y, X, MK (soldan sağa X sırası)
    kor_rows = {}
    for e in msp:
        if e.dxftype() == 'TEXT' and e.dxf.layer in ('KOR_Y', 'NADI'):
            ins = e.dxf.insert
            row_y = round(float(ins.y), 0)
            col_x = round(float(ins.x), 0)
            if row_y not in kor_rows:
                kor_rows[row_y] = {}
            kor_rows[row_y][col_x] = e.dxf.text

    # Koordinat noktalarını düzenli listeye çevir
    # KOR_Y layer: Y sütunu ~490368, X sütunu ~490378, MK ~490388
    # NADI layer: nokta no
    nokta_listesi = []
    col_groups = {}
    for e in msp:
        if e.dxftype() == 'TEXT' and e.dxf.layer == 'KOR_Y':
            ins = e.dxf.insert
            iy = round(float(ins.y), 1)
            ix = round(float(ins.x), 0)
            if iy not in col_groups:
                col_groups[iy] = {}
            col_groups[iy][ix] = e.dxf.text

    # Nokta adlarını bul (NADI layer)
    nadi_by_row = {}
    for e in msp:
        if e.dxftype() == 'TEXT' and e.dxf.layer == 'NADI':
            ins = e.dxf.insert
            iy = round(float(ins.y), 1)
            nadi_by_row[iy] = e.dxf.text

    # Birleştir - her satır için No, Y, X, MK
    for iy in sorted(col_groups.keys(), reverse=True):
        cols = col_groups[iy]
        sorted_cols = sorted(cols.items())
        no = nadi_by_row.get(iy, '?')
        vals = [v for _, v in sorted_cols]
        if len(vals) >= 3:
            nokta_listesi.append({
                'no': no,
                'y': vals[0],   # easting
                'x': vals[1],   # northing
                'mk': vals[2] if len(vals) > 2 else '0.09',
            })

    # Ada/Parsel bilgisi
    ada_no = '?'
    parsel_no = '?'
    for e in msp:
        if e.dxftype() == 'TEXT':
            if e.dxf.layer == 'B_ADA_NO':
                ada_no = e.dxf.text
            elif e.dxf.layer == 'B_ESKİ_PARSEL_NO':
                parsel_no = e.dxf.text

    return {
        'parseller': parsel_data,
        'koordinatlar': nokta_listesi,
        'ada_no': ada_no,
        'parsel_no': parsel_no,
        'toplam_alan': sum(v['alan'] for v in parsel_data.values()),
    }


# ─── Şablonu Doldur ────────────────────────────────────────────────────────
def tescil_olustur(sablon_bytes, cizim_bytes, form):
    """
    Şablon DXF + çizim DXF + form verisiyle dolu TESCİL_BİLDİRİMİ üretir.
    form: dict — İl, İlçe, Köy, Mevkii, Pafta, Kutuk, Malik, Cinsi,
                  TescilliM2, TescilliDM2, Tarih, No
    Döndürür: bytes (DXF içeriği)
    """
    cizim_veri = cizimden_veri_cek(cizim_bytes)
    doc = ezdxf.read(BytesIO(sablon_bytes))
    msp = doc.modelspace()

    ADA       = cizim_veri['ada_no']
    PARSEL    = cizim_veri['parsel_no']
    PARSELLER = cizim_veri['parseller']
    TOPLAM    = cizim_veri['toplam_alan']
    KOORDINATLAR = cizim_veri['koordinatlar']

    tescilli_alan = f"{form['TescilliM2']}.{form.get('TescilliDM2','00')}"

    # ── 1. Eski çizim katmanlarını kaldır ─────────────────────────────────
    OLD_LAYERS = {
        'PARSEL','PARSEL_NO','NOKTA','KYA','@ROL','ROL_CEPHE',
        'NADI','PASIF_PARSEL','SINIRLAR','@NA','@KO'
    }
    to_del = [e for e in msp if e.dxf.layer in OLD_LAYERS]
    for e in to_del:
        msp.delete_entity(e)

    # ── 2. Çizim katmanlarını içe aktar ───────────────────────────────────
    NEW_DRAW = {
        'B_YENİ_PARSEL','B_YENİ_PARSEL_NO','B_NOKTA','B_BİNA',
        'B_TELÇİT','B_DUVAR','B_SUNDURMA','B_BİNA_TARAMA',
        'B_YOL_DERE','B_ADA_NO','B_ESKİ_PARSEL_NO','B_TERKİN',
        'B_EL_DİREK','POL','B_ESKİ_PARSEL','CEPHE_U','NADI',
    }
    doc_cizim = ezdxf.read(BytesIO(cizim_bytes))
    xref.load_modelspace(
        sdoc=doc_cizim, tdoc=doc,
        filter_fn=lambda e: e.dxf.layer in NEW_DRAW,
        conflict_policy=xref.ConflictPolicy.KEEP,
    )

    # Eski çizimden kalan YOL etiketlerini temizle (çizim sınırı dışı)
    for e in list(msp):
        if e.dxftype()=='TEXT' and e.dxf.layer=='B_YOL_DERE':
            iy = float(e.dxf.insert.y)
            all_y = [float(p[1]) for pdata in PARSELLER.values() for p in pdata['pts']]
            if all_y and (iy < min(all_y)-50 or iy > max(all_y)+50):
                msp.delete_entity(e)

    # ── 3. INPUT katmanını güncelle ───────────────────────────────────────
    sorted_parcels = sorted(PARSELLER.keys())
    n_parcels = len(sorted_parcels)

    # Tablo satırı Y pozisyonları (şablona göre sabit offset)
    FORM_ROW_Y = {
        'eski_parsel': 4633731.40,
    }
    # Yeni parsel satırları - şablon 3 satır içeriyor: A,B,C
    # Satır aralığı: ~8.62
    parsel_row_ys = []
    base_y = 4633722.78
    step   = -(4633722.78 - 4633714.16)
    for i in range(max(n_parcels, 3)):
        parsel_row_ys.append(round(base_y + i * step, 2))

    # INPUT entity'lerini güncelle
    for e in msp:
        if e.dxftype() != 'TEXT' or e.dxf.layer != 'INPUT':
            continue
        ix = float(e.dxf.insert.x)
        iy = float(e.dxf.insert.y)

        # Konum bilgileri
        if abs(ix - 490461.81) < 1 or (abs(ix-490727.53)<1 and abs(iy-4633817.75)<1):
            e.dxf.text = form['Il']
        elif abs(ix-490513.64)<1 or (abs(ix-490727.53)<1 and abs(iy-4633813.50)<1):
            e.dxf.text = form['Ilce']
        elif abs(ix-490565.09)<2 or (abs(ix-490727.53)<1 and abs(iy-4633809.25)<1):
            e.dxf.text = form['Koy']
        elif abs(ix-490618.44)<1:
            e.dxf.text = form['Mevkii']
        elif abs(ix-490727.53)<1 and abs(iy-4633805.00)<1:
            e.dxf.text = f"{ADA}/{PARSEL}"

        # Düşünceler
        elif abs(iy-4633733.88)<1:
            labels_str = ', '.join(sorted_parcels[:-1]) + ' ve ' + sorted_parcels[-1] if n_parcels > 1 else sorted_parcels[0]
            e.dxf.text = f"Ayırma sonucu {labels_str}"
        elif abs(iy-4633730.08)<1:
            e.dxf.text = "parseller oldu."

        # Eski parsel satırı
        elif abs(iy-4633731.40)<1:
            if abs(ix-490589.68)<1:   e.dxf.text = form['Malik']
            elif abs(ix-490555.24)<1: e.dxf.text = form['Cinsi']
            elif abs(ix-490534.67)<1: e.dxf.text = form.get('TescilliDM2','')
            elif abs(ix-490521.81)<1: e.dxf.text = form.get('TescilliM2','')
            elif abs(ix-490513.59)<1: e.dxf.text = '--'
            elif abs(ix-490502.98)<1: e.dxf.text = PARSEL
            elif abs(ix-490486.20)<1: e.dxf.text = ADA
            elif abs(ix-490462.96)<1: e.dxf.text = form['Pafta']
            elif abs(ix-490445.85)<1: e.dxf.text = form['Kutuk']

        # Yeni parsel satırları
        else:
            for i, row_y in enumerate(parsel_row_ys):
                if abs(iy-row_y)<0.5 and i < n_parcels:
                    label = sorted_parcels[i]
                    pdata = PARSELLER[label]
                    if abs(ix-490589.68)<1:   e.dxf.text = form['Malik']
                    elif abs(ix-490555.24)<1: e.dxf.text = form['Cinsi']
                    elif abs(ix-490534.67)<1: e.dxf.text = f"{pdata['dm2']:02d}"
                    elif abs(ix-490521.81)<1: e.dxf.text = str(pdata['m2'])
                    elif abs(ix-490514.30)<1: e.dxf.text = '--'
                    elif abs(ix-490500.46)<2: e.dxf.text = label
                    elif abs(ix-490486.20)<1: e.dxf.text = ADA
                    elif abs(ix-490462.96)<1: e.dxf.text = form['Pafta']
                    break

        # Tarih / No
        if abs(ix-490636.39)<0.3: e.dxf.text = form['Tarih']
        elif abs(ix-490636.81)<0.3: e.dxf.text = form['No']

    # Ekstra parsel satırı gerekiyorsa (>3 parsel) ekle
    c_entities = [e for e in msp if e.dxftype()=='TEXT' and
                  e.dxf.layer=='INPUT' and abs(float(e.dxf.insert.y)-4633705.54)<1]
    for extra_i in range(3, n_parcels):
        label = sorted_parcels[extra_i]
        pdata = PARSELLER[label]
        row_y = parsel_row_ys[extra_i]
        for ref in c_entities:
            rix = float(ref.dxf.insert.x)
            if abs(rix-490589.68)<1:   val = form['Malik']
            elif abs(rix-490555.24)<1: val = form['Cinsi']
            elif abs(rix-490534.67)<1: val = f"{pdata['dm2']:02d}"
            elif abs(rix-490521.81)<1: val = str(pdata['m2'])
            elif abs(rix-490514.30)<1: val = '--'
            elif abs(rix-490500.51)<2: val = label
            elif abs(rix-490486.20)<1: val = ADA
            elif abs(rix-490462.96)<1: val = form['Pafta']
            else: continue
            msp.add_text(val, dxfattribs={
                'layer':'INPUT','insert':(rix,row_y,0),
                'height':ref.dxf.height,'style':ref.dxf.get('style','Standard'),
                'color':ref.dxf.get('color',256),
            })

    # ── 4. KO_R koordinat tablosunu güncelle ─────────────────────────────
    _update_kor(msp, PARSELLER, KOORDINATLAR, ADA, PARSEL, tescilli_alan, sorted_parcels)

    # ── 5. KO_M katman rengi beyaz ────────────────────────────────────────
    layer = doc.layers.get('KO_M')
    if layer:
        layer.color = 7

    # ── 6. Tablo çizgilerini düzelt ───────────────────────────────────────
    _fix_table_borders(msp, n_parcels, sorted_parcels, parsel_row_ys)

    # ── 7. SABLON_YAZI güncelle ───────────────────────────────────────────
    for e in msp:
        if e.dxftype()=='TEXT' and e.dxf.layer=='SABLON_YAZI':
            if e.dxf.text in ('340/22', '100/1', f'{ADA}/{PARSEL}'):
                e.dxf.text = f"{ADA}/{PARSEL}"

    out = BytesIO()
    doc.write(out)
    return out.getvalue()


def _update_kor(msp, parseller, koordinatlar, ada, parsel, tescilli_alan, sorted_parcels):
    """KO_R ve KO_M koordinat/alan tablolarını güncelle."""
    POINTS = {p['no']: p for p in koordinatlar}

    # Noktalar map
    NOKTALAR_MAP = {}
    # Parsel poligon köşe noktalarını belirle (basit: her parsel için kullanılan noktalar)

    # Alan tablosu güncelle - her iki tablo için
    ALT = {
        4633594.15: (parsel, {'noktalar': ','.join(str(p['no']) for p in koordinatlar),
                               'hesap': round(sum(v['alan'] for v in parseller.values()), 2),
                               'tescilli': tescilli_alan}),
    }
    base_y_alt = 4633584.90
    step_alt   = -(4633584.90 - 4633576.87)

    UST = {
        4633759.33: (parsel, {'noktalar': ','.join(str(p['no']) for p in koordinatlar),
                               'hesap': round(sum(v['alan'] for v in parseller.values()), 2),
                               'tescilli': tescilli_alan}),
    }
    base_y_ust = 4633750.08
    step_ust   = -(4633750.08 - 4633742.05)

    for i, label in enumerate(sorted_parcels):
        pdata = parseller[label]
        alan  = round(pdata['alan'], 2)
        pts   = pdata.get('pts', [])
        pt_nos = _find_point_nos(pts, koordinatlar)
        noktalar_str = ','.join(pt_nos)

        ALT[round(base_y_alt + i * step_alt, 2)] = (
            label, {'noktalar': noktalar_str, 'hesap': alan, 'tescilli': ''}
        )
        UST[round(base_y_ust + i * step_ust, 2)] = (
            label, {'noktalar': noktalar_str, 'hesap': alan, 'tescilli': ''}
        )

    # KO_R'u güncelle
    YS_X_ALT = 490393.97; YS_X_UST = 490905.94
    NOKTALAR_X_ALT = 490315.19; NOKTALAR_X_UST = 490827.16
    TESCILLI_X_ALT = 490355.11; TESCILLI_X_UST = 490867.08
    HESAP_X_ALT = 490369.77;   HESAP_X_UST = 490881.74
    FARK_X_ALT  = 490382.30;   FARK_X_UST  = 490894.27
    ADA_X_ALT   = 490297.00;   ADA_X_UST   = 490808.96
    PARSEL_X_ALT= 490305.28;   PARSEL_X_UST= 490817.02

    for e in msp:
        if e.dxftype()!='TEXT' or e.dxf.layer!='KO_R':
            continue
        iy = round(float(e.dxf.insert.y), 2)
        ix = float(e.dxf.insert.x)

        for rows, ys_x, nok_x, tesc_x, hesap_x, fark_x, ada_x, parsel_x in [
            (ALT, YS_X_ALT, NOKTALAR_X_ALT, TESCILLI_X_ALT, HESAP_X_ALT, FARK_X_ALT, ADA_X_ALT, PARSEL_X_ALT),
            (UST, YS_X_UST, NOKTALAR_X_UST, TESCILLI_X_UST, HESAP_X_UST, FARK_X_UST, ADA_X_UST, PARSEL_X_UST),
        ]:
            for row_y, (p_label, pinfo) in rows.items():
                if abs(iy - row_y) > 0.5:
                    continue
                alan_val = pinfo['hesap']
                if abs(ix - nok_x)   < 1: e.dxf.text = pinfo['noktalar']
                elif abs(ix - tesc_x)< 2: e.dxf.text = str(pinfo['tescilli'])
                elif abs(ix - hesap_x)< 2: e.dxf.text = f"{alan_val:.2f}"
                elif abs(ix - fark_x) < 1: e.dxf.text = '0.00'
                elif abs(ix - ys_x)   < 3: e.dxf.text = str(yanilma_siniri(alan_val) if alan_val else '')
                elif abs(ix - ada_x)  < 1: e.dxf.text = ada
                elif abs(ix - parsel_x)<2: e.dxf.text = str(p_label)

    # Koordinat tablosunu güncelle
    _update_koordinat_tablosu(msp, koordinatlar)


def _find_point_nos(pts, koordinatlar):
    """Poligon köşelerini koordinat listesindeki nokta numaralarıyla eşleştir."""
    nos = []
    for px, py in pts:
        best_no, best_d = '?', float('inf')
        for k in koordinatlar:
            try:
                ky = float(k['y']); kx = float(k['x'])
                d = math.sqrt((px-ky)**2 + (py-kx)**2)
                if d < best_d:
                    best_d, best_no = d, k['no']
            except Exception:
                pass
        if best_d < 1.0:
            nos.append(str(best_no))
    return nos


def _update_koordinat_tablosu(msp, koordinatlar):
    """Koordinat tablosundaki A1-A5 / 340/x satırlarını yeni noktalarla güncelle."""
    # Üst tablo: Y sütunu X≈490762.61, X sütunu X≈490781.61
    # Alt tablo: Y sütunu X≈490250.65, X sütunu X≈490269.65
    tables = [
        {'label_x':490743.20,'y_x':490762.61,'x_x':490781.61,'mk_x':490800.06},
        {'label_x':490231.24,'y_x':490250.65,'x_x':490269.65,'mk_x':490288.09},
    ]
    # Mevcut satır Y konumları
    for tbl in tables:
        rows_in_tbl = []
        for e in msp:
            if e.dxftype()=='TEXT' and e.dxf.layer in ('KO_R','KO_M'):
                ix = float(e.dxf.insert.x)
                iy = float(e.dxf.insert.y)
                if abs(ix - tbl['label_x']) < 1:
                    rows_in_tbl.append((iy, e))
        rows_in_tbl.sort(key=lambda r: -r[0])

        for i, (row_y, label_e) in enumerate(rows_in_tbl):
            if i < len(koordinatlar):
                pt = koordinatlar[i]
                label_e.dxf.text = str(pt['no'])
                # Y ve X değerlerini güncelle
                for e in msp:
                    if e.dxftype()=='TEXT' and e.dxf.layer=='KO_R':
                        ex = float(e.dxf.insert.x)
                        ey = float(e.dxf.insert.y)
                        if abs(ey-row_y)<0.5:
                            if abs(ex-tbl['y_x'])<1:  e.dxf.text = pt['y']
                            elif abs(ex-tbl['x_x'])<1: e.dxf.text = pt['x']
                            elif abs(ex-tbl['mk_x'])<1: e.dxf.text = pt.get('mk','0.09')
            else:
                label_e.dxf.text = ''
                for e in msp:
                    if e.dxftype()=='TEXT' and e.dxf.layer=='KO_R':
                        ex = float(e.dxf.insert.x)
                        ey = float(e.dxf.insert.y)
                        if abs(ey-row_y)<0.5 and abs(ex-tbl['label_x'])>1:
                            e.dxf.text = ''


def _fix_table_borders(msp, n_parcels, sorted_parcels, parsel_row_ys):
    """Alan tablosu çizgilerini düzelt: D+ satırı için çizgi ekle."""
    # Alt tablo sabit değerler
    ALT = {'top':4633597.47,'bot':4633564.57,'xl':490296.26,'xr':490407.13}
    UST = {'top':4633762.65,'bot':4633729.73,'xl':490808.23,'xr':490919.10}

    # Mevcut dikey çizgileri temizle ve yeniden ekle (header altından)
    to_del = []
    for e in msp:
        if e.dxftype()=='LINE' and e.dxf.layer=='KO_C':
            sx,sy=float(e.dxf.start.x),float(e.dxf.start.y)
            ex,ey=float(e.dxf.end.x),float(e.dxf.end.y)
            is_vert = abs(sx-ex)<0.1 and abs(sy-ey)>3
            if is_vert:
                bot=min(sy,ey); top=max(sy,ey)
                if ALT['xl']-5 < sx < ALT['xr']+5 and abs(bot-ALT['bot'])<2:
                    to_del.append(e)
                elif UST['xl']-5 < sx < UST['xr']+5 and abs(bot-UST['bot'])<2:
                    to_del.append(e)
    for e in to_del:
        msp.delete_entity(e)

    for cfg, vert_xs in [
        (ALT, [490296.26,490302.36,490314.17,490350.77,490366.24,490380.74,490389.76,490407.13]),
        (UST, [490808.23,490814.33,490826.14,490862.74,490878.20,490892.71,490901.72,490919.10]),
    ]:
        for vx in vert_xs:
            msp.add_line((vx,cfg['top'],0),(vx,cfg['bot'],0),dxfattribs={'layer':'KO_C','color':256})

    # Koordinat tablosu sağ kenarlık
    for ref_x, top_y, bot_y in [(490294.60,4633609.63,4633557.31),
                                  (490806.57,4633774.81,4633722.49)]:
        has = any(
            e.dxftype()=='LINE' and e.dxf.layer=='KO_C' and
            abs(float(e.dxf.start.x)-ref_x)<0.5 and
            abs(float(e.dxf.end.x)-ref_x)<0.5 and
            abs(float(e.dxf.start.y)-float(e.dxf.end.y))>5
            for e in msp
        )
        if not has:
            msp.add_line((ref_x,top_y,0),(ref_x,bot_y,0),dxfattribs={'layer':'KO_C','color':256})
