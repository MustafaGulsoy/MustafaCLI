# 🌐 Web UI Guide - FastAPI + Angular

## MustafaCLI Web Interface

Modern web UI for interacting with your AI coding agent through a beautiful, real-time interface.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────┐
│                  FRONTEND                       │
│         Angular 17 (Port 4200)                  │
│                                                 │
│  Components:                                    │
│  - Chat Interface                              │
│  - Code Viewer (Syntax Highlighting)          │
│  - Tool Execution Monitor                     │
│  - Session Manager                            │
│                                                 │
│  Services:                                      │
│  - WebSocket Service (Real-time)              │
│  - API Service (REST)                         │
│  - State Management                           │
└─────────────────────────────────────────────────┘
                      ↕ HTTP/WebSocket
┌─────────────────────────────────────────────────┐
│                   BACKEND                       │
│         FastAPI (Port 8000)                     │
│                                                 │
│  Endpoints:                                     │
│  - REST API (/api/...)                        │
│  - WebSocket (/ws/{session_id})               │
│  - Health Check (/health)                     │
│                                                 │
│  Features:                                      │
│  - Session Management                         │
│  - Real-time Streaming                        │
│  - CORS for Angular                           │
│  - Multiple concurrent sessions               │
└─────────────────────────────────────────────────┘
                      ↕
┌─────────────────────────────────────────────────┐
│              AGENT SYSTEM                       │
│  - Agent with RAG                               │
│  - Tool Registry                                │
│  - Context Caching                             │
└─────────────────────────────────────────────────┘
```

---

## 📦 What's Been Created

### Backend (FastAPI) ✅

**Location:** `src/api/`

**Files:**
```
src/api/
├── __init__.py          # Module initialization
├── main.py              # FastAPI app with WebSocket
├── models.py            # Pydantic models
└── sessions.py          # Session management
```

**Features:**
- ✅ Real-time WebSocket streaming
- ✅ REST API endpoints
- ✅ Session management (multi-user)
- ✅ CORS configuration for Angular
- ✅ Health checks
- ✅ RAG integration support

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | API info |
| GET | `/health` | Health check |
| GET | `/docs` | Swagger UI |
| POST | `/api/sessions` | Create session |
| GET | `/api/sessions` | List sessions |
| GET | `/api/sessions/{id}` | Get session |
| DELETE | `/api/sessions/{id}` | Delete session |
| POST | `/api/chat` | Send message (non-streaming) |
| WS | `/ws/{session_id}` | WebSocket streaming |

### Frontend (Angular) 🚧

**Location:** `frontend/`

**Files Created:**
```
frontend/
├── package.json         # Dependencies
├── angular.json         # Angular config
├── tsconfig.json        # TypeScript config
├── src/
│   ├── index.html       # Main HTML
│   └── (structure ready for components)
```

**Ready for Implementation:**
- Chat interface component
- Code viewer with syntax highlighting
- WebSocket service
- API service
- State management

---

## 🚀 Quick Start

### 1. Setup Backend (FastAPI)

```bash
# Install dependencies
pip install fastapi uvicorn[standard] websockets python-multipart

# Or update from requirements.txt
pip install -r requirements.txt
```

**Start Backend:**
```bash
# From project root
python -m src.api.main

# Or with uvicorn directly
uvicorn src.api.main:app --reload --port 8000
```

**Verify Backend:**
```bash
# Open browser
http://localhost:8000          # API info
http://localhost:8000/docs     # Swagger UI
http://localhost:8000/health   # Health check
```

### 2. Setup Frontend (Angular)

```bash
cd frontend

# Install Node.js dependencies
npm install

# Start development server
npm start

# Or with ng
ng serve
```

**Verify Frontend:**
```bash
# Open browser
http://localhost:4200
```

---

## 🔌 WebSocket Protocol

### Client → Server

**Send Message:**
```json
{
  "type": "message",
  "content": "explain how agent works"
}
```

**Keep-Alive:**
```json
{
  "type": "ping"
}
```

**Cancel:**
```json
{
  "type": "cancel"
}
```

### Server → Client

**Connected:**
```json
{
  "type": "connected",
  "session_id": "uuid...",
  "working_dir": ".",
  "rag_enabled": true
}
```

**Response Chunk:**
```json
{
  "type": "response",
  "data": {
    "content": "...",
    "state": "thinking",
    "iteration": 1,
    "tool_calls": [...],
    "tool_results": [...]
  }
}
```

**Complete:**
```json
{
  "type": "complete",
  "data": {
    "iterations": 3,
    "duration_ms": 2500
  }
}
```

**Error:**
```json
{
  "type": "error",
  "error": "error message"
}
```

---

## 💻 API Usage Examples

### Create Session

```bash
curl -X POST http://localhost:8000/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"working_dir": ".", "enable_rag": true}'
```

**Response:**
```json
{
  "session_id": "abc-123",
  "created_at": "2026-01-13T12:00:00",
  "working_dir": ".",
  "rag_enabled": true,
  "active": true
}
```

### Send Message (Non-Streaming)

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "abc-123",
    "message": "list files in current directory"
  }'
```

### WebSocket (JavaScript Example)

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/abc-123');

ws.onopen = () => {
  console.log('Connected');

  // Send message
  ws.send(JSON.stringify({
    type: 'message',
    content: 'explain how agent works'
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);

  if (data.type === 'response') {
    console.log('Agent:', data.data.content);
  } else if (data.type === 'complete') {
    console.log('Done in', data.data.duration_ms, 'ms');
  }
};
```

---

## 🎨 Frontend Components (To Be Implemented)

### 1. Chat Component

**Features:**
- Message history
- User input
- Real-time streaming responses
- Tool execution indicators
- Markdown rendering
- Code syntax highlighting

**Location:** `frontend/src/app/components/chat/`

### 2. Code Viewer Component

**Features:**
- Syntax highlighting (Prism.js)
- Line numbers
- Copy to clipboard
- File path display
- Language detection

**Location:** `frontend/src/app/components/code-viewer/`

### 3. Tool Monitor Component

**Features:**
- Active tool calls
- Tool results
- Success/failure indicators
- Execution time
- Output preview

**Location:** `frontend/src/app/components/tool-monitor/`

### 4. Session Manager Component

**Features:**
- Create/delete sessions
- Switch between sessions
- Session info display
- RAG toggle

**Location:** `frontend/src/app/components/session-manager/`

---

## 🔧 Configuration

### Backend Configuration

**Environment Variables:**
```bash
# .env
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=http://localhost:4200,http://localhost:8080
MAX_SESSIONS=10
SESSION_TIMEOUT=3600
```

### Frontend Configuration

**environment.ts:**
```typescript
export const environment = {
  production: false,
  apiUrl: 'http://localhost:8000',
  wsUrl: 'ws://localhost:8000'
};
```

---

## 🐳 Docker Support

### Dockerfile (Backend)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY .env .env

EXPOSE 8000

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Dockerfile (Frontend)

```dockerfile
FROM node:20-alpine AS build

WORKDIR /app

COPY frontend/package*.json ./
RUN npm install

COPY frontend/ .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist/mustafa-cli-ui /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

### docker-compose.yml

```yaml
version: '3.8'

services:
  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    ports:
      - "8000:8000"
    volumes:
      - ./src:/app/src
      - ./.rag_db:/app/.rag_db
    environment:
      - AGENT_MODEL_NAME=qwen2.5-coder:7b

  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
    ports:
      - "4200:80"
    depends_on:
      - backend
```

---

## 📊 Features Matrix

| Feature | Backend | Frontend | Status |
|---------|---------|----------|--------|
| REST API | ✅ | - | Complete |
| WebSocket | ✅ | 🚧 | Backend Done |
| Session Management | ✅ | 🚧 | Backend Done |
| Real-time Streaming | ✅ | 🚧 | Backend Done |
| RAG Integration | ✅ | 🚧 | Backend Done |
| Chat Interface | - | 🚧 | Pending |
| Code Viewer | - | 🚧 | Pending |
| Tool Monitor | - | 🚧 | Pending |
| Syntax Highlighting | - | 🚧 | Pending |
| Multiple Sessions | ✅ | 🚧 | Backend Done |

---

## 🧪 Testing

### Backend Tests

```bash
# Test health endpoint
curl http://localhost:8000/health

# Test session creation
curl -X POST http://localhost:8000/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"working_dir": "."}'

# Interactive API docs
open http://localhost:8000/docs
```

### WebSocket Test

```python
import asyncio
import websockets
import json

async def test_websocket():
    uri = "ws://localhost:8000/ws/test-session"

    async with websockets.connect(uri) as websocket:
        # Send message
        await websocket.send(json.dumps({
            "type": "message",
            "content": "list files"
        }))

        # Receive responses
        while True:
            response = await websocket.recv()
            data = json.loads(response)
            print(data)

            if data.get("type") == "complete":
                break

asyncio.run(test_websocket())
```

---

## 🔐 Security Considerations

### Implemented:
- ✅ CORS configuration
- ✅ Session isolation
- ✅ Input validation (Pydantic)
- ✅ WebSocket authentication (session-based)

### To Implement:
- 🔲 JWT authentication
- 🔲 Rate limiting
- 🔲 Request size limits
- 🔲 API keys
- 🔲 HTTPS in production

---

## 🚧 Next Steps

### Immediate (Angular Implementation):

1. **WebSocket Service** (1 hour)
   ```typescript
   // frontend/src/app/services/websocket.service.ts
   ```

2. **API Service** (30 min)
   ```typescript
   // frontend/src/app/services/api.service.ts
   ```

3. **Chat Component** (2 hours)
   ```typescript
   // frontend/src/app/components/chat/chat.component.ts
   ```

4. **Code Viewer Component** (1 hour)
   ```typescript
   // frontend/src/app/components/code-viewer/code-viewer.component.ts
   ```

### Future Enhancements:

- 📊 Usage analytics dashboard
- 👥 Multi-user collaboration
- 💾 Conversation history
- 🎨 Theme customization
- 📱 Mobile responsive design
- 🔔 Browser notifications
- 📁 File browser integration
- 🔍 Search in conversations

---

## 📚 Resources

### FastAPI:
- Docs: https://fastapi.tiangolo.com/
- WebSocket: https://fastapi.tiangolo.com/advanced/websockets/

### Angular:
- Docs: https://angular.io/docs
- WebSocket: https://rxjs.dev/api/webSocket/webSocket

### Libraries:
- Prism.js (Syntax): https://prismjs.com/
- Marked (Markdown): https://marked.js.org/

---

## 🐛 Troubleshooting

### Backend Issues

**Issue:** "Address already in use"
```bash
# Kill process on port 8000
# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Linux/Mac
lsof -ti:8000 | xargs kill -9
```

**Issue:** "WebSocket connection failed"
- Check CORS settings in `main.py`
- Verify session exists
- Check firewall settings

### Frontend Issues

**Issue:** "npm install fails"
```bash
# Clear cache and retry
npm cache clean --force
rm -rf node_modules package-lock.json
npm install
```

**Issue:** "Cannot connect to backend"
- Verify backend is running on port 8000
- Check CORS configuration
- Verify API URL in environment

---

## ✅ Quick Test Checklist

- [ ] Backend starts without errors
- [ ] `/health` endpoint returns 200
- [ ] Swagger UI accessible at `/docs`
- [ ] Can create session via API
- [ ] WebSocket connects successfully
- [ ] Can send/receive messages
- [ ] Frontend builds without errors
- [ ] Angular app loads in browser
- [ ] Can connect to backend from frontend

---

**Created:** 2026-01-13
**Author:** Mustafa (Kardelen Yazılım)
**Version:** 0.4.0
**Status:** Backend Complete, Frontend Structure Ready

🚀 **Ready to build the full UI!**
