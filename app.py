"""
Photo Verifier - Fotoğraf Doğrulama Sistemi
============================================
Saha ziyaret fotoğraflarının görüntülenmesi ve doğrulanması.
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file
from datetime import datetime, timedelta
import os

from config import PROJECTS, get_project_config
from sources import get_source

app = Flask(__name__)
app.secret_key = 'photo-verifier-secret-key-2024'


@app.route('/')
def index():
    """Ana sayfa - ilk projeye yönlendir."""
    return redirect(url_for('dashboard', project='adco'))


@app.route('/<project>')
def dashboard(project):
    """Proje dashboard'u."""
    if project not in PROJECTS:
        return "Proje bulunamadı", 404
    
    config = get_project_config(project)
    source = get_source(project)
    
    # Son 7 günün istatistikleri
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    
    try:
        stats = source.get_stats(start_date, end_date)
    except Exception as e:
        stats = {'error': str(e)}
    
    return render_template('dashboard.html',
                         project=project,
                         project_name=config['name'],
                         projects=PROJECTS,
                         stats=stats)


@app.route('/<project>/photos')
def photos(project):
    """Fotoğraf listesi - gruplandırılmış."""
    if project not in PROJECTS:
        return "Proje bulunamadı", 404
    
    config = get_project_config(project)
    source = get_source(project)
    
    # Filtreler
    photo_type = request.args.get('type', 'exhibition')
    date_from = request.args.get('from', (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'))
    date_to = request.args.get('to', datetime.now().strftime('%Y-%m-%d'))
    user_id = request.args.get('user_id', type=int)
    customer_code = request.args.get('customer_code')
    
    # Personel ve mağaza listeleri (filtre seçenekleri için)
    try:
        personnel_list = source.get_personnel_list(date_from, date_to)
        customer_list = source.get_customer_list(date_from, date_to)
    except Exception as e:
        print(f"Liste hatası: {e}")
        personnel_list = []
        customer_list = []
    
    # Fotoğrafları getir (ziyarete göre gruplu)
    try:
        photos_grouped = source.get_photos_grouped(photo_type, date_from, date_to, user_id, customer_code)
    except Exception as e:
        photos_grouped = []
        print(f"Hata: {e}")
    
    return render_template('photos.html',
                         project=project,
                         project_name=config['name'],
                         projects=PROJECTS,
                         photo_type=photo_type,
                         photo_types=config.get('photo_tables', []),
                         photos_grouped=photos_grouped,
                         date_from=date_from,
                         date_to=date_to,
                         user_id=user_id,
                         customer_code=customer_code,
                         personnel_list=personnel_list,
                         customer_list=customer_list)


@app.route('/<project>/visit/<int:visit_id>')
def visit_detail(project, visit_id):
    """Tek bir ziyaretin tüm fotoğrafları."""
    if project not in PROJECTS:
        return "Proje bulunamadı", 404
    
    config = get_project_config(project)
    source = get_source(project)
    
    try:
        visit_data = source.get_visit_photos(visit_id)
    except Exception as e:
        visit_data = {'error': str(e)}
    
    return render_template('visit_detail.html',
                         project=project,
                         project_name=config['name'],
                         projects=PROJECTS,
                         visit=visit_data)


@app.route('/<project>/duplicates')
def duplicates(project):
    """Duplicate fotoğraflar sayfası."""
    if project not in PROJECTS:
        return "Proje bulunamadı", 404
    
    config = get_project_config(project)
    source = get_source(project)
    
    # Önce cache'den dene (hızlı), yoksa canlı hesapla
    if source.has_duplicate_cache():
        duplicate_groups = source.get_duplicates_from_cache()
        from_cache = True
    else:
        duplicate_groups = source.find_duplicates()
        from_cache = False
    
    return render_template('duplicates.html',
                         project=project,
                         project_name=config['name'],
                         projects=PROJECTS,
                         duplicate_groups=duplicate_groups,
                         from_cache=from_cache)


@app.route('/<project>/reports')
def reports(project):
    """Raporlar sayfası."""
    if project not in PROJECTS:
        return "Proje bulunamadı", 404
    
    config = get_project_config(project)
    
    return render_template('reports.html',
                         project=project,
                         project_name=config['name'],
                         projects=PROJECTS)


# ==================== API ENDPOINTS ====================

@app.route('/api/<project>/verify', methods=['POST'])
def api_verify(project):
    """Fotoğraf doğrulama API'si."""
    if project not in PROJECTS:
        return jsonify({'error': 'Proje bulunamadı'}), 404
    
    source = get_source(project)
    data = request.json
    
    try:
        result = source.verify_photo(
            photo_id=data['photo_id'],
            photo_type=data['photo_type'],
            status=data['status'],
            note=data.get('note', ''),
            verified_by=data.get('verified_by', 'anonymous')
        )
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/<project>/stats')
def api_stats(project):
    """İstatistik API'si."""
    if project not in PROJECTS:
        return jsonify({'error': 'Proje bulunamadı'}), 404
    
    source = get_source(project)
    
    days = int(request.args.get('days', 7))
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    try:
        stats = source.get_stats(start_date, end_date)
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/image/<project>/<path:image_path>')
def serve_image(project, image_path):
    """Fotoğrafları serve et."""
    if project not in PROJECTS:
        return "Proje bulunamadı", 404
    
    config = get_project_config(project)
    base_path = config['image_path']
    
    full_path = os.path.join(base_path, image_path)
    
    if not os.path.abspath(full_path).startswith(os.path.abspath(base_path)):
        return "Erişim reddedildi", 403
    
    if os.path.exists(full_path):
        return send_file(full_path)
    else:
        return "Dosya bulunamadı", 404


# ==================== TEMPLATE FILTERS ====================

@app.template_filter('datetime')
def format_datetime(value, format='%d.%m.%Y %H:%M'):
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except:
            return value
    return value.strftime(format)


@app.template_filter('date')
def format_date(value, format='%d.%m.%Y'):
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except:
            return value
    return value.strftime(format)


if __name__ == '__main__':
    print("=" * 50)
    print("📸 Photo Verifier - Fotoğraf Doğrulama Sistemi")
    print("=" * 50)
    print("http://localhost:5555")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5555, debug=True)
