"""
Photo Verifier - Fotoğraf Doğrulama Sistemi
============================================
Saha ziyaret fotoğraflarının görüntülenmesi ve doğrulanması.
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file, session
from datetime import datetime, timedelta
from functools import wraps
import os
import hashlib
import pymssql

from config import PROJECTS, get_project_config
from sources import get_source

app = Flask(__name__)
app.secret_key = 'photo-verifier-secret-key-2025'  # Production'da değiştir

def get_pv_connection():
    """PhotoVerifier veritabanı bağlantısı."""
    from config import PHOTOVERIFIER_DB
    return pymssql.connect(
        server=PHOTOVERIFIER_DB['host'],
        port=PHOTOVERIFIER_DB.get('port', 1433),
        user=PHOTOVERIFIER_DB['username'],
        password=PHOTOVERIFIER_DB['password'],
        database=PHOTOVERIFIER_DB['database']
    )

def login_required(f):
    """Login gerektiren sayfalar için decorator."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    """Oturum açmış kullanıcıyı getirir."""
    if 'user_id' in session:
        return {
            'id': session['user_id'],
            'username': session.get('username'),
            'display_name': session.get('display_name'),
            'role': session.get('role')
        }
    return None

def hash_password(password: str) -> str:
    """Şifreyi hashler."""
    return hashlib.sha256(password.encode()).hexdigest()

def log_event(action: str, project: str = None, details: str = None):
    """Aktivite loglar."""
    try:
        user = get_current_user()
        conn = get_pv_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO EventLogs (UserId, Username, Action, Project, Details, IpAddress)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (
            user['id'] if user else None,
            user['username'] if user else None,
            action,
            project,
            details,
            request.remote_addr
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Log error: {e}")

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Kullanıcı girişi."""
    error = None
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        try:
            conn = get_pv_connection()
            cursor = conn.cursor(as_dict=True)
            cursor.execute('''
                SELECT Id, Username, PasswordHash, DisplayName, Role, IsActive
                FROM Users
                WHERE Username = %s
            ''', (username,))
            user = cursor.fetchone()
            conn.close()
            
            if user and user['IsActive']:
                if user['PasswordHash'] == hash_password(password):
                    session['user_id'] = user['Id']
                    session['username'] = user['Username']
                    session['display_name'] = user['DisplayName'] or user['Username']
                    session['role'] = user['Role']
                    
                    # Login logla
                    log_event('Login', details=f"Başarılı giriş")
                    
                    # LastLoginAt güncelle
                    conn = get_pv_connection()
                    cursor = conn.cursor()
                    cursor.execute('UPDATE Users SET LastLoginAt = GETDATE() WHERE Id = %s', (user['Id'],))
                    conn.commit()
                    conn.close()
                    
                    return redirect(url_for('index'))
                else:
                    error = 'Hatalı şifre'
                    log_event('LoginFailed', details=f"Hatalı şifre: {username}")
            elif user and not user['IsActive']:
                error = 'Hesap devre dışı'
            else:
                error = 'Kullanıcı bulunamadı'
        except Exception as e:
            error = f'Sistem hatası: {str(e)}'
            print(f"Login error: {e}")
    
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    """Kullanıcı çıkışı."""
    if 'user_id' in session:
        log_event('Logout')
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    """Ana sayfa - ilk projeye yönlendir."""
    return redirect(url_for('dashboard', project='adco'))


@app.route('/<project>')
@login_required
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
                         stats=stats,
                         current_user=get_current_user())


@app.route('/<project>/photos')
@login_required
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
                         customer_list=customer_list,
                            current_user=get_current_user())
                        
                    


@app.route('/<project>/visit/<int:visit_id>')
@login_required
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
                         visit=visit_data,
                            current_user=get_current_user())

@app.route('/<project>/duplicates')
@login_required
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
                         from_cache=from_cache,
                            current_user=get_current_user())


@app.route('/<project>/reports')
@login_required
def reports(project):
    """Raporlar sayfası."""
    if project not in PROJECTS:
        return "Proje bulunamadı", 404
    
    config = get_project_config(project)
    
    return render_template('reports.html',
                         project=project,
                         project_name=config['name'],
                         projects=PROJECTS,
                            current_user=get_current_user())


# ==================== API ENDPOINTS ====================

@app.route('/api/<project>/verify', methods=['POST'])
@login_required
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
@login_required
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
@login_required
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
@login_required
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
@login_required
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
    

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """Profil ve şifre değiştirme."""
    message = None
    error = None
    
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not all([current_password, new_password, confirm_password]):
            error = 'Tüm alanları doldurun'
        elif new_password != confirm_password:
            error = 'Yeni şifreler eşleşmiyor'
        elif len(new_password) < 6:
            error = 'Şifre en az 6 karakter olmalı'
        else:
            try:
                conn = get_pv_connection()
                cursor = conn.cursor(as_dict=True)
                cursor.execute('SELECT PasswordHash FROM Users WHERE Id = %s', (session['user_id'],))
                user = cursor.fetchone()
                
                if user and user['PasswordHash'] == hash_password(current_password):
                    cursor.execute('UPDATE Users SET PasswordHash = %s WHERE Id = %s', 
                                 (hash_password(new_password), session['user_id']))
                    conn.commit()
                    message = 'Şifre başarıyla güncellendi'
                    log_event('PasswordChange', details='Şifre değiştirildi')
                else:
                    error = 'Mevcut şifre hatalı'
                conn.close()
            except Exception as e:
                error = f'Sistem hatası: {str(e)}'
    
    return render_template('profile.html', 
                         message=message, 
                         error=error,
                         current_user=get_current_user(),
                         projects=PROJECTS)    
