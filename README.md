# Local Agent CLI 🤖

Claude Code mimarisini açık kaynak modeller için implemente eden agentic coding assistant.

## 🎯 Neden Bu Proje?

Claude Code'un başarısının arkasında yatan mimari prensipleri açık kaynak modeller ile kullanmak için:

- **Infinite Agentic Loop**: Görev tamamlanana kadar düşün → tool kullan → gözlemle → tekrarla
- **Minimal Ama Güçlü Tool Seti**: bash, view, str_replace, create_file
- **Akıllı Context Yönetimi**: Token limitleri içinde kalarak uzun session'lar
- **Error Recovery**: Hatalardan öğren ve farklı yaklaşım dene

## 🚀 Hızlı Başlangıç

### Kurulum

```bash
# Ollama kurulu olmalı
curl -fsSL https://ollama.com/install.sh | sh

# Model indir (önerilen)
ollama pull qwen2.5-coder:32b

# Projeyi kur
pip install -e .
```

### Kullanım

```bash
# Interactive mode
local-agent

# Single prompt
local-agent "Create a REST API with FastAPI"

# Farklı model
local-agent -m deepseek-coder-v2:16b "Fix the bug in main.py"

# OpenAI-compatible API (LM Studio, vLLM, etc.)
local-agent -p openai -u http://localhost:1234/v1 "Analyze this code"
```

## 🏗️ Mimari

```
┌─────────────────────────────────────────────────────────────┐
│                        CLI Interface                         │
│  (Rich terminal UI, streaming, progress indicators)          │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                          Agent                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                   Agentic Loop                       │    │
│  │  User Input → Think → Tool Use → Observe → Repeat   │    │
│  └─────────────────────────────────────────────────────┘    │
│                          │                                   │
│  ┌───────────────────────▼─────────────────────────────┐    │
│  │              Context Manager                         │    │
│  │  - Token counting                                    │    │
│  │  - Conversation compaction                           │    │
│  │  - Message history                                   │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────┬───────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          │               │               │
┌─────────▼─────┐ ┌───────▼──────┐ ┌──────▼──────┐
│  Tool Registry │ │   Provider   │ │   Skills    │
│  - bash        │ │  - Ollama    │ │  (optional) │
│  - view        │ │  - OpenAI    │ │             │
│  - str_replace │ │  - Anthropic │ │             │
│  - create_file │ │              │ │             │
└────────────────┘ └──────────────┘ └─────────────┘
```

## 🛠️ Tool Sistemi

### bash
```python
# Her türlü shell komutu
await bash.execute(command="ls -la")
await bash.execute(command="pip install pandas")
await bash.execute(command="python test.py")
```

### view
```python
# Dosya içeriği (line numbers ile)
await view.execute(path="main.py")
await view.execute(path="main.py", line_range=[10, 50])

# Dizin yapısı
await view.execute(path="./src")
```

### str_replace
```python
# Hassas düzenleme - string dosyada unique olmalı
await str_replace.execute(
    path="main.py",
    old_str="def old_function():\n    pass",
    new_str="def new_function():\n    return 42"
)
```

### create_file
```python
# Yeni dosya oluştur
await create_file.execute(
    path="utils.py",
    content="def helper():\n    return 'hello'"
)
```

## 🔧 Provider'lar

### Ollama (Önerilen)
```bash
# Ollama ile local model
local-agent -p ollama -m qwen2.5-coder:32b
local-agent -p ollama -m deepseek-coder-v2:16b
local-agent -p ollama -m codellama:34b
```

### OpenAI-Compatible
```bash
# LM Studio
local-agent -p openai -u http://localhost:1234/v1

# vLLM
local-agent -p openai -u http://localhost:8000/v1

# text-generation-webui
local-agent -p openai -u http://localhost:5000/v1
```

### Anthropic (API key gerekli)
```bash
export ANTHROPIC_API_KEY=sk-...
local-agent -p anthropic -m claude-sonnet-4-20250514
```

## 📊 Model Karşılaştırması

| Model | Boyut | Tool Calling | Kod Kalitesi | Hız |
|-------|-------|--------------|--------------|-----|
| qwen2.5-coder:32b | 32B | Native ✅ | ⭐⭐⭐⭐⭐ | Orta |
| deepseek-coder-v2:16b | 16B | Native ✅ | ⭐⭐⭐⭐ | Hızlı |
| codellama:34b | 34B | Prompt-based | ⭐⭐⭐⭐ | Yavaş |
| llama3.2:latest | 8B | Native ✅ | ⭐⭐⭐ | Çok Hızlı |

## 🎨 CLI Komutları

```
/help           - Yardım göster
/quit, /exit    - Çık
/clear          - Context temizle
/stats          - Context istatistikleri
/model [name]   - Model değiştir
/tools          - Tool listesi
/cd [path]      - Çalışma dizini değiştir
/compact        - Context'i manuel compact et
```

## 🔬 Programmatic Kullanım

```python
import asyncio
from src import Agent, AgentConfig, create_provider, create_default_tools

async def main():
    # Components
    config = AgentConfig(
        model_name="qwen2.5-coder:32b",
        max_iterations=50,
        working_dir="./my-project"
    )
    
    provider = create_provider("ollama", model=config.model_name)
    tools = create_default_tools(working_dir=config.working_dir)
    
    # Agent
    agent = Agent(config, provider, tools)
    
    # Callbacks (optional)
    agent.set_callbacks(
        on_tool_start=lambda name, args: print(f"Running {name}..."),
        on_tool_end=lambda name, result: print(f"Done: {result.success}")
    )
    
    # Run
    async for response in agent.run("Create a FastAPI server with CRUD endpoints"):
        if response.tool_calls:
            print(f"Iteration {response.iteration}: {len(response.tool_calls)} tools")
        else:
            print(f"Response: {response.content[:100]}...")
    
    await provider.close()

asyncio.run(main())
```

## 🤝 Katkıda Bulunma

1. Fork yapın
2. Feature branch oluşturun (`git checkout -b feature/amazing-feature`)
3. Commit yapın (`git commit -m 'Add amazing feature'`)
4. Push yapın (`git push origin feature/amazing-feature`)
5. Pull Request açın

## 📝 Lisans

MIT License - detaylar için [LICENSE](LICENSE) dosyasına bakın.

## 🙏 Teşekkürler

- [Anthropic](https://anthropic.com) - Claude Code mimarisi ilhamı
- [Ollama](https://ollama.com) - Local model çalıştırma
- [Qwen Team](https://github.com/QwenLM) - Mükemmel kod modeli
- [Rich](https://rich.readthedocs.io) - Güzel terminal UI

---

**Kardelen Yazılım** tarafından ❤️ ile yapıldı.
