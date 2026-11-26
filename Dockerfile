FROM python:3.13-slim

# ffmpeg for editing, the X/GL libraries are what headless Blender (bpy) links to.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fontconfig curl ca-certificates \
       libx11-6 libxrender1 libxfixes3 libxi6 libxkbcommon0 libxext6 libsm6 libice6 libgl1 libgomp1 \
    && apt-get clean

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Free narrator voice (LibriTTS, CC BY 4.0), used when no ElevenLabs key is set.
RUN mkdir -p voices \
    && curl -fsSL https://github.com/rhasspy/piper/releases/download/v0.0.2/voice-en-us-libritts-high.tar.gz \
       | tar xz -C voices

COPY . .

ENV DATA_DIR=/data PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["uvicorn", "b2a.server:app", "--host", "0.0.0.0", "--port", "8000"]
