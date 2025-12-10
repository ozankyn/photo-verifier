"""
Hash Scanner - Fotoğraf Hash Tarayıcı
=====================================
Tüm fotoğrafları tarayıp MD5 hash hesaplar.
Zamanlanmış görev olarak çalıştırılabilir.
"""

import os
import hashlib
import sqlite3
from datetime import datetime, timedelta

from config import PROJECTS, get_project_config
from sources import get_source


def calculate_md5(file_path: str) -> str:
    """Dosyanın MD5 hash'ini hesaplar."""
    try:
        with open(file_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    except Exception as e:
        print(f"  Hash hatası: {file_path} - {e}")
        return None


def get_local_path(project_config: dict, image_url: str) -> str:
    """Image URL'ini lokal dosya yoluna çevirir."""
    base_path = project_config['image_path']
    return os.path.join(base_path, image_url)


def scan_project(project_key: str, days: int = 30):
    """Bir projenin fotoğraflarını tarar."""
    print(f"\n{'='*50}")
    print(f"📸 {project_key.upper()} taranıyor...")
    print('='*50)
    
    config = get_project_config(project_key)
    source = get_source(project_key)
    
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    print(f"Tarih aralığı: {start_date} - {end_date}")
    
    # Veritabanı bağlantısı
    db_path = os.path.join(os.path.dirname(__file__), 'data', 'verifications.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    stats = {'processed': 0, 'skipped': 0, 'not_found': 0, 'errors': 0}
    
    # Her fotoğraf türü için
    for photo_type in config.get('photo_tables', []):
        print(f"\n📂 {photo_type} fotoğrafları...")
        
        try:
            if photo_type == 'exhibition':
                photos = source.get_exhibition_photos(start_date, end_date)
            elif photo_type == 'planogram':
                photos = source.get_planogram_photos(start_date, end_date)
            elif photo_type == 'visit':
                photos = source.get_visit_photos(start_date=start_date, end_date=end_date)
            else:
                continue
        except Exception as e:
            print(f"  Sorgu hatası: {e}")
            continue
        
        print(f"  Bulunan: {len(photos)} fotoğraf")
        
        for i, photo in enumerate(photos):
            photo_id = photo['PhotoId']
            visit_id = photo.get('VisitId')
            image_url = photo.get('ImageUrl', '')
            image_path = photo.get('ImagePath', '')
            
            # Zaten tarandı mı?
            cursor.execute('''
                SELECT 1 FROM photo_hashes 
                WHERE project = ? AND photo_type = ? AND photo_id = ?
            ''', (project_key, photo_type, photo_id))
            
            if cursor.fetchone():
                stats['skipped'] += 1
                continue
            
            # Dosya yolunu oluştur
            local_path = get_local_path(config, image_url)
            
            if not os.path.exists(local_path):
                stats['not_found'] += 1
                continue
            
            # Hash hesapla
            md5_hash = calculate_md5(local_path)
            
            if md5_hash:
                file_size = os.path.getsize(local_path)
                
                cursor.execute('''
                    INSERT OR REPLACE INTO photo_hashes 
                    (project, photo_type, photo_id, visit_id, md5_hash, file_size, image_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (project_key, photo_type, photo_id, visit_id, md5_hash, file_size, image_path))
                
                stats['processed'] += 1
            else:
                stats['errors'] += 1
            
            # İlerleme
            if (i + 1) % 100 == 0:
                print(f"  İşlenen: {i + 1}/{len(photos)}")
                conn.commit()
        
        conn.commit()
    
    conn.close()
    
    print(f"\n📊 {project_key.upper()} Sonuç:")
    print(f"  Yeni işlenen: {stats['processed']}")
    print(f"  Zaten mevcut: {stats['skipped']}")
    print(f"  Dosya bulunamadı: {stats['not_found']}")
    print(f"  Hata: {stats['errors']}")


def scan_all(days: int = 30):
    """Tüm projeleri tarar."""
    print("="*50)
    print("📸 PHOTO HASH SCANNER")
    print(f"   Tüm projeler - Son {days} gün")
    print("="*50)
    
    for project_key in PROJECTS:
        scan_project(project_key, days)
    
    print("\n" + "="*50)
    print("✅ Tarama tamamlandı!")
    print("="*50)


if __name__ == "__main__":
    import sys
    
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    scan_all(days)