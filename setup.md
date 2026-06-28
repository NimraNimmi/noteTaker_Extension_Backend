# Transcription Backend Setup Guide

## 1. Local Development

### Prerequisites
- Python 3.9+
- FFmpeg installed on your system
  - **macOS:** `brew install ffmpeg`
  - **Ubuntu/Debian:** `sudo apt-get install ffmpeg`
  - **Windows:** Download from https://ffmpeg.org/download.html

### Installation

```bash
# Clone or create your project directory
cd transcription-backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Run Locally

```bash
# Set your Groq API key
export GROQ_API_KEY="gsk_..."  # On Windows: set GROQ_API_KEY=gsk_...

# Start the server
python transcription_server.py
# or
uvicorn transcription_server:app --reload --port 8000
```

Server will be available at `http://localhost:8000`

Test it:
```bash
curl http://localhost:8000/health
# Should return: {"status":"ok"}
```

---

## 2. Extension Configuration

### Update manifest.json

Add backend URL to content security policy (if you have one):

```json
{
  "permissions": [
    "storage",
    "webRequest"
  ],
  "host_permissions": [
    "http://localhost:8000/*",
    "https://your-backend.com/*"  // For production
  ]
}
```

### In your extension's dashboard/settings UI

Add a settings page to let users configure the backend URL:

```javascript
// Example: settings.js or options.js
import { setBackendUrl, getBackendUrl } from "./groq.js";

async function loadSettings() {
  const url = await getBackendUrl();
  document.getElementById("backendUrl").value = url;
}

async function saveSettings() {
  const url = document.getElementById("backendUrl").value;
  await setBackendUrl(url);
  alert("Backend URL saved!");
}

document.getElementById("save-btn").addEventListener("click", saveSettings);
window.addEventListener("DOMContentLoaded", loadSettings);
```

In your extension popup or dashboard, before transcribing:

```html
<!-- settings panel -->
<div>
  <label>Backend Server URL:</label>
  <input type="text" id="backendUrl" placeholder="http://localhost:8000" />
  <button id="save-btn">Save</button>
</div>
```

---

## 3. Production Deployment

### Option A: Replit (Easiest, Free Tier)

1. Go to https://replit.com
2. Click "Create" → "Import from GitHub" or paste your code
3. Add `GROQ_API_KEY` to Secrets:
   - Click "Secrets" (lock icon) on left sidebar
   - Key: `GROQ_API_KEY`, Value: `gsk_...`
4. Add `.replit` file to auto-run:

```bash
run = "python transcription_server.py"
```

5. Click "Run" — Replit gives you a public URL like `https://your-project.replit.dev`
6. In extension, set backend URL to that public URL

### Option B: Railway.app (Recommended for Production)

1. Go to https://railway.app
2. Create new project → "Deploy from GitHub" or paste code
3. Add environment variables in Dashboard:
   - `GROQ_API_KEY` = `gsk_...`
4. Railway auto-deploys and gives you a public URL
5. Update extension backend URL to that domain

### Option C: Docker (Any Cloud)

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

# Install FFmpeg
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY transcription_server.py .

EXPOSE 8000
CMD ["uvicorn", "transcription_server:app", "--host", "0.0.0.0", "--port", "8000"]
```

Deploy with Docker Compose, AWS ECS, Google Cloud Run, etc.

---

## 4. Using the Backend from Extension

### Update groq.js

Replace your old `groq.js` with the new one provided. Key changes:

- `groqTranscribe()` now POSTs to backend instead of Groq directly
- Backend handles chunking + Groq integration
- Summarize/Q&A still use direct Groq API (requires API key)

### In your extension code:

```javascript
import { groqTranscribe, setBackendUrl } from "./groq.js";

// Optional: Set backend URL (defaults to http://localhost:8000)
await setBackendUrl("https://your-backend.com");

// Transcribe (now hits backend)
const transcript = await groqTranscribe(audioBlob, (done, total) => {
  console.log(`Progress: ${done}/${total} chunks`);
});
```

---

## 5. Troubleshooting

### "GROQ_API_KEY not set on server"
- Make sure `GROQ_API_KEY` environment variable is set before starting the server
- In production, set it in your hosting platform's secrets/env vars

### "Failed to transcribe chunk"
- Check that your audio file is valid (can you play it in browser?)
- Try reducing `CHUNK_DURATION_MS` in `transcription_server.py` (e.g., 30 seconds instead of 60)
- Check Groq API status and rate limits

### CORS errors in extension
- If backend is on different domain, check `allow_origins` in `transcription_server.py`
- For local dev: `allow_origins=["chrome-extension://*"]` is fine
- For production: `allow_origins=["https://your-backend.com"]`

### "FFmpeg not found"
- Make sure FFmpeg is installed on your system (not just in Python)
- `which ffmpeg` (macOS/Linux) or `where ffmpeg` (Windows)
- Reinstall if needed

### Large files timing out
- Increase timeout in `transcribeChunk()` in `transcription_server.py`
- Currently 300 seconds (5 min) per chunk — should be enough for 1 min chunks
- Reduce `CHUNK_DURATION_MS` if timeouts persist

---

## 6. File Structure

```
transcription-backend/
├── transcription_server.py  # Main FastAPI app
├── requirements.txt         # Python dependencies
├── Dockerfile              # For containerized deployment
└── .env                    # Local env vars (GROQ_API_KEY=...)
```

---

## 7. Example cURL Test

```bash
# Test with a local audio file
curl -X POST "http://localhost:8000/transcribe" \
  -F "file=@recording.webm"

# Response:
# {
#   "transcript": "Full transcribed text here...",
#   "chunks_processed": 5,
#   "status": "success"
# }
```