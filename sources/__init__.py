"""
Photo Verifier - Data Sources
==============================
Her proje için veritabanı erişim modülleri.
"""

from .base_source import BaseSource

# Source sınıfları (tüm projeler aynı yapıyı kullanıyor)
_sources = {}


def get_source(project_key):
    """Proje için source instance döndürür."""
    if project_key not in _sources:
        from config import get_project_config
        config = get_project_config(project_key)
        _sources[project_key] = BaseSource(config)
    return _sources[project_key]
