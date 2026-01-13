# 🚀 Web UI Quick Start Guide

## Web Arayüzü Hazır! 🎉

FastAPI backend ve Angular frontend tamamen implement edildi!

---

## 📦 Oluşturulan Dosyalar

### Backend (FastAPI) ✅
```
src/api/
├── __init__.py          # Module init
├── main.py              # FastAPI app + WebSocket (270 lines)
├── models.py            # Pydantic models (80 lines)
└── sessions.py          # Session management (150 lines)
```

### Frontend (Angular) ✅
```
frontend/
├── src/
│   ├── app/
│   │   ├── components/
│   │   │   └── chat/
│   │   │       ├── chat.component.ts      # Main chat component
│   │   │       ├── chat.component.html    # Template (150 lines)
│   │   │       └── chat.component.css     # Styles (400 lines)
│   │   ├── services/
│   │   │   ├── api.service.ts             # REST API integration
│   │   │   └── websocket.service.ts       # WebSocket service
│   │   ├── models/
│   │   │   └── models.ts                  # TypeScript interfaces
│   │   └── app.component.ts               # Root component
│   ├── environments/
│   │   └── environment.ts                 # Configuration
│   ├── main.ts                            # Bootstrap
│   ├── styles.css                         # Global styles
│   └── index.html                         # HTML entry
├── package.json                           # Dependencies
├── angular.json                           # Angular config
├── tsconfig.json                          # TypeScript config
└── tsconfig.app.json                      # App TypeScript config
```

---

## 🚀 Hemen Başla! (5 Dakika)

### Adım 1: Backend'i Başlat

```bash
# Terminal 1
cd D:\Private\Projeler\Python\MustafaCLI

# Activate venv
venv\Scripts\activate

# Install dependencies (if not done)
pip install fastapi uvicorn[standard] websockets python-multipart

# Start backend
python -m src.api.main
```

**Output görmelisin:**
```
🚀 MustafaCLI API starting...
📡 WebSocket endpoint: ws://localhost:8000/ws/{session_id}
🌐 REST API: http://localhost:8000/docs
INFO:     Started server process
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Adım 2: Frontend'i Başlat

```bash
# Terminal 2 (yeni terminal aç)
cd D:\Private\Projeler\Python\MustafaCLI\frontend

# Install Node.js dependencies
npm install

# Start Angular dev server
npm start
```

**Output görmelisin:**
```
✔ Browser application bundle generation complete.
Initial Chunk Files | Names         |  Raw Size
main.js             | main          | XXX.XX kB

Application bundle generation complete. [X.XXX seconds]
Watch mode enabled. Watching for file changes...
  ➜  Local:   http://localhost:4200/
```

### Adım 3: Tarayıcıda Aç

```
http://localhost:4200
```

**Görmelisin:**
- Modern dark theme chat interface
- "Connected" status badge (yeşil)
- "RAG" toggle checkbox
- Message input area
- Welcome message

---

## ✨ Özellikler

### Chat Interface
- ✅ Real-time WebSocket streaming
- ✅ Message history
- ✅ User/Assistant/System message types
- ✅ Tool calls görüntüleme
- ✅ Tool results ile success/fail badges
- ✅ Iteration tracking
- ✅ Timestamps
- ✅ Auto-scroll
- ✅ Loading indicator
- ✅ Cancel operation

### UI Features
- ✅ Modern dark theme (VS Code style)
- ✅ Syntax highlighted code blocks
- ✅ Responsive design
- ✅ Connection status indicator
- ✅ RAG toggle
- ✅ Clear chat button
- ✅ Enter to send (Shift+Enter for new line)

### Technical
- ✅ Standalone Angular components
- ✅ RxJS for reactive programming
- ✅ TypeScript strict mode
- ✅ HTTP Client integration
- ✅ WebSocket service with reconnection
- ✅ Environment-based configuration

---

## 🎯 Kullanım Örnekleri

### Example 1: Basit Soru
```
You: "list files in current directory"

Agent: [Uses view tool]
📊 Results:
  ✓ view - Success
  Output: [file list...]
```

### Example 2: RAG ile Kod Bulma
```
You: "where is the tool execution code?"

[RAG] Found 3 relevant code chunks:
  - src/core/agent.py:280 (95%)

Agent: Tool execution is in src/core/agent.py:280...
```

### Example 3: Git İşlemleri
```
You: "show last 5 commits"

Agent: [Uses git tool]
🔧 Tool Calls:
  git: {"command": "log", "args": "--oneline -5"}

📊 Results:
  ✓ git - Success
  Output:
    04de4cc feat: Major upgrade
    6b67a5c docs: Comprehensive roadmap
    ...
```

---

## 🎨 UI Görünümü

### Header
```
🤖 MustafaCLI Agent    [Connected]    [✓ RAG]  [Clear]
```

### Chat Messages
```
┌─────────────────────────────────────────────┐
│ 👤 You                      2:30 PM         │
│ list files in current directory             │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│ 🤖 Agent                    2:30 PM  Iter 1 │
│ [Uses view tool to list files...]           │
│                                              │
│ 🔧 Tool Calls:                              │
│   view: {"path": "."}                       │
│                                              │
│ 📊 Results:                                  │
│   ✓ view - Success                          │
│   Output: [files listed]                    │
└─────────────────────────────────────────────┘
```

### Input Area
```
┌─────────────────────────────────────────────┐
│ Type your message...                        │
│ (Enter to send, Shift+Enter for new line)  │
│                                 [Send]      │
└─────────────────────────────────────────────┘
```

---

## 🧪 Test Senaryoları

### Test 1: Connection Check
```bash
# Browser'da
http://localhost:4200

# Görmelisin:
- ⚙️ System: Connected to MustafaCLI Agent
- Status: Connected (green)
```

### Test 2: Simple Command
```
Message: "hello"
Expected: Agent responds with greeting
```

### Test 3: Tool Usage
```
Message: "list files"
Expected:
- Tool call: view
- Tool result with file list
- Success badge
```

### Test 4: RAG Toggle
```
1. Click RAG toggle
2. New session created
3. Chat clears
4. Welcome message shows new RAG status
```

### Test 5: Cancel Operation
```
1. Send long-running task
2. Click Cancel
3. Loading stops
```

---

## 🔧 Troubleshooting

### Problem: "Cannot GET /"
**Sebep:** Backend çalışmıyor
**Çözüm:**
```bash
python -m src.api.main
```

### Problem: "WebSocket connection failed"
**Sebep:** Backend URL yanlış veya backend çalışmıyor
**Çözüm:**
1. Backend'in 8000 portunda çalıştığını kontrol et
2. `frontend/src/environments/environment.ts` dosyasını kontrol et

### Problem: "npm: command not found"
**Sebep:** Node.js yüklü değil
**Çözüm:**
```bash
# Node.js indir ve yükle
https://nodejs.org/

# Verify
node --version
npm --version
```

### Problem: Angular derleme hatası
**Çözüm:**
```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
```

### Problem: CORS hatası
**Sebep:** Backend CORS yapılandırması
**Çözüm:** `src/api/main.py` dosyasında CORS origins kontrolü:
```python
allow_origins=[
    "http://localhost:4200",  # Angular dev server
]
```

---

## 📊 API Test (Opsiyonel)

### Swagger UI ile Test
```
http://localhost:8000/docs
```

**Test Endpoints:**
1. `GET /health` - Health check
2. `POST /api/sessions` - Create session
3. `POST /api/chat` - Send message (non-streaming)

### cURL ile Test
```bash
# Health check
curl http://localhost:8000/health

# Create session
curl -X POST http://localhost:8000/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"working_dir": ".", "enable_rag": true}'

# List sessions
curl http://localhost:8000/api/sessions
```

---

## 🚀 Production Build

### Frontend Build
```bash
cd frontend
npm run build

# Output: frontend/dist/mustafa-cli-ui/
```

### Serve Production
```bash
# Install serve
npm install -g serve

# Serve built files
serve -s dist/mustafa-cli-ui -l 4200
```

---

## 📝 Konfigürasyon

### Backend Port Değiştirme
```python
# src/api/main.py (end of file)
uvicorn.run(
    "src.api.main:app",
    host="0.0.0.0",
    port=8080,  # Change here
    reload=True
)
```

### Frontend API URL Değiştirme
```typescript
// frontend/src/environments/environment.ts
export const environment = {
  production: false,
  apiUrl: 'http://localhost:8080',  // Change here
  wsUrl: 'ws://localhost:8080'       // Change here
};
```

---

## 🎓 Kod Yapısı

### Component Lifecycle
```typescript
ngOnInit()
  └─> initializeSession()
      ├─> apiService.createSession()  // REST
      ├─> wsService.connect()         // WebSocket
      └─> Subscribe to messages

User sends message
  └─> sendMessage()
      ├─> Add to chat
      ├─> wsService.sendMessage()
      └─> Set loading

WebSocket receives
  └─> handleWebSocketMessage()
      ├─> 'response' → Update chat
      ├─> 'complete' → Stop loading
      └─> 'error' → Show error
```

### Service Pattern
```typescript
ApiService        → REST endpoints
WebSocketService  → Real-time streaming

ChatComponent uses both:
- ApiService for session management
- WebSocketService for messaging
```

---

## 📦 Dependencies Açıklaması

### Backend
```txt
fastapi==0.109.0         # Modern web framework
uvicorn[standard]==0.27.0  # ASGI server
websockets==12.0         # WebSocket support
python-multipart==0.0.6  # File upload support
```

### Frontend
```json
{
  "@angular/core": "^17.0.0",      // Framework
  "@angular/common": "^17.0.0",    // Common utilities
  "@angular/forms": "^17.0.0",     // Form handling
  "rxjs": "~7.8.0",                // Reactive programming
  "prismjs": "^1.29.0",            // Syntax highlighting
  "marked": "^11.0.0"              // Markdown parsing
}
```

---

## ✅ Checklist

- [ ] Backend çalışıyor (port 8000)
- [ ] Frontend çalışıyor (port 4200)
- [ ] Swagger UI açılıyor (/docs)
- [ ] Browser'da UI görünüyor
- [ ] "Connected" status gösteriyor
- [ ] Mesaj gönderebiliyorum
- [ ] Agent cevap veriyor
- [ ] Tool calls görünüyor
- [ ] Tool results görünüyor
- [ ] RAG toggle çalışıyor
- [ ] Clear button çalışıyor

---

## 🎉 Başarıyla Tamamlandı!

**İstatistikler:**
- Backend: 500+ satır Python
- Frontend: 1,000+ satır TypeScript/HTML/CSS
- Total: ~1,500 satır kod
- Özellikler: 15+ feature
- Süre: Tam implementasyon

**Artık kullanabilirsin:**
```bash
# Terminal 1
python -m src.api.main

# Terminal 2
cd frontend && npm start

# Browser
http://localhost:4200
```

**Enjoy! 🚀✨**
