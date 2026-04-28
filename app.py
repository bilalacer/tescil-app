import os, traceback
from flask import Flask, request, send_file, jsonify, render_template
from io import BytesIO

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/olustur', methods=['POST'])
def olustur():
    try:
        if 'cizim' not in request.files or 'sablon' not in request.files:
            return jsonify({'hata': 'Her iki DXF dosyası da yüklenmelidir.'}), 400
        cizim_file  = request.files['cizim']
        sablon_file = request.files['sablon']
        if not cizim_file.filename.lower().endswith('.dxf') or not sablon_file.filename.lower().endswith('.dxf'):
            return jsonify({'hata': 'Sadece .dxf dosyaları kabul edilir.'}), 400
        cizim_bytes  = cizim_file.read()
        sablon_bytes = sablon_file.read()
        form = {
            'Il':          request.form.get('il','').upper(),
            'Ilce':        request.form.get('ilce','').upper(),
            'Koy':         request.form.get('koy','').upper(),
            'Mevkii':      request.form.get('mevkii','').upper(),
            'Pafta':       request.form.get('pafta','').upper(),
            'Kutuk':       request.form.get('kutuk',''),
            'Malik':       request.form.get('malik','').upper(),
            'Cinsi':       request.form.get('cinsi','').upper(),
            'TescilliM2':  request.form.get('tescilli_m2',''),
            'TescilliDM2': request.form.get('tescilli_dm2','00'),
            'Tarih':       request.form.get('tarih',''),
            'No':          request.form.get('no',''),
        }
        from dxf_processor import tescil_olustur
        dxf_bytes = tescil_olustur(sablon_bytes, cizim_bytes, form)
        return send_file(
            BytesIO(dxf_bytes),
            as_attachment=True,
            download_name='TESCİL_BİLDİRİMİ.dxf',
            mimetype='application/octet-stream',
        )
    except Exception:
        return jsonify({'hata': traceback.format_exc()}), 500


@app.route('/onizle', methods=['POST'])
def onizle():
    try:
        if 'cizim' not in request.files:
            return jsonify({'hata': 'Çizim dosyası eksik.'}), 400
        from dxf_processor import cizimden_veri_cek, yanilma_siniri
        cizim_bytes = request.files['cizim'].read()
        veri = cizimden_veri_cek(cizim_bytes)
        for label, pdata in veri['parseller'].items():
            pdata['ys'] = yanilma_siniri(pdata['alan'])
        return jsonify(veri)
    except Exception:
        return jsonify({'hata': traceback.format_exc()}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
