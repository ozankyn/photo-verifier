# Photo Verifier

Saha ziyaret fotoğraflarının görüntülenmesi ve doğrulanması için web tabanlı dashboard.

## Özellikler

- 📸 **Fotoğraf Görüntüleme**: Ziyarete göre gruplandırılmış fotoğraf galerisi
- ✅ **Doğrulama**: Fotoğrafları onaylama/reddetme/şüpheli işaretleme
- 🔍 **Duplicate Tespiti**: Aynı fotoğrafın farklı ziyaretlerde kullanımını bulma
- 📊 **Raporlama**: Excel formatında detaylı raporlar

## Desteklenen Projeler

| Proje | Veritabanı | Fotoğraf Türleri |
|-------|------------|------------------|
| ADCO | TeamGuerillaAdco | Teşhir, Planogram |
| Beylerbeyi | TeamGuerillaBeylerbeyi | Teşhir, Planogram |
| BF | TeamGuerillaBF | Teşhir, Ziyaret |
| Efes KK Merch | TeamGuerillaEfes | Teşhir, Planogram, Ziyaret |

## Kurulum (Windows Sunucu)

```powershell
# 1. Proje klasörünü oluştur
mkdir D:\PhotoVerifier
cd D:\PhotoVerifier

# 2. Dosyaları kopyala veya git clone
git clone https://github.com/ozankyn/photo-verifier.git .

# 3. Virtual environment oluştur
python -m venv venv
venv\Scripts\activate

# 4. Bağımlılıkları yükle
pip install -r requirements.txt
```

## Çalıştırma

### Development
```powershell
python app.py
```

### Production (Waitress)
```powershell
python run_production.py
```

### Windows Service
Task Scheduler ile otomatik başlatma için `start.bat` dosyasını kullanın.

## Erişim

- **Lokal**: http://localhost:5555
- **Ağ**: http://192.168.10.3:5555

## Konfigürasyon

`config.py` dosyasında:
- Veritabanı bağlantı bilgileri
- Fotoğraf dizin yolları
- Proje tanımları

## Kullanım

1. Sol menüden proje seçin (ADCO, Beylerbeyi, BF, Efes)
2. "Fotoğraflar" sayfasından fotoğraf türü ve tarih aralığı seçin
3. Fotoğrafları görüntüleyin, büyütmek için tıklayın
4. Doğrulama butonları ile işaretleyin:
   - ✓ Doğru
   - ✗ Yanlış  
   - ? Şüpheli

## Lisans

Team Guerilla - Internal Use Only
