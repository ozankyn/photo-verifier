"""
Duplicate Cache Builder
========================
Duplicate hesaplamalarını önbelleğe alır.
Gece çalıştırılmak üzere tasarlanmıştır.
"""

import json
import pymssql
from datetime import datetime

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


def build_cache_for_project(project_key: str):
    """Bir proje için duplicate cache oluşturur."""
    print(f"\n📦 {project_key.upper()} cache oluşturuluyor...")
    
    source = get_source(project_key)
    duplicates = source.find_duplicates()
    
    print(f"  Bulunan duplicate grup: {len(duplicates)}")
    
    conn = get_pv_connection()
    cursor = conn.cursor()
    
    # Eski cache'i temizle
    cursor.execute('DELETE FROM DuplicateCache WHERE Project = %s', (project_key,))
    
    # Yeni cache'i yaz
    for dup in duplicates:
        photo_ids = json.dumps([f['photo_id'] for f in dup['files']])
        details = json.dumps(dup['files'], default=str, ensure_ascii=False)
        
        cursor.execute('''
            INSERT INTO DuplicateCache (Project, Md5Hash, PhotoCount, PhotoIds, Details)
            VALUES (%s, %s, %s, %s, %s)
        ''', (project_key, dup['hash'], dup['count'], photo_ids, details))
    
    conn.commit()
    conn.close()
    
    print(f"  ✅ {len(duplicates)} grup cache'e yazıldı")


def build_all_caches():
    """Tüm projeler için cache oluşturur."""
    print("="*50)
    print("📦 DUPLICATE CACHE BUILDER")
    print(f"   Başlangıç: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*50)
    
    for project_key in PROJECTS:
        build_cache_for_project(project_key)
    
    print("\n" + "="*50)
    print("✅ Tüm cache'ler güncellendi!")
    print(f"   Bitiş: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*50)


if __name__ == "__main__":
    build_all_caches()