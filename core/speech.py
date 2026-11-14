"""Optional OpenAI-compatible speech service, separate from agent execution."""
import hashlib
import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar
import httpx
import os
import threading
from pathlib import Path
from urllib.parse import urlsplit
from openai import OpenAI


logger = logging.getLogger(__name__)
speech_request_id = ContextVar('speech_request_id', default='direct')

@contextmanager
def speech_timing(stage, **metrics):
    started = time.monotonic()
    outcome = 'ok'
    try:
        yield
    except Exception as exc:
        outcome = type(exc).__name__
        raise
    finally:
        # Only technical timing metadata; no keys, audio or recognized text.
        logger.info('speech_stage request_id=%s stage=%s elapsed_ms=%.0f outcome=%s metrics=%s',
                    speech_request_id.get(), stage, (time.monotonic() - started) * 1000, outcome, metrics)


class SpeechService:
    def __init__(self, root: Path, options=None):
        self.root = root
        self.options = options or {}
        self.limit = threading.BoundedSemaphore(2)
        self.asr_limit = threading.BoundedSemaphore(2)
        self.cache_locks = [threading.Lock() for _ in range(16)]

    def settings(self):
        return {
            'api_key': os.environ.get('CZON_SPEECH_API_KEY', ''),
            'base_url': os.environ.get('CZON_SPEECH_BASE_URL', self.options.get('base_url', 'https://api.openai.com/v1')),
            'asr_model': os.environ.get('CZON_ASR_MODEL', self.options.get('asr_model', 'whisper-1')),
            'tts_model': os.environ.get('CZON_TTS_MODEL', self.options.get('tts_model', 'tts-1')),
            'voice': self.options.get('voice', 'alloy'),
            'style': self.options.get('style', '请用自然、沉稳的中文对话语气说话，语速适中，句间停顿自然。'),
        }

    def client(self, *, timeout=45):
        options = self.settings()
        return OpenAI(api_key=options['api_key'], base_url=options['base_url'], timeout=timeout, max_retries=0)

    def transcribe(self, name, data):
        with speech_timing('asr_upstream', bytes=len(data)):
            with self.client(timeout=httpx.Timeout(15, connect=3, write=3, pool=3)) as client:
                return client.audio.transcriptions.create(model=self.settings()['asr_model'], file=(name, data)).text

    def synthesize(self, owner, text):
        options = self.settings()
        spoken = text
        if urlsplit(options['base_url']).hostname == 'api.siliconflow.cn' and options['tts_model'] == 'FunAudioLLM/CosyVoice2-0.5B' and options['style']:
            spoken = options['style'] + '<|endofprompt|>' + text
        digest = hashlib.sha256(('\0'.join([owner, options['base_url'], options['tts_model'], options['voice'], spoken])).encode()).hexdigest()
        folder = self.root / hashlib.sha256(owner.encode()).hexdigest()[:16]
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f'{digest}.mp3'
        # Identical phrases from multiple displays share the same generated audio.
        with speech_timing('tts_cache_and_upstream', cache_hit=path.exists(), characters=len(text)), self.cache_locks[int(digest[:2], 16) % len(self.cache_locks)]:
            if not path.exists():
                with self.client() as client:
                    audio = client.audio.speech.create(model=options['tts_model'], voice=options['voice'], input=spoken, response_format='mp3')
                    temporary = path.with_suffix('.tmp')
                    try:
                        temporary.write_bytes(audio.content)
                        temporary.replace(path)
                    finally:
                        temporary.unlink(missing_ok=True)
        return path
