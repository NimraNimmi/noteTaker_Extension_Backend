# api/index.py - Place this file in your api/ directory

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydub import AudioSegment
import httpx
import os
import asyncio
from io import BytesIO

app = FastAPI()

# Enable CORS for extension
app.add_middleware(
    CORSMiddleware,
    allow_origins=["chrome-extension://*", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_API_BASE = "https://api.groq.com/openai/v1"
WHISPER_MODEL = "whisper-large-v3-turbo"
CHUNK_DURATION_MS = 30000  # 30 seconds per chunk


def split_audio(audio_bytes: bytes, duration_ms: int = CHUNK_DURATION_MS) -> list[bytes]:
    try:
        audio = AudioSegment.from_file(BytesIO(audio_bytes))
        if len(audio) <= duration_ms:
            return [audio_bytes]
        
        chunks = []
        for i in range(0, len(audio), duration_ms):
            chunk = audio[i : i + duration_ms]
            buf = BytesIO()
            chunk.export(buf, format="webm", codec="libopus")
            chunks.append(buf.getvalue())
        return chunks
    except Exception as e:
        print(f"[split_audio] Error: {e}")
        raise


async def transcribe_chunk(chunk_bytes: bytes, api_key: str, retries: int = 2) -> str:
    for attempt in range(retries):
        try:
            form_data = {
                "model": (None, WHISPER_MODEL),
                "response_format": (None, "text"),
                "file": ("audio.webm", chunk_bytes, "audio/webm"),
            }
            
            async with httpx.AsyncClient(timeout=120) as client:
                res = await client.post(
                    f"{GROQ_API_BASE}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    files=form_data,
                )
            
            if res.status_code == 200:
                return res.text.strip()
            else:
                error = res.text if hasattr(res, 'text') else str(res.status_code)
                print(f"[transcribe_chunk] HTTP {res.status_code}: {error}")
                if res.status_code >= 500 and attempt < retries - 1:
                    await asyncio.sleep(1)
                    continue
                raise Exception(f"Groq error {res.status_code}")
        
        except Exception as e:
            print(f"[transcribe_chunk] Attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(1)
            else:
                raise
    
    raise Exception("Max retries exceeded")


@app.post("/api/transcribe")
async def transcribe(file: UploadFile = File(...)):
    if not GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY not configured")
    
    try:
        audio_bytes = await file.read()
        size_mb = len(audio_bytes) / 1024 / 1024
        print(f"[transcribe] Received {size_mb:.1f}MB audio")
        
        if len(audio_bytes) > 25 * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail=f"File too large ({size_mb:.1f}MB). Max 25MB for Vercel.",
            )
        
        chunks = split_audio(audio_bytes)
        print(f"[transcribe] Split into {len(chunks)} chunks")
        
        parts = []
        for i, chunk in enumerate(chunks):
            print(f"[transcribe] Chunk {i + 1}/{len(chunks)}...")
            text = await transcribe_chunk(chunk, GROQ_API_KEY)
            parts.append(text)
        
        full_transcript = " ".join(parts).strip()
        return {
            "transcript": full_transcript,
            "chunks_processed": len(chunks),
            "status": "success",
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"[transcribe] Error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/health")
def health():
    return {"status": "ok"}