"""
Base Source - Temel Veritabanı İşlemleri
=========================================
Tüm projeler için ortak sorgular ve işlemler.
"""
import os
import pymssql
import hashlib
from datetime import datetime
from typing import List, Dict, Optional
from config import PHOTO_TYPE_CONFIG
from config import PHOTOVERIFIER_DB

class BaseSource:
    """Temel veri kaynağı sınıfı."""
    
    def __init__(self, config: dict):
        self.config = config
        self.project_key = config['key']
        self.db_config = config['db']
        self.image_path = config['image_path']
        self.filters = config.get('filters', {})
        
        # Doğrulama DB'si (SQL Server - PhotoVerifier)
        self.pv_db_config = PHOTOVERIFIER_DB
    
    def _get_connection(self):
        """SQL Server bağlantısı oluşturur."""
        return pymssql.connect(
            server=self.db_config['host'],
            port=self.db_config.get('port', 1433),
            user=self.db_config['username'],
            password=self.db_config['password'],
            database=self.db_config['database']
        )

    def _get_pv_connection(self):
        """PhotoVerifier veritabanı bağlantısı oluşturur."""
        return pymssql.connect(
            server=self.pv_db_config['host'],
            port=self.pv_db_config.get('port', 1433),
            user=self.pv_db_config['username'],
            password=self.pv_db_config['password'],
            database=self.pv_db_config['database']
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

    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """İki koordinat arası kuş uçuşu mesafe (km) - Haversine formülü."""
        import math
        
        R = 6371  # Dünya yarıçapı (km)
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return round(R * c, 2)    

    
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
    
    def get_exhibition_photos(self, start_date: str, end_date: str, user_id: int = None, customer_code: str = None) -> List[Dict]:
        """Teşhir fotoğraflarını getirir."""
        user_join = ""
        
        if 'user_role_id' in self.filters:
            user_join = "INNER JOIN UserRoles ur ON v.UserId = ur.UserId AND ur.RoleId = {} AND ur.IsDeleted = 0".format(self.filters['user_role_id'])
        
        # Type kolonu bazı projelerde yok
        type_column = "e.Type as ExhibitionType," if self.config.get('has_exhibition_type', True) else "NULL as ExhibitionType,"
        
        # Ekstra filtreler
        extra_filters = ""
        if user_id:
            extra_filters += f" AND v.UserId = {user_id}"
        if customer_code:
            extra_filters += f" AND r.CustomerId = '{customer_code}'"
        
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
          {extra_filters}
        ORDER BY e.CreatedDate DESC
        """
        
        print(f"DEBUG get_exhibition_photos: {start_date} to {end_date}, user={user_id}, customer={customer_code}")
        
        try:
            conn = self._get_connection()
            cursor = conn.cursor(as_dict=True)
            cursor.execute(query, (start_date, end_date))
            results = cursor.fetchall()
            conn.close()
            
            print(f"DEBUG exhibition query returned: {len(results)} rows")
            
            for r in results:
                r['ImageUrl'] = self._convert_image_path(r['ImagePath'])
            
            return results
        except Exception as e:
            print(f"DEBUG ERROR in get_exhibition_photos: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def get_planogram_photos(self, start_date: str, end_date: str, user_id: int = None, customer_code: str = None) -> List[Dict]:
        """Planogram fotoğraflarını getirir."""
        user_join = ""
        if 'user_role_id' in self.filters:
            user_join = "INNER JOIN UserRoles ur ON v.UserId = ur.UserId AND ur.RoleId = {} AND ur.IsDeleted = 0".format(self.filters['user_role_id'])
        
        # Ekstra filtreler
        extra_filters = ""
        if user_id:
            extra_filters += f" AND v.UserId = {user_id}"
        if customer_code:
            extra_filters += f" AND r.CustomerId = '{customer_code}'"
        
        query = f"""
        SELECT 
            p.Id as PhotoId,
            p.TeammateVisitId as VisitId,
            p.ImagePath,
            p.CreatedDate as PhotoDate,
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
          {extra_filters}
        ORDER BY p.CreatedDate DESC
        """
        
        try:
            conn = self._get_connection()
            cursor = conn.cursor(as_dict=True)
            cursor.execute(query, (start_date, end_date))
            results = cursor.fetchall()
            conn.close()
            
            for r in results:
                r['ImageUrl'] = self._convert_image_path(r['ImagePath'])
            
            return results
        except Exception as e:
            print(f"DEBUG ERROR in get_planogram_photos: {e}")
            return []
    
    def get_visit_photos(self, visit_id: int = None, start_date: str = None, end_date: str = None, user_id: int = None, customer_code: str = None) -> List[Dict]:
        """Ziyaret fotoğraflarını getirir."""
        user_join = ""
        if 'user_role_id' in self.filters:
            user_join = "INNER JOIN UserRoles ur ON v.UserId = ur.UserId AND ur.RoleId = {} AND ur.IsDeleted = 0".format(self.filters['user_role_id'])
        
        if visit_id:
            where_clause = "v.Id = %s"
            params = (visit_id,)
        else:
            where_clause = "CAST(v.CreatedDate AS DATE) BETWEEN %s AND %s"
            params = (start_date, end_date)
        
        # Ekstra filtreler
        extra_filters = ""
        if user_id:
            extra_filters += f" AND v.UserId = {user_id}"
        if customer_code:
            extra_filters += f" AND r.CustomerId = '{customer_code}'"
        
        query = f"""
        SELECT 
            v.Id as VisitId,
            v.Id as PhotoId,
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
          {extra_filters}
        ORDER BY v.StartDate DESC
        """
        
        try:
            conn = self._get_connection()
            cursor = conn.cursor(as_dict=True)
            cursor.execute(query, params)
            results = cursor.fetchall()
            conn.close()
            
            for r in results:
                r['ImageUrl'] = self._convert_image_path(r['ImagePath'])
                r['PhotoDate'] = r.get('StartDate')  # Template uyumu için
            
            return results
        except Exception as e:
            print(f"DEBUG ERROR in get_visit_photos: {e}")
            return []
    
    def get_photos_grouped(self, photo_type: str, start_date: str, end_date: str, user_id: int = None, customer_code: str = None) -> List[Dict]:
        """Fotoğrafları ziyarete göre gruplandırarak getirir."""
        print(f"DEBUG get_photos_grouped: type={photo_type}, from={start_date}, to={end_date}, user={user_id}, customer={customer_code}")
        
        try:
            if photo_type == 'exhibition':
                photos = self.get_exhibition_photos(start_date, end_date, user_id, customer_code)
            elif photo_type == 'planogram':
                photos = self.get_planogram_photos(start_date, end_date, user_id, customer_code)
            elif photo_type == 'visit':
                photos = self.get_visit_photos(start_date=start_date, end_date=end_date, user_id=user_id, customer_code=customer_code)
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
        
        # Doğrulama bilgilerini ekle
        for group in result:
            for photo in group['photos']:
                verification = self.get_verification_status(photo['PhotoId'], photo_type)
                photo['verification'] = verification
        
        print(f"DEBUG grouped visits count: {len(result)}")
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
    
    def verify_photo(self, photo_id: int, photo_type: str, status: str, note: str = None, visit_id: int = None, verified_by: int = None) -> bool:
        """Fotoğraf doğrulama sonucunu kaydeder."""
        try:
            conn = self._get_pv_connection()
            cursor = conn.cursor()
            
            # Önce var mı kontrol et
            cursor.execute('''
                SELECT Id FROM Verifications 
                WHERE Project = %s AND PhotoType = %s AND PhotoId = %s
            ''', (self.project_key, photo_type, photo_id))
            
            existing = cursor.fetchone()
            
            if existing:
                cursor.execute('''
                    UPDATE Verifications 
                    SET Status = %s, Note = %s, VerifiedAt = GETDATE(), VerifiedBy = %s
                    WHERE Project = %s AND PhotoType = %s AND PhotoId = %s
                ''', (status, note, verified_by, self.project_key, photo_type, photo_id))
            else:
                cursor.execute('''
                    INSERT INTO Verifications (Project, PhotoType, PhotoId, VisitId, Status, Note, VerifiedBy)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (self.project_key, photo_type, photo_id, visit_id, status, note, verified_by))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"DEBUG verify_photo error: {e}")
            return False
    
    def get_verification_status(self, photo_id: int, photo_type: str) -> Optional[Dict]:
        """Fotoğrafın doğrulama durumunu getirir."""
        try:
            conn = self._get_pv_connection()
            cursor = conn.cursor(as_dict=True)
            
            cursor.execute('''
                SELECT Status as status, Note as note, VerifiedAt as verified_at
                FROM Verifications
                WHERE Project = %s AND PhotoType = %s AND PhotoId = %s
            ''', (self.project_key, photo_type, photo_id))
            
            result = cursor.fetchone()
            conn.close()
            return result
        except Exception as e:
            print(f"DEBUG get_verification_status error: {e}")
            return None
    
    # ==================== DUPLICATE DETECTION ====================
    
    def find_duplicates(self) -> List[Dict]:
        """Duplicate fotoğrafları bulur (hash tabanlı)."""
        try:
            conn = self._get_pv_connection()
            cursor = conn.cursor()
            
            # Aynı hash'e sahip grupları bul
            cursor.execute('''
                SELECT Md5Hash, COUNT(*) as count
                FROM PhotoHashes
                WHERE Project = %s AND Md5Hash IS NOT NULL
                GROUP BY Md5Hash
                HAVING COUNT(*) > 1
            ''', (self.project_key,))
            
            duplicate_hashes = cursor.fetchall()
            duplicates = []
            
            for md5_hash, count in duplicate_hashes:
                cursor.execute('''
                    SELECT PhotoId, PhotoType, VisitId, ImagePath
                    FROM PhotoHashes
                    WHERE Project = %s AND Md5Hash = %s
                ''', (self.project_key, md5_hash))
                
                files = []
                for row in cursor.fetchall():
                    photo_id = row[0]
                    photo_type = row[1]
                    visit_id = row[2]
                    image_path = row[3]
                    
                    # Ana DB'den personel ve müşteri bilgisi al
                    detail = self._get_photo_detail(photo_id, photo_type, visit_id)
                    
                    # Mesafe hesapla (km)
                    distance = None
                    visit_lat = detail.get('visit_lat')
                    visit_lon = detail.get('visit_lon')
                    customer_lat = detail.get('customer_lat')
                    customer_lon = detail.get('customer_lon')
                    
                    if all([visit_lat, visit_lon, customer_lat, customer_lon]):
                        distance = self._calculate_distance(visit_lat, visit_lon, customer_lat, customer_lon)
                    
                    files.append({
                        'photo_id': photo_id,
                        'photo_type': photo_type,
                        'visit_id': visit_id,
                        'image_path': image_path,
                        'image_url': self._convert_image_path(image_path),
                        'personnel': detail.get('personnel', ''),
                        'customer_name': detail.get('customer_name', ''),
                        'customer_code': detail.get('customer_code', ''),
                        'photo_date': detail.get('photo_date', ''),
                        'visit_lat': visit_lat,
                        'visit_lon': visit_lon,
                        'customer_lat': customer_lat,
                        'customer_lon': customer_lon,
                        'distance_km': distance,
                    })
                
                duplicates.append({
                    'hash': md5_hash,
                    'count': count,
                    'files': files
                })
            
            conn.close()
            return duplicates
        except Exception as e:
            print(f"DEBUG find_duplicates error: {e}")
            import traceback
            traceback.print_exc()
            return []

    def get_duplicates_from_cache(self) -> List[Dict]:
        """Önbellekten duplicate'leri getirir (hızlı)."""
        try:
            conn = self._get_pv_connection()
            cursor = conn.cursor(as_dict=True)
            
            cursor.execute('''
                SELECT Md5Hash, PhotoCount, Details, UpdatedAt
                FROM DuplicateCache
                WHERE Project = %s
                ORDER BY PhotoCount DESC
            ''', (self.project_key,))
            
            results = cursor.fetchall()
            conn.close()
            
            duplicates = []
            for row in results:
                import json
                files = json.loads(row['Details']) if row['Details'] else []
                duplicates.append({
                    'hash': row['Md5Hash'],
                    'count': row['PhotoCount'],
                    'files': files,
                    'cached_at': row['UpdatedAt']
                })
            
            return duplicates
        except Exception as e:
            print(f"DEBUG get_duplicates_from_cache error: {e}")
            return []

    def has_duplicate_cache(self) -> bool:
        """Cache var mı kontrol eder."""
        try:
            conn = self._get_pv_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM DuplicateCache WHERE Project = %s', (self.project_key,))
            count = cursor.fetchone()[0]
            conn.close()
            return count > 0
        except:
            return False        

    def _get_photo_detail(self, photo_id: int, photo_type: str, visit_id: int) -> Dict:
        """Fotoğraf detaylarını ana DB'den alır."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(as_dict=True)
            
            if photo_type == 'exhibition':
                cursor.execute('''
                    SELECT 
                        e.CreatedDate as photo_date,
                        u.Name + ' ' + u.Surname as personnel,
                        c.CustomerName as customer_name,
                        c.CustomerCode as customer_code,
                        v.Latitude as visit_lat,
                        v.Longitude as visit_lon,
                        c.Latitude as customer_lat,
                        c.Longitude as customer_lon
                    FROM TeammateVisitExhibition e
                    INNER JOIN TeammateVisit v ON e.TeammateVisitId = v.Id
                    INNER JOIN TeammateRoute r ON v.TeammateRouteId = r.Id
                    INNER JOIN Customers c ON r.CustomerId = c.CustomerCode
                    INNER JOIN Users u ON v.UserId = u.Id
                    WHERE e.Id = %s
                ''', (photo_id,))
            elif photo_type == 'planogram':
                cursor.execute('''
                    SELECT 
                        p.CreatedDate as photo_date,
                        u.Name + ' ' + u.Surname as personnel,
                        c.CustomerName as customer_name,
                        c.CustomerCode as customer_code,
                        v.Latitude as visit_lat,
                        v.Longitude as visit_lon,
                        c.Latitude as customer_lat,
                        c.Longitude as customer_lon
                    FROM TeammateVisitPlanogram p
                    INNER JOIN TeammateVisit v ON p.TeammateVisitId = v.Id
                    INNER JOIN TeammateRoute r ON v.TeammateRouteId = r.Id
                    INNER JOIN Customers c ON r.CustomerId = c.CustomerCode
                    INNER JOIN Users u ON v.UserId = u.Id
                    WHERE p.Id = %s
                ''', (photo_id,))
            elif photo_type == 'visit':
                cursor.execute('''
                    SELECT 
                        v.StartDate as photo_date,
                        u.Name + ' ' + u.Surname as personnel,
                        c.CustomerName as customer_name,
                        c.CustomerCode as customer_code,
                        v.Latitude as visit_lat,
                        v.Longitude as visit_lon,
                        c.Latitude as customer_lat,
                        c.Longitude as customer_lon
                    FROM TeammateVisit v
                    INNER JOIN TeammateRoute r ON v.TeammateRouteId = r.Id
                    INNER JOIN Customers c ON r.CustomerId = c.CustomerCode
                    INNER JOIN Users u ON v.UserId = u.Id
                    WHERE v.Id = %s
                ''', (photo_id,))
            else:
                conn.close()
                return {}
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                # Türkçe karakter düzeltmesi
                if result.get('personnel'):
                    result['personnel'] = self._fix_turkish_chars(result['personnel'])
                return result
            return {}
        except Exception as e:
            print(f"DEBUG _get_photo_detail error: {e}")
            return {}

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
