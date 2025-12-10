"""
Photo Verifier - Konfigürasyon
===============================
4 Proje için veritabanı ve dosya yolu ayarları.
"""

# SQL Server bağlantı bilgileri
DB_CONFIG = {
    'host': '192.168.10.2',
    'port': 1433,
    'username': 'photoverifier',
    'password': '1q2w3e4R!!',
}

# Proje tanımları
PROJECTS = {
    'adco': {
        'name': 'ADCO',
        'database': 'TeamGuerillaAdco',
        'image_path': r'D:\AdcoFiles\Image',
        'photo_tables': ['exhibition', 'planogram'],
        'color': '#3498db',  # Mavi
        'icon': '🏪',
    },
    'beylerbeyi': {
        'name': 'Beylerbeyi',
        'database': 'TeamGuerillaBeylerbeyi',
        'image_path': r'D:\BeylerbeyiFiles\Image',
        'photo_tables': ['exhibition', 'planogram'],
        'color': '#9b59b6',  # Mor
        'icon': '🍺',
    },
    'bf': {
        'name': 'BF',
        'database': 'TeamGuerillaBF',
        'image_path': r'D:\BFFiles\Image',
        'photo_tables': ['exhibition', 'visit'],
        'color': '#e74c3c',  # Kırmızı
        'icon': '🔴',
    },
    'efes': {
        'name': 'Efes - KK Merch',
        'database': 'TeamGuerillaEfes',
        'image_path': r'D:\EfesData\Files\Image',
        'photo_tables': ['exhibition', 'planogram', 'visit'],
        'color': '#f39c12',
        'icon': '🍻',
        'has_exhibition_type': False,  # Type kolonu yok
        'filters': {
            'user_role_id': 4,
        },
    },
}

# Fotoğraf türü eşleştirmeleri
PHOTO_TYPE_CONFIG = {
    'exhibition': {
        'table': 'TeammateVisitExhibition',
        'name_tr': 'Teşhir',
        'icon': '📦',
    },
    'planogram': {
        'table': 'TeammateVisitPlanogram',
        'name_tr': 'Planogram',
        'icon': '📊',
    },
    'visit': {
        'table': 'TeammateVisit',
        'name_tr': 'Ziyaret',
        'icon': '📸',
    },
}


def get_project_config(project_key):
    """Proje konfigürasyonunu döndürür."""
    if project_key not in PROJECTS:
        raise ValueError(f"Proje bulunamadı: {project_key}")
    
    config = PROJECTS[project_key].copy()
    config['key'] = project_key
    config['db'] = {
        **DB_CONFIG,
        'database': config['database'],
    }
    return config


def get_db_connection_string(project_key):
    """Proje için bağlantı string'i döndürür."""
    config = get_project_config(project_key)
    return config['db']
