"""
Transcription backend server using FastAPI + Groq Whisper.
Handles large audio files by chunking properly with pydub.
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydub import AudioSegment
import httpx
import os
from io import BytesIO

app = FastAPI()

# Enable CORS for extension
app.add_middleware(
    CORSMiddleware,
    allow_origins=["chrome-extension://*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_API_BASE = "https://api.groq.com/openai/v1"
WHISPER_MODEL = "whisper-large-v3-turbo"
CHUNK_DURATION_MS = 60000  # 1 minute chunks (adjust as needed)


def split_audio(audio_bytes: bytes, duration_ms: int = CHUNK_DURATION_MS) -> list[bytes]:
    """
    Split audio into chunks using pydub.
    Returns list of audio bytes (each is valid WebM).
    """
    try:
        # Load audio (pydub auto-detects format)
        audio = AudioSegment.from_file(BytesIO(audio_bytes))
        
        if len(audio) <= duration_ms:
            return [audio_bytes]  # Single chunk
        
        chunks = []
        for i in range(0, len(audio), duration_ms):
            chunk = audio[i : i + duration_ms]
            # Export as WebM (same format as input)
            buf = BytesIO()
            chunk.export(buf, format="webm", codec="libopus")
            chunks.append(buf.getvalue())
        
        return chunks
    except Exception as e:
        print(f"[split_audio] Error: {e}")
        raise


async def transcribe_chunk(chunk_bytes: bytes, api_key: str, retries: int = 3) -> str:
    """
    Transcribe a single audio chunk via Groq Whisper.
    """
    for attempt in range(retries):
        try:
            form_data = {
                "model": (None, WHISPER_MODEL),
                "response_format": (None, "text"),
                "file": ("audio.webm", chunk_bytes, "audio/webm"),
            }
            
            async with httpx.AsyncClient(timeout=300) as client:
                res = await client.post(
                    f"{GROQ_API_BASE}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    files=form_data,
                )
            
            if res.status_code == 200:
                return res.text.strip()
            else:
                error = await res.atext() if hasattr(res, 'atext') else res.text
                print(f"[transcribe_chunk] HTTP {res.status_code}: {error}")
                if res.status_code >= 500 and attempt < retries - 1:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                raise Exception(f"Groq error {res.status_code}")
        
        except Exception as e:
            print(f"[transcribe_chunk] Attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(2 * (attempt + 1))
            else:
                raise
    
    raise Exception("Max retries exceeded")


@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """
    Receive audio blob, chunk it, transcribe via Groq, return full transcript.
    """
    if not GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY not set on server")
    
    try:
        # Read uploaded file
        audio_bytes = await file.read()
        print(f"[transcribe] Received {len(audio_bytes) / 1024 / 1024:.1f}MB audio file")
        
        # Split into chunks
        chunks = split_audio(audio_bytes)
        print(f"[transcribe] Split into {len(chunks)} chunks")
        
        # Transcribe each chunk
        parts = []
        for i, chunk in enumerate(chunks):
            print(f"[transcribe] Transcribing chunk {i + 1}/{len(chunks)}...")
            text = await transcribe_chunk(chunk, GROQ_API_KEY)
            parts.append(text)
        
        full_transcript = " ".join(parts).strip()
        return {
            "transcript": full_transcript,
            "chunks_processed": len(chunks),
            "status": "success",
        }
    
    except Exception as e:
        print(f"[transcribe] Error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/health")
def health():
    """Health check."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)