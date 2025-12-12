"""
Photo Cache Builder
====================
Fotoğraf listelerini önbelleğe alır.
Saat başı çalıştırılmak üzere tasarlanmıştır.
"""

import json
import pymssql
from datetime import datetime, timedelta

from config import PROJECTS, PHOTOVERIFIER_DB
from sources import get_source


def get_pv_connection():
    """PhotoVerifier veritabanı bağlantısı."""
    return pymssql.connect(
        server=PHOTOVERIFIER_DB['host'],
        port=PHOTOVERIFIER_DB.get('port', 1433),
        user=PHOTOVERIFIER_DB['username'],
        password=PHOTOVERIFIER_DB['password'],
        database=PHOTOVERIFIER_DB['database']
    )


def build_cache_for_project(project_key: str, days: int = 7):
    """Bir proje için fotoğraf cache oluşturur."""
    print(f"\n📸 {project_key.upper()} cache oluşturuluyor...")
    
    source = get_source(project_key)
    config = PROJECTS[project_key]
    
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    conn = get_pv_connection()
    cursor = conn.cursor()
    
    for photo_type in config.get('photo_tables', []):
        print(f"  📂 {photo_type}...")
        
        try:
            # Fotoğrafları getir
            if photo_type == 'exhibition':
                photos = source.get_exhibition_photos(start_date, end_date)
            elif photo_type == 'planogram':
                photos = source.get_planogram_photos(start_date, end_date)
            elif photo_type == 'visit':
                photos = source.get_visit_photos(start_date=start_date, end_date=end_date)
            else:
                continue
            
            print(f"    Bulunan: {len(photos)} fotoğraf")
            
            # Tarihe göre grupla
            by_date = {}
            for photo in photos:
                photo_date = photo.get('PhotoDate') or photo.get('StartDate')
                if photo_date:
                    date_key = photo_date.strftime('%Y-%m-%d') if hasattr(photo_date, 'strftime') else str(photo_date)[:10]
                    if date_key not in by_date:
                        by_date[date_key] = []
                    by_date[date_key].append(photo)
            
            # Her gün için cache yaz
            for cache_date, day_photos in by_date.items():
                # JSON'a çevir (datetime'ları string yap)
                photos_json = json.dumps(day_photos, default=str, ensure_ascii=False)
                
                # Önce sil sonra ekle
                cursor.execute('''
                    DELETE FROM PhotoListCache 
                    WHERE Project = %s AND PhotoType = %s AND CacheDate = %s
                ''', (project_key, photo_type, cache_date))
                
                cursor.execute('''
                    INSERT INTO PhotoListCache (Project, PhotoType, CacheDate, Details, PhotoCount)
                    VALUES (%s, %s, %s, %s, %s)
                ''', (project_key, photo_type, cache_date, photos_json, len(day_photos)))
            
            conn.commit()
            print(f"    ✅ {len(by_date)} gün cache'e yazıldı")
            
        except Exception as e:
            print(f"    ❌ Hata: {e}")
            import traceback
            traceback.print_exc()
    
    conn.close()


def build_all_caches(days: int = 7):
    """Tüm projeler için cache oluşturur."""
    print("="*50)
    print("📸 PHOTO CACHE BUILDER")
    print(f"   Başlangıç: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Son {days} gün")
    print("="*50)
    
    for project_key in PROJECTS:
        build_cache_for_project(project_key, days)
    
    print("\n" + "="*50)
    print("✅ Tüm cache'ler güncellendi!")
    print(f"   Bitiş: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*50)


if __name__ == "__main__":
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    build_all_caches(days)