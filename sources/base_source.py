"""
Base Source - Temel Veritabanı İşlemleri
=========================================
Tüm projeler için ortak sorgular ve işlemler.
"""

import pymssql
import sqlite3
import hashlib
import os
from datetime import datetime
from typing import List, Dict, Optional
from config import PHOTO_TYPE_CONFIG


class BaseSource:
    """Temel veri kaynağı sınıfı."""
    
    def __init__(self, config: dict):
        self.config = config
        self.project_key = config['key']
        self.db_config = config['db']
        self.image_path = config['image_path']
        self.filters = config.get('filters', {})
        
        # Doğrulama DB'si (SQLite - lokal)
        self.verify_db_path = os.path.join(
            os.path.dirname(__file__), '..', 'data', 'verifications.db'
        )
        self._init_verify_db()
    
    def _get_connection(self):
        """SQL Server bağlantısı oluşturur."""
        return pymssql.connect(
            server=self.db_config['host'],
            port=self.db_config.get('port', 1433),
            user=self.db_config['username'],
            password=self.db_config['password'],
            database=self.db_config['database']
        )

        def _fix_turkish_chars(self, text: str) -> str:
        """Bozuk Türkçe karakterleri düzeltir."""
        if not text:
            return text
        replacements = {
            'ý': 'ı',
            'Ý': 'İ',
            'þ': 'ş',
            'Þ': 'Ş',
            'ð': 'ğ',
            'Ð': 'Ğ',
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text
    
    def _init_verify_db(self):
        """Doğrulama veritabanını oluşturur."""
        os.makedirs(os.path.dirname(self.verify_db_path), exist_ok=True)
        
        conn = sqlite3.connect(self.verify_db_path)
        cursor = conn.cursor()
        
        # Doğrulama tablosu
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS verifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT NOT NULL,
                photo_type TEXT NOT NULL,
                photo_id INTEGER NOT NULL,
                visit_id INTEGER,
                status TEXT NOT NULL,
                note TEXT,
                verified_by TEXT,
                verified_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(project, photo_type, photo_id)
            )
        ''')
        
        # Hash tablosu (duplicate detection için)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS photo_hashes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT NOT NULL,
                photo_type TEXT NOT NULL,
                photo_id INTEGER NOT NULL,
                visit_id INTEGER,
                md5_hash TEXT,
                file_size INTEGER,
                image_path TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(project, photo_type, photo_id)
            )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_hash ON photo_hashes(md5_hash)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_project ON photo_hashes(project)')
        
        conn.commit()
        conn.close()
    
    def _build_user_filter(self):
        """Kullanıcı filtresi SQL parçası oluşturur."""
        if 'user_role_id' in self.filters:
            return f"AND ur.RoleId = {self.filters['user_role_id']}"
        return ""
    
    def _convert_image_path(self, db_path: str) -> str:
        """
        Veritabanındaki path'i web URL'ine çevirir.
        \\bfserver1\d$\AdcoFiles\Image\2025\12\10\guid.png -> 2025/12/10/guid.png
        """
        if not db_path:
            return ""
        
        # Tüm backslash'leri forward slash'e çevir
        path = db_path.replace('\\', '/')
        
        # Çift slash'leri tek yap
        while '//' in path:
            path = path.replace('//', '/')
        
        # Image'den sonrasını al
        if '/Image/' in path:
            return path.split('/Image/')[-1]
        
        # Alternatif: Yıl klasörünü bul (2025, 2024 gibi)
        parts = path.split('/')
        for i, part in enumerate(parts):
            if part.isdigit() and len(part) == 4 and int(part) >= 2020:
                return '/'.join(parts[i:])
        
        # En kötü ihtimal: sadece dosya adı
        return path.split('/')[-1]
    
    # ==================== FOTOğRAF SORGULARI ====================
    
    def get_exhibition_photos(self, start_date: str, end_date: str) -> List[Dict]:
        """Teşhir fotoğraflarını getirir."""
        user_filter = self._build_user_filter()
        user_join = ""
        
        if 'user_role_id' in self.filters:
            user_join = "INNER JOIN UserRoles ur ON v.UserId = ur.UserId AND ur.RoleId = {} AND ur.IsDeleted = 0".format(self.filters['user_role_id'])
        
        # Type kolonu bazı projelerde yok
        type_column = "e.Type as ExhibitionType," if self.config.get('has_exhibition_type', True) else "NULL as ExhibitionType,"
        
        query = f"""
        SELECT 
            e.Id as PhotoId,
            e.TeammateVisitId as VisitId,
            e.ImagePath,
            e.CreatedDate as PhotoDate,
            {type_column}
            e.PackageQuantity,
            v.UserId,
            v.StartDate as VisitStartDate,
            v.FinishDate as VisitEndDate,
            r.CustomerId,
            c.CustomerName,
            c.CustomerCode,
            u.Name + ' ' + u.Surname as Personnel,
            'exhibition' as PhotoType
        FROM TeammateVisitExhibition e
        INNER JOIN TeammateVisit v ON e.TeammateVisitId = v.Id
        INNER JOIN TeammateRoute r ON v.TeammateRouteId = r.Id
        INNER JOIN Customers c ON r.CustomerId = c.CustomerCode
        INNER JOIN Users u ON v.UserId = u.Id
        {user_join}
        WHERE e.ImagePath IS NOT NULL
          AND e.IsDeleted = 0
          AND CAST(e.CreatedDate AS DATE) BETWEEN %s AND %s
        ORDER BY e.CreatedDate DESC
        """
        
        print(f"DEBUG get_exhibition_photos: {start_date} to {end_date}")
        
        try:
            conn = self._get_connection()
            cursor = conn.cursor(as_dict=True)
            cursor.execute(query, (start_date, end_date))
            results = cursor.fetchall()
            conn.close()
            
            print(f"DEBUG exhibition query returned: {len(results)} rows")
            
            # Path'leri dönüştür
            for r in results:
                r['ImageUrl'] = self._convert_image_path(r['ImagePath'])
            
            return results
        except Exception as e:
            print(f"DEBUG ERROR in get_exhibition_photos: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def get_planogram_photos(self, start_date: str, end_date: str) -> List[Dict]:
        """Planogram fotoğraflarını getirir."""
        user_filter = self._build_user_filter()
        user_join = "LEFT JOIN UserRoles ur ON v.UserId = ur.UserId" if user_filter else ""
        
        query = f"""
        SELECT 
            p.Id as PhotoId,
            p.TeammateVisitId as VisitId,
            p.ImagePath,
            p.CreatedDate as PhotoDate,
            p.LidQuantity,
            p.BeforeImagePath,
            v.UserId,
            v.StartDate as VisitStartDate,
            r.CustomerId,
            c.CustomerName,
            c.CustomerCode,
            u.Name + ' ' + u.Surname as Personnel,
            'planogram' as PhotoType
        FROM TeammateVisitPlanogram p
        INNER JOIN TeammateVisit v ON p.TeammateVisitId = v.Id
        INNER JOIN TeammateRoute r ON v.TeammateRouteId = r.Id
        INNER JOIN Customers c ON r.CustomerId = c.CustomerCode
        INNER JOIN Users u ON v.UserId = u.Id
        {user_join}
        WHERE p.ImagePath IS NOT NULL
          AND p.IsDeleted = 0
          AND CAST(p.CreatedDate AS DATE) BETWEEN %s AND %s
          {user_filter}
        ORDER BY p.CreatedDate DESC
        """
        
        conn = self._get_connection()
        cursor = conn.cursor(as_dict=True)
        cursor.execute(query, (start_date, end_date))
        results = cursor.fetchall()
        conn.close()
        
        for r in results:
            r['ImageUrl'] = self._convert_image_path(r['ImagePath'])
        
        return results
    
    def get_visit_photos(self, visit_id: int = None, start_date: str = None, end_date: str = None) -> Dict:
        """Ziyaret fotoğraflarını getirir."""
        user_filter = self._build_user_filter()
        user_join = "LEFT JOIN UserRoles ur ON v.UserId = ur.UserId" if user_filter else ""
        
        if visit_id:
            where_clause = "v.Id = %s"
            params = (visit_id,)
        else:
            where_clause = "CAST(v.CreatedDate AS DATE) BETWEEN %s AND %s"
            params = (start_date, end_date)
        
        query = f"""
        SELECT 
            v.Id as VisitId,
            v.ImagePath,
            v.StartDate,
            v.FinishDate,
            v.Latitude,
            v.Longitude,
            v.UserId,
            r.CustomerId,
            c.CustomerName,
            c.CustomerCode,
            u.Name + ' ' + u.Surname as Personnel,
            'visit' as PhotoType
        FROM TeammateVisit v
        INNER JOIN TeammateRoute r ON v.TeammateRouteId = r.Id
        INNER JOIN Customers c ON r.CustomerId = c.CustomerCode
        INNER JOIN Users u ON v.UserId = u.Id
        {user_join}
        WHERE v.ImagePath IS NOT NULL
          AND v.IsDeleted = 0
          AND {where_clause}
          {user_filter}
        ORDER BY v.StartDate DESC
        """
        
        conn = self._get_connection()
        cursor = conn.cursor(as_dict=True)
        cursor.execute(query, params)
        results = cursor.fetchall()
        conn.close()
        
        for r in results:
            r['ImageUrl'] = self._convert_image_path(r['ImagePath'])
            r['PhotoId'] = r['VisitId']  # Tutarlılık için
        
        return results
    
    def get_photos_grouped(self, photo_type: str, start_date: str, end_date: str) -> List[Dict]:
        """Fotoğrafları ziyarete göre gruplandırarak getirir."""
        print(f"DEBUG get_photos_grouped: type={photo_type}, from={start_date}, to={end_date}")
        
        try:
            if photo_type == 'exhibition':
                photos = self.get_exhibition_photos(start_date, end_date)
            elif photo_type == 'planogram':
                photos = self.get_planogram_photos(start_date, end_date)
            elif photo_type == 'visit':
                photos = self.get_visit_photos(start_date=start_date, end_date=end_date)
            else:
                print(f"DEBUG unknown photo_type: {photo_type}")
                return []
            
            print(f"DEBUG photos count: {len(photos)}")
            if photos:
                print(f"DEBUG first photo ImagePath: {photos[0].get('ImagePath', 'NO PATH')}")
                print(f"DEBUG first photo ImageUrl: {photos[0].get('ImageUrl', 'NO URL')}")
        except Exception as e:
            print(f"DEBUG ERROR in get_photos_grouped: {e}")
            import traceback
            traceback.print_exc()
            return []
        
        # Ziyarete göre grupla
        grouped = {}
        for photo in photos:
            visit_id = photo['VisitId']
            if visit_id not in grouped:
                grouped[visit_id] = {
                    'visit_id': visit_id,
                    'customer_name': photo.get('CustomerName', ''),
                    'customer_code': photo.get('CustomerCode', ''),
                    'personnel': photo.get('Personnel', ''),
                    'visit_date': photo.get('VisitStartDate') or photo.get('StartDate'),
                    'photos': []
                }
            grouped[visit_id]['photos'].append(photo)
        
        # Liste olarak döndür, tarihe göre sıralı
        result = list(grouped.values())
        result.sort(key=lambda x: x['visit_date'] or '', reverse=True)
        
        print(f"DEBUG grouped visits count: {len(result)}")
        # Doğrulama bilgilerini ekle
        for group in result:
            for photo in group['photos']:
                verification = self.get_verification_status(photo['PhotoId'], photo_type)
                photo['verification'] = verification
        return result
    
    def get_all_visit_photos(self, visit_id: int) -> Dict:
        """Bir ziyaretin TÜM fotoğraflarını getirir (exhibition + planogram + visit)."""
        result = {
            'visit_id': visit_id,
            'info': None,
            'exhibition': [],
            'planogram': [],
            'visit': [],
        }
        
        conn = self._get_connection()
        cursor = conn.cursor(as_dict=True)
        
        # Ziyaret bilgisi
        cursor.execute("""
            SELECT 
                v.Id as VisitId,
                v.StartDate,
                v.FinishDate,
                v.ImagePath,
                r.CustomerId,
                c.CustomerName,
                c.CustomerCode,
                u.Name + ' ' + u.Surname as Personnel
            FROM TeammateVisit v
            INNER JOIN TeammateRoute r ON v.TeammateRouteId = r.Id
            INNER JOIN Customers c ON r.CustomerId = c.CustomerCode
            INNER JOIN Users u ON v.UserId = u.Id
            WHERE v.Id = %s
        """, (visit_id,))
        
        visit_info = cursor.fetchone()
        if visit_info:
            result['info'] = visit_info
            if visit_info['ImagePath']:
                result['visit'].append({
                    'PhotoId': visit_id,
                    'ImagePath': visit_info['ImagePath'],
                    'ImageUrl': self._convert_image_path(visit_info['ImagePath']),
                    'PhotoType': 'visit'
                })
        
        # Teşhir fotoğrafları
        cursor.execute("""
            SELECT Id as PhotoId, ImagePath, CreatedDate, Type, PackageQuantity, ProductQuantity
            FROM TeammateVisitExhibition
            WHERE TeammateVisitId = %s AND ImagePath IS NOT NULL AND IsDeleted = 0
            ORDER BY CreatedDate
        """, (visit_id,))
        
        for row in cursor.fetchall():
            row['ImageUrl'] = self._convert_image_path(row['ImagePath'])
            row['PhotoType'] = 'exhibition'
            result['exhibition'].append(row)
        
        # Planogram fotoğrafları
        cursor.execute("""
            SELECT Id as PhotoId, ImagePath, CreatedDate, LidQuantity, BeforeImagePath
            FROM TeammateVisitPlanogram
            WHERE TeammateVisitId = %s AND ImagePath IS NOT NULL AND IsDeleted = 0
            ORDER BY CreatedDate
        """, (visit_id,))
        
        for row in cursor.fetchall():
            row['ImageUrl'] = self._convert_image_path(row['ImagePath'])
            row['PhotoType'] = 'planogram'
            result['planogram'].append(row)
        
        conn.close()
        return result
    
    # ==================== İSTATİSTİKLER ====================
    
    def get_stats(self, start_date: str, end_date: str) -> Dict:
        """İstatistikleri getirir."""
        stats = {
            'date_range': f"{start_date} - {end_date}",
            'exhibition_count': 0,
            'planogram_count': 0,
            'visit_count': 0,
            'unique_visits': 0,
            'active_personnel': 0,
        }
        
        user_filter = self._build_user_filter()
        user_join = "LEFT JOIN UserRoles ur ON v.UserId = ur.UserId" if user_filter else ""
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Exhibition
        cursor.execute(f"""
            SELECT COUNT(*) FROM TeammateVisitExhibition e
            INNER JOIN TeammateVisit v ON e.TeammateVisitId = v.Id
            {user_join}
            WHERE e.ImagePath IS NOT NULL AND e.IsDeleted = 0
            AND CAST(e.CreatedDate AS DATE) BETWEEN %s AND %s
            {user_filter}
        """, (start_date, end_date))
        stats['exhibition_count'] = cursor.fetchone()[0]
        
        # Planogram
        cursor.execute(f"""
            SELECT COUNT(*) FROM TeammateVisitPlanogram p
            INNER JOIN TeammateVisit v ON p.TeammateVisitId = v.Id
            {user_join}
            WHERE p.ImagePath IS NOT NULL AND p.IsDeleted = 0
            AND CAST(p.CreatedDate AS DATE) BETWEEN %s AND %s
            {user_filter}
        """, (start_date, end_date))
        stats['planogram_count'] = cursor.fetchone()[0]
        
        # Visit
        cursor.execute(f"""
            SELECT COUNT(*) FROM TeammateVisit v
            {user_join}
            WHERE v.ImagePath IS NOT NULL AND v.IsDeleted = 0
            AND CAST(v.CreatedDate AS DATE) BETWEEN %s AND %s
            {user_filter}
        """, (start_date, end_date))
        stats['visit_count'] = cursor.fetchone()[0]
        
        # Unique visits
        cursor.execute(f"""
            SELECT COUNT(DISTINCT e.TeammateVisitId) FROM TeammateVisitExhibition e
            INNER JOIN TeammateVisit v ON e.TeammateVisitId = v.Id
            {user_join}
            WHERE CAST(e.CreatedDate AS DATE) BETWEEN %s AND %s
            {user_filter}
        """, (start_date, end_date))
        stats['unique_visits'] = cursor.fetchone()[0]
        
        # Active personnel
        cursor.execute(f"""
            SELECT COUNT(DISTINCT v.UserId) FROM TeammateVisit v
            {user_join}
            WHERE CAST(v.CreatedDate AS DATE) BETWEEN %s AND %s
            {user_filter}
        """, (start_date, end_date))
        stats['active_personnel'] = cursor.fetchone()[0]
        
        conn.close()
        return stats
    
    # ==================== DOĞRULAMA ====================
    
    def verify_photo(self, photo_id: int, photo_type: str, status: str, 
                     note: str = '', verified_by: str = 'anonymous') -> Dict:
        """Fotoğrafı doğrular/reddeder."""
        conn = sqlite3.connect(self.verify_db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO verifications 
            (project, photo_type, photo_id, status, note, verified_by, verified_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            self.project_key,
            photo_type,
            photo_id,
            status,
            note,
            verified_by,
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
        
        return {'photo_id': photo_id, 'status': status}
    
    def get_verification_status(self, photo_id: int, photo_type: str) -> Optional[Dict]:
        """Fotoğrafın doğrulama durumunu getirir."""
        conn = sqlite3.connect(self.verify_db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT status, note, verified_by, verified_at
            FROM verifications
            WHERE project = ? AND photo_type = ? AND photo_id = ?
        ''', (self.project_key, photo_type, photo_id))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'status': row[0],
                'note': row[1],
                'verified_by': row[2],
                'verified_at': row[3]
            }
        return None
    
    # ==================== DUPLICATE DETECTION ====================
    
    def find_duplicates(self) -> List[Dict]:
        """Duplicate fotoğrafları bulur (hash tabanlı)."""
        conn = sqlite3.connect(self.verify_db_path)
        cursor = conn.cursor()
        
        # Aynı hash'e sahip grupları bul
        cursor.execute('''
            SELECT md5_hash, COUNT(*) as count
            FROM photo_hashes
            WHERE project = ? AND md5_hash IS NOT NULL
            GROUP BY md5_hash
            HAVING COUNT(*) > 1
        ''', (self.project_key,))
        
        duplicate_hashes = cursor.fetchall()
        duplicates = []
        
        for md5_hash, count in duplicate_hashes:
            cursor.execute('''
                SELECT photo_id, photo_type, visit_id, image_path
                FROM photo_hashes
                WHERE project = ? AND md5_hash = ?
            ''', (self.project_key, md5_hash))
            
            files = []
            for row in cursor.fetchall():
                files.append({
                    'photo_id': row[0],
                    'photo_type': row[1],
                    'visit_id': row[2],
                    'image_path': row[3],
                    'image_url': self._convert_image_path(row[3])
                })
            
            duplicates.append({
                'hash': md5_hash,
                'count': count,
                'files': files
            })
        
        conn.close()
        return duplicates

    def get_personnel_list(self, start_date: str = None, end_date: str = None) -> List[Dict]:
        """Aktif personel listesini getirir."""
        user_join = ""
        if 'user_role_id' in self.filters:
            user_join = f"INNER JOIN UserRoles ur ON u.Id = ur.UserId AND ur.RoleId = {self.filters['user_role_id']} AND ur.IsDeleted = 0"
        
        date_filter = ""
        params = ()
        if start_date and end_date:
            date_filter = "AND CAST(v.CreatedDate AS DATE) BETWEEN %s AND %s"
            params = (start_date, end_date)
        
        query = f"""
        SELECT DISTINCT u.Id, u.Name + ' ' + u.Surname as FullName
        FROM Users u
        INNER JOIN TeammateVisit v ON u.Id = v.UserId
        {user_join}
        WHERE u.IsDeleted = 0 {date_filter}
        ORDER BY FullName
        """
        
        conn = self._get_connection()
        cursor = conn.cursor(as_dict=True)
        cursor.execute(query, params)
        results = cursor.fetchall()
        conn.close()
        # Türkçe karakter düzeltmesi
        for r in results:
            if r.get('FullName'):
                r['FullName'] = self._fix_turkish_chars(r['FullName'])
        return results

    def get_customer_list(self, start_date: str = None, end_date: str = None) -> List[Dict]:
        """Aktif mağaza listesini getirir."""
        user_join = ""
        if 'user_role_id' in self.filters:
            user_join = f"INNER JOIN UserRoles ur ON v.UserId = ur.UserId AND ur.RoleId = {self.filters['user_role_id']} AND ur.IsDeleted = 0"
        
        date_filter = ""
        params = ()
        if start_date and end_date:
            date_filter = "AND CAST(v.CreatedDate AS DATE) BETWEEN %s AND %s"
            params = (start_date, end_date)
        
        query = f"""
        SELECT DISTINCT c.CustomerCode, c.CustomerName
        FROM Customers c
        INNER JOIN TeammateRoute r ON c.CustomerCode = r.CustomerId
        INNER JOIN TeammateVisit v ON r.Id = v.TeammateRouteId
        {user_join}
        WHERE 1=1 {date_filter}
        ORDER BY c.CustomerName
        """
        
        conn = self._get_connection()
        cursor = conn.cursor(as_dict=True)
        cursor.execute(query, params)
        results = cursor.fetchall()
        conn.close()
        return results    
