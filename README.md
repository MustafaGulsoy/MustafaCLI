# Mustafa CLI

**Claude Code mimarisini local LLM'lerle kullanan otonom AI kodlama asistani.**

Terminalde `mustafa` yazarak her dizinde kullanabilirsin. Ollama uzerinden calisan local modeller ile dosya okuma, duzenleme, komut calistirma ve kod analizi yapar — internet veya API key gerektirmez.

---

## Ne Yapar?

Mustafa CLI, Claude Code'un calisma mantigi ile local open-source modelleri birlestiren bir agentic CLI aracidir:

- **Otonom Calisma**: Soru sormak yerine once dosyalari inceler, komutu calistirir, sonra rapor sunar
- **8 Tool**: bash, view, str_replace, create_file, git, search, ast_analysis, generate_tests
- **Model Secimi**: Baslangicta Ollama'daki tum modelleri listeler, tool-capable olanlari isaretler
- **Canli Spinner**: Dusunurken "Thinking", "Vibing", "Reasoning" gibi durum mesajlari gosterir
- **MCP Entegrasyonu**: Neo4j, FreeCAD, Gmsh, CalculiX MCP server'lari ile muhendislik analizi (SAT-MAESTRO plugin)
- **Windows + Linux**: Git Bash uzerinden tum Unix komutlari Windows'ta da calisir

---

## Kurulum

### Gereksinimler
- Python 3.10+
- [Ollama](https://ollama.ai) kurulu ve calisiyor
- Node.js (global `mustafa` komutu icin)
- Git for Windows (Windows'ta bash komutlari icin)

### Adimlar

```bash
git clone https://github.com/MustafaGulsoy/MustafaCLI.git
cd MustafaCLI

python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

pip install -r requirements.txt

# Model indir
ollama pull qwen3:8b

# Global komut olarak kur
npm link
```

---

## Kullanim

```bash
# Interaktif mod — model secim menusu acilir
mustafa

# Tek komut
mustafa -m qwen3:8b "bu projedeki dosyalari listele"

# Belirli dizinde calistir
mustafa -d /path/to/project "rapor cikar"

# MCP server durumunu gor
mustafa --mcp-status
```

### Interaktif Komutlar

| Komut | Islem |
|-------|-------|
| `/help` | Yardim |
| `/model qwen3:8b` | Model degistir |
| `/tools` | Tool listesi |
| `/cd /path` | Dizin degistir |
| `/stats` | Context istatistikleri |
| `/clear` | Konusmayi sifirla |
| `/quit` | Cikis |

---

## Araclar

| Tool | Aciklama |
|------|----------|
| `bash` | Shell komutlari calistir (ls, git, python, npm vb.) |
| `view` | Dosya iceriklerini oku, satir araligi belirle |
| `str_replace` | Dosyalarda metin degistir (atomic editing) |
| `create_file` | Yeni dosya olustur |
| `git` | Git status, diff, log, blame, show |
| `search` | Kod tabaninda semantik arama |
| `ast_analysis` | Python dosya yapisini analiz et (class, function, import) |
| `generate_tests` | pytest test sablonu olustur |

---

## Mimari

```
mustafa (npm global) --> bin/mustafa.js --> python -m src.cli
                                              |
                                              v
                                        Agent Loop
                                     (think -> tool -> observe -> repeat)
                                              |
                                    +---------+---------+
                                    |         |         |
                                Provider   Tools    Context
                                (Ollama)  (8 tool)  (compaction)
                                    |
                              Ollama API
                           (qwen3, llama3, mistral...)
```

### Desteklenen Providerlar
- **Ollama** (varsayilan) — local modeller
- **OpenAI Compatible** — LM Studio, vLLM, text-generation-webui
- **Anthropic** — Claude API (API key gerekir)

---

## SAT-MAESTRO Plugin

Uydu muhendisligi icin ozel plugin. MCP server mimarisi ile:

- **Elektrik Analizi**: ERC, net check, derating, connector validation
- **Yapisal Analiz**: Kutle butcesi, agirlik merkezi, montaj agaci
- **Termal Analiz**: Lumped-parameter solver, orbital dongu, sicaklik limitleri
- **Mekanizma**: Deployment sequence, kinematik analiz, tork marjini
- **Titresim**: Modal analiz, random vibrasyon, sok (SRS)
- **Capraz Disiplin**: Elektrik-termal, kutle-termal korelasyon

53 ECSS kurali (E-ST-32C, E-ST-31C, E-ST-33C, E-HB-32-26A) ile uyumluluk kontrolu.

---

## Yapilandirma

`.env` dosyasi ile:

```bash
AGENT_MODEL_NAME=qwen3:8b       # Varsayilan model
AGENT_TEMPERATURE=0.0            # Deterministik cikti
AGENT_MAX_ITERATIONS=100         # Maksimum dongu
AGENT_MAX_TOKENS=8192            # Response token limiti
```

---

## Lisans

MIT License - Mustafa (Kardelen Yazilim)
