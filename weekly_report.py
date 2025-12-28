"""
Weekly Report - Haftalık Aktivite Raporu
=========================================
Her Pazartesi otomatik çalışır, e-posta gönderir.
"""

import pymssql
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

from config import PROJECTS, PHOTOVERIFIER_DB, EMAIL_CONFIG


def get_pv_connection():
    """PhotoVerifier veritabanı bağlantısı."""
    return pymssql.connect(
        server=PHOTOVERIFIER_DB['host'],
        port=PHOTOVERIFIER_DB.get('port', 1433),
        user=PHOTOVERIFIER_DB['username'],
        password=PHOTOVERIFIER_DB['password'],
        database=PHOTOVERIFIER_DB['database']
    )


def get_weekly_stats():
    """Haftalık istatistikleri toplar."""
    conn = get_pv_connection()
    cursor = conn.cursor(as_dict=True)
    
    # Son 7 gün
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    
    report = {
        'period': f"{start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}",
        'projects': {},
        'users': {},
        'event_summary': {},
    }
    
    # 1. Proje bazlı doğrulama istatistikleri
    for project_key in PROJECTS:
        cursor.execute('''
            SELECT 
                Status,
                COUNT(*) as count
            FROM Verifications
            WHERE Project = %s AND VerifiedAt >= %s
            GROUP BY Status
        ''', (project_key, start_date))
        
        stats = {'approved': 0, 'rejected': 0, 'suspicious': 0, 'total': 0}
        for row in cursor.fetchall():
            stats[row['Status']] = row['count']
            stats['total'] += row['count']
        
        # Toplam duplicate sayısı
        cursor.execute('''
            SELECT COUNT(*) as count FROM DuplicateCache WHERE Project = %s
        ''', (project_key,))
        duplicate_count = cursor.fetchone()['count']
        
        report['projects'][project_key] = {
            'name': PROJECTS[project_key]['name'],
            'verifications': stats,
            'duplicate_groups': duplicate_count,
        }
    
    # 2. Kullanıcı bazlı aksiyonlar
    cursor.execute('''
        SELECT 
            u.DisplayName,
            u.Username,
            COUNT(*) as action_count,
            SUM(CASE WHEN v.Status = 'approved' THEN 1 ELSE 0 END) as approved,
            SUM(CASE WHEN v.Status = 'rejected' THEN 1 ELSE 0 END) as rejected,
            SUM(CASE WHEN v.Status = 'suspicious' THEN 1 ELSE 0 END) as suspicious
        FROM Verifications v
        JOIN Users u ON v.VerifiedBy = u.Id
        WHERE v.VerifiedAt >= %s
        GROUP BY u.DisplayName, u.Username
        ORDER BY action_count DESC
    ''', (start_date,))
    
    for row in cursor.fetchall():
        report['users'][row['DisplayName'] or row['Username']] = {
            'total': row['action_count'],
            'approved': row['approved'],
            'rejected': row['rejected'],
            'suspicious': row['suspicious'],
        }
    
    # 3. Event log özeti
    cursor.execute('''
        SELECT 
            Action,
            COUNT(*) as count
        FROM EventLogs
        WHERE CreatedAt >= %s
        GROUP BY Action
        ORDER BY count DESC
    ''', (start_date,))
    
    for row in cursor.fetchall():
        report['event_summary'][row['Action']] = row['count']
    
    # 4. Toplam login sayısı
    cursor.execute('''
        SELECT COUNT(DISTINCT UserId) as unique_users
        FROM EventLogs
        WHERE Action = 'Login' AND CreatedAt >= %s
    ''', (start_date,))
    report['unique_logins'] = cursor.fetchone()['unique_users']
    
    conn.close()
    return report


def generate_html_report(report):
    """HTML formatında rapor oluşturur."""
    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            h1 {{ color: #2c3e50; }}
            h2 {{ color: #34495e; border-bottom: 2px solid #3498db; padding-bottom: 5px; }}
            table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
            th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
            th {{ background-color: #3498db; color: white; }}
            tr:nth-child(even) {{ background-color: #f9f9f9; }}
            .stat-approved {{ color: #27ae60; font-weight: bold; }}
            .stat-rejected {{ color: #e74c3c; font-weight: bold; }}
            .stat-suspicious {{ color: #f39c12; font-weight: bold; }}
            .summary-box {{ background: #ecf0f1; padding: 15px; border-radius: 8px; margin-bottom: 20px; }}
        </style>
    </head>
    <body>
        <h1>📸 Photo Verifier - Haftalık Rapor</h1>
        <div class="summary-box">
            <strong>📅 Dönem:</strong> {report['period']}<br>
            <strong>👥 Aktif Kullanıcı:</strong> {report['unique_logins']} kişi giriş yaptı
        </div>
        
        <h2>📊 Proje Bazlı Değerlendirme Durumu</h2>
        <table>
            <tr>
                <th>Proje</th>
                <th>✅ Onaylanan</th>
                <th>❌ Reddedilen</th>
                <th>❓ Şüpheli</th>
                <th>📋 Toplam İşlem</th>
                <th>🔍 Duplicate Grup</th>
            </tr>
    """
    
    for project_key, data in report['projects'].items():
        v = data['verifications']
        html += f"""
            <tr>
                <td><strong>{data['name']}</strong></td>
                <td class="stat-approved">{v['approved']}</td>
                <td class="stat-rejected">{v['rejected']}</td>
                <td class="stat-suspicious">{v['suspicious']}</td>
                <td>{v['total']}</td>
                <td>{data['duplicate_groups']}</td>
            </tr>
        """
    
    html += """
        </table>
        
        <h2>👤 Kullanıcı Bazlı Aksiyonlar</h2>
        <table>
            <tr>
                <th>Kullanıcı</th>
                <th>✅ Onay</th>
                <th>❌ Red</th>
                <th>❓ Şüpheli</th>
                <th>📋 Toplam</th>
            </tr>
    """
    
    for user, stats in report['users'].items():
        html += f"""
            <tr>
                <td><strong>{user}</strong></td>
                <td class="stat-approved">{stats['approved']}</td>
                <td class="stat-rejected">{stats['rejected']}</td>
                <td class="stat-suspicious">{stats['suspicious']}</td>
                <td>{stats['total']}</td>
            </tr>
        """
    
    if not report['users']:
        html += '<tr><td colspan="5" style="text-align:center;">Bu hafta değerlendirme yapılmadı</td></tr>'
    
    html += """
        </table>
        
        <h2>📋 Event Log Özeti</h2>
        <table>
            <tr>
                <th>İşlem Türü</th>
                <th>Adet</th>
            </tr>
    """
    
    action_names = {
        'Login': '🔓 Giriş',
        'Logout': '🚪 Çıkış',
        'Verify': '✓ Doğrulama',
        'PasswordChange': '🔐 Şifre Değişikliği',
        'UserCreate': '👤 Kullanıcı Oluşturma',
        'UserEdit': '✏️ Kullanıcı Düzenleme',
        'LoginFailed': '❌ Başarısız Giriş',
    }
    
    for action, count in report['event_summary'].items():
        action_display = action_names.get(action, action)
        html += f"""
            <tr>
                <td>{action_display}</td>
                <td>{count}</td>
            </tr>
        """
    
    html += """
        </table>
        
        <hr>
        <p style="color: #7f8c8d; font-size: 12px;">
            Bu rapor Photo Verifier sistemi tarafından otomatik olarak oluşturulmuştur.<br>
            🔗 <a href="https://photo.teamguerilla.com">photo.teamguerilla.com</a>
        </p>
    </body>
    </html>
    """
    
    return html


def send_email(html_content):
    """E-posta gönderir."""
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"📸 Photo Verifier - Haftalık Rapor ({datetime.now().strftime('%d.%m.%Y')})"
    msg['From'] = EMAIL_CONFIG['sender_email']
    msg['To'] = ', '.join(EMAIL_CONFIG['recipients'])
    
    msg.attach(MIMEText(html_content, 'html'))
    
    try:
        server = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
        server.starttls()
        server.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['sender_password'])
        server.sendmail(
            EMAIL_CONFIG['sender_email'],
            EMAIL_CONFIG['recipients'],
            msg.as_string()
        )
        server.quit()
        print("✅ E-posta gönderildi!")
        return True
    except Exception as e:
        print(f"❌ E-posta hatası: {e}")
        return False


def run_weekly_report():
    """Haftalık rapor oluşturur ve gönderir."""
    print("="*50)
    print("📸 WEEKLY REPORT")
    print(f"   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*50)
    
    # İstatistikleri topla
    print("\n📊 İstatistikler toplanıyor...")
    report = get_weekly_stats()
    
    # HTML rapor oluştur
    print("📝 Rapor oluşturuluyor...")
    html = generate_html_report(report)
    
    # E-posta gönder
    print("📧 E-posta gönderiliyor...")
    send_email(html)
    
    print("\n✅ Haftalık rapor tamamlandı!")


if __name__ == "__main__":
    run_weekly_report()