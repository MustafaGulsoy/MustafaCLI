# Tool Kullanım İyileştirmeleri - 7B Model için

## Mevcut Durum Analizi

**Model**: qwen2.5-coder:7b
**Sorun**: Dosya oluşturabiliyor ama düzenleme yapamıyor
**Sebep**: 7B modeller daha açık talimatlar ve örnekler gerektirir

## Öneriler

### 1. ⚡ Hızlı Çözüm: Few-Shot Examples Ekle

System prompt'a **somut örnekler** ekleyin:

```python
### str_replace - Dosya Düzenleme Örnekleri

DOĞRU KULLANIM:
```tool
{
    "name": "str_replace",
    "arguments": {
        "path": "main.py",
        "old_str": "def hello():\n    print('hi')",
        "new_str": "def hello():\n    print('Hello, World!')"
    }
}
```

YANLIŞ: Sadece değişen kısmı yazmak
DOĞRU: Tam satırları context ile birlikte vermek
```

### 2. 🎯 Tool Seçim Mantığını Netleştir

**Önce-Sonra Yaklaşımı:**

```
## Dosya İşlemleri - Karar Ağacı

1. Dosya VAR MI?
   - HAYIR → create_file kullan
   - EVET → 2. adıma geç

2. Düzenleme mi yapacaksın?
   - EVET → view ile oku, sonra str_replace kullan
   - HAYIR → Başka işlem

3. str_replace için:
   a) view ile dosyayı oku
   b) Değiştirilecek kısmı TAM olarak kopyala (old_str)
   c) Yeni halini yaz (new_str)
```

### 3. 🔧 Tool Tanımlarını Güçlendir

**str_replace için:**

```python
description = """Dosyada HASSAS düzenleme yap - En çok kullanılan tool!

KULLANIM:
1. view tool ile dosyayı OKU
2. Değiştirilecek kısmı AYNEN KOPYALA (boşluklar dahil!)
3. Yeni halini yaz

ÖRNEK:
Dosya içeriği:
  name = "John"
  age = 25

Değiştirmek için:
{
  "name": "str_replace",
  "arguments": {
    "path": "user.py",
    "old_str": "  name = \"John\"",
    "new_str": "  name = \"Jane\""
  }
}

UYARI: old_str dosyada TAM OLARAK BİR KEZ geçmeli!
"""
```

### 4. 📝 Prompt Engineering - Chain of Thought

**System prompt'a ekle:**

```
## Düşünme Süreci (Her İşlemde Uygula)

1. PLAN: Ne yapacağım?
   - "Dosya var mı? → view ile kontrol"
   - "Düzenleme mi? → str_replace"
   - "Yeni dosya mı? → create_file"

2. EXECUTE: Tool'u çağır
   - Parametreleri DOĞRU yaz
   - old_str'i AYNEN kopyala

3. VERIFY: Sonuç doğru mu?
   - Tool output'u oku
   - Başarılı mı kontrol et
```

### 5. 🚀 En İyi Çözüm: Prompt Templates

**Dosya düzenleme için özel prompt:**

```python
EDIT_FILE_TEMPLATE = """
Dosya düzenleme adımları:

ADIM 1: Dosyayı oku
```tool
{"name": "view", "arguments": {"path": "{file_path}"}}
```

ADIM 2: İçeriği incele ve değiştirilecek kısmı belirle

ADIM 3: str_replace ile düzenle
```tool
{{
    "name": "str_replace",
    "arguments": {{
        "path": "{file_path}",
        "old_str": "...",  // Dosyadan AYNEN kopyala
        "new_str": "..."   // Yeni hali
    }}
}}
```

ADIM 4: Değişikliği doğrula (view ile tekrar oku)
"""
```

### 6. 🎓 Model-Specific Tuning

**qwen2.5-coder:7b için özel ayarlar:**

```python
# constants.py veya config.py
SMALL_MODEL_ENHANCEMENTS = {
    "qwen2.5-coder:7b": {
        "verbose_tool_descriptions": True,
        "include_examples": True,
        "enforce_chain_of_thought": True,
        "temperature": 0.1,  # Daha deterministik
        "max_tokens": 4096,
    }
}
```

### 7. 🔍 Debug Helper: Tool Usage Logger

**Tool kullanımını logla:**

```python
class ToolUsageTracker:
    """7B modellerin tool kullanımını analiz et"""

    def __init__(self):
        self.usage = defaultdict(int)
        self.failures = defaultdict(list)

    def log_tool_call(self, tool_name, success, error=None):
        self.usage[tool_name] += 1
        if not success:
            self.failures[tool_name].append(error)

    def get_suggestions(self):
        """Model hangi tool'da zorlanıyor?"""
        return {
            "most_used": max(self.usage, key=self.usage.get),
            "most_failed": max(self.failures, key=lambda k: len(self.failures[k])),
            "success_rate": {
                tool: 1 - (len(self.failures[tool]) / self.usage[tool])
                for tool in self.usage
            }
        }
```

### 8. 🛠️ Alternatif: Simplified str_replace

**7B modeller için basitleştirilmiş versiyon:**

```python
class SimpleEditTool(Tool):
    """Daha kolay kullanımlı edit tool - 7B modeller için"""

    name = "edit_line"
    description = """Dosyada tek satır düzelt

    KULLANIM:
    {
        "name": "edit_line",
        "arguments": {
            "path": "file.py",
            "line_number": 5,  # Hangi satır
            "new_content": "print('Hello')"  # Yeni içerik
        }
    }
    """
```

## Öncelikli Uygulama Sırası

### Hemen Yapılabilecekler (5 dakika):

1. ✅ System prompt'a str_replace ÖRNEK ekle
2. ✅ Tool descriptions'a KULLANIM bölümü ekle
3. ✅ Temperature'ü 0.0'dan 0.1'e çıkar (az randomness)

### Orta Vadeli (1 saat):

4. ⚡ Chain of thought enforcement ekle
5. ⚡ Tool usage tracker implement et
6. ⚡ Model-specific ayarlar

### Uzun Vadeli (1+ gün):

7. 🔧 Alternative simplified tools
8. 🔧 Fine-tuning için dataset toplama
9. 🔧 Tool usage analytics dashboard

## Test Senaryoları

### Senaryo 1: Basit Düzenleme
```
User: "main.py dosyasındaki 'hello' kelimesini 'hi' yap"

Beklenen:
1. view main.py
2. str_replace ile değiştir
3. view ile doğrula
```

### Senaryo 2: Çok Satırlı Düzenleme
```
User: "config.py'deki port numarasını 8000'den 3000'e değiştir"

Beklenen:
1. view config.py
2. Tam satırı bul: PORT = 8000
3. str_replace ile: PORT = 3000
```

### Senaryo 3: Hata Recovery
```
User: "test.py'de fonksiyon adını değiştir"

Model yanlış old_str kullanırsa:
1. Error alacak: "String not found"
2. view ile tekrar okuyacak
3. Doğru string'i bulup tekrar deneyecek
```

## Metrikler

Başarılı iyileştirme için takip edilecek:

- **Tool Usage Success Rate**: str_replace başarı oranı > %80
- **First Attempt Success**: İlk denemede başarı > %60
- **Average Iterations**: Dosya düzenleme için ortalama < 2 iteration
- **Error Recovery Rate**: Hatadan kurtarma > %90

## Sonuç

**En Etkili 3 İyileştirme:**

1. 📚 **Few-Shot Examples** - System prompt'a somut örnekler
2. 🎯 **Chain of Thought** - Adım adım düşünmeyi zorunlu kıl
3. 🔧 **Better Tool Descriptions** - Daha açık, örnekli açıklamalar

**Beklenen Sonuç:**
- %30-40 daha fazla başarılı tool kullanımı
- Daha az iteration gerektiren işlemler
- Model'in kendi hatalarını düzeltebilmesi

---

**Not**: 32B model kullanırsanız bu sorunların çoğu otomatik çözülür, ama 7B ile de %80+ başarı mümkün!
