#!/usr/bin/env python3
"""
Zen2API Android App - All-in-one proxy service for Zen Browser
Combines 5 services into a single Android app:
1. zen2api (port 9015) - OpenAI/Anthropic format proxy to Zen upstream
2. anyrouter (port 18888) - Anthropic-compatible proxy to AnyRouter
3. openrouter (port 9020) - OpenRouter free-model proxy
4. codebuff (port 9025) - Codebuff free-model proxy  
5. grok2api (port 9030) - Grok/NVIDIA/Modal/Kilo proxies

Built from decompiled zen2api-release bytecode for ARM64 Android/Termux
"""

import os
import sys
import asyncio
import threading
import signal
from pathlib import Path

# Add python libs to path
sys.path.insert(0, str(Path(__file__).parent))

# ─── Config ──────────────────────────────────────────────────────────────
class Config:
    # Environment detection
    IS_ANDROID = 'ANDROID_ROOT' in os.environ or 'ANDROID_DATA' in os.environ
    IS_TERMUX = 'TERMUX_VERSION' in os.environ
    
    # Paths
    if IS_ANDROID:
        BASE_DIR = Path('/data/data/com.zen2api/files') if not IS_TERMUX else Path.home() / '.zen2api'
    else:
        BASE_DIR = Path.home() / '.zen2api'
    
    CONFIG_DIR = BASE_DIR / 'config'
    LOG_DIR = BASE_DIR / 'logs'
    CACHE_DIR = BASE_DIR / 'cache'
    
    for d in (CONFIG_DIR, LOG_DIR, CACHE_DIR):
        d.mkdir(parents=True, exist_ok=True)
    
    # Service ports
    ZEN2API_PORT = int(os.getenv('ZEN2API_PORT', '9015'))
    ANYROUTER_PORT = int(os.getenv('ANYROUTER_PORT', '18888'))
    OPENROUTER_PORT = int(os.getenv('OPENROUTER_PORT', '9020'))
    CODEBUFF_PORT = int(os.getenv('CODEBUFF_PORT', '9025'))
    GROK_PORT = int(os.getenv('GROK_PORT', '9030'))
    
    HOST = os.getenv('ZEN2API_HOST', '0.0.0.0')
    
    # Feature flags
    ZEN2API_ENABLED = os.getenv('ZEN2API_ENABLED', 'true').lower() == 'true'
    ANYROUTER_ENABLED = os.getenv('ANYROUTER_ENABLED', 'true').lower() == 'true'
    OPENROUTER_ENABLED = os.getenv('OPENROUTER_ENABLED', 'true').lower() == 'true'
    CODEBUFF_ENABLED = os.getenv('CODEBUFF_ENABLED', 'true').lower() == 'true'
    GROK_ENABLED = os.getenv('GROK_ENABLED', 'true').lower() == 'true'
    
    # API Keys (set via env or config file)
    ZEN2API_KEY = os.getenv('ZEN2API_KEY', '')
    ANYROUTER_API_KEY = os.getenv('ANYROUTER_API_KEY', '')
    OPENROUTER_API_KEYS = os.getenv('OPENROUTER_API_KEYS', '').split(',') if os.getenv('OPENROUTER_API_KEYS') else []
    CODEBUFF_AUTH_TOKEN = os.getenv('CODEBUFF_AUTH_TOKEN', '')
    CODEBUFF_CREDENTIALS_PATH = os.getenv('CODEBUFF_CREDENTIALS_PATH', str(CONFIG_DIR / 'codebuff_credentials.json'))
    NVIDIA_API_KEYS = os.getenv('NVIDIA_API_KEYS', '').split(',') if os.getenv('NVIDIA_API_KEYS') else []
    MODAL_TOKENS = os.getenv('MODAL_TOKENS', '').split(',') if os.getenv('MODAL_TOKENS') else []
    
    # Upstream URLs
    ZEN_UPSTREAM_URL = os.getenv('ZEN_UPSTREAM_URL', 'https://opencode.ai/zen/v1/messages')
    ZEN_CHAT_COMPLETIONS_URL = os.getenv('ZEN_CHAT_COMPLETIONS_URL', 'https://opencode.ai/zen/v1/chat/completions')
    ZEN_MODELS_URL = os.getenv('ZEN_MODELS_URL', 'https://opencode.ai/zen/v1/models')
    ANYROUTER_UPSTREAM = os.getenv('ANYROUTER_UPSTREAM', 'https://anyrouter.top')
    OPENROUTER_UPSTREAM = os.getenv('OPENROUTER_UPSTREAM', 'https://openrouter.ai/api/v1')
    KILO_UPSTREAM = os.getenv('KILO_UPSTREAM', 'https://api.kilo.ai/api/openrouter')
    NVIDIA_UPSTREAM = os.getenv('NVIDIA_UPSTREAM', 'https://integrate.api.nvidia.com/v1/chat/completions')
    MODAL_UPSTREAM = os.getenv('MODAL_UPSTREAM', 'https://api.us-west-2.modal.direct/v1/chat/completions')
    CODEBUFF_BASE_URL = os.getenv('CODEBUFF_BASE_URL', 'https://www.codebuff.com')
    
    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = LOG_DIR / 'zen2api_android.log'

# ─── Minimal FastAPI Reimplementation ──────────────────────────────────
# Using uvicorn + starlette directly to avoid heavy deps

try:
    from fastapi import FastAPI, Request, Response, HTTPException, Depends
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import StreamingResponse, JSONResponse
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    print("FastAPI not available, using minimal HTTP server")

# ─── Service Base Classes ───────────────────────────────────────────────
import httpx
import json
import time
import logging
from typing import Optional, Dict, Any, List, AsyncIterator
from contextlib import asynccontextmanager

logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Config.LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('zen2api_android')

# ─── Shared HTTP Client ─────────────────────────────────────────────────
class HTTPClient:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(60.0))
    
    async def close(self):
        await self.client.aclose()
    
    async def post(self, url: str, **kwargs) -> httpx.Response:
        return await self.client.post(url, **kwargs)
    
    async def get(self, url: str, **kwargs) -> httpx.Response:
        return await self.client.get(url, **kwargs)
    
    async def stream(self, method: str, url: str, **kwargs) -> AsyncIterator[httpx.Response]:
        async with self.client.stream(method, url, **kwargs) as resp:
            yield resp

http_client = HTTPClient()

# ─── Adapter Utilities ──────────────────────────────────────────────────
def convert_openai_to_anthropic(openai_body: dict) -> dict:
    """Convert OpenAI chat/completions format to Anthropic messages format"""
    messages = openai_body.get('messages', [])
    anthropic_messages = []
    system = None
    
    for msg in messages:
        role = msg.get('role')
        content = msg.get('content', '')
        
        if role == 'system':
            system = content
        elif role == 'user':
            anthropic_messages.append({'role': 'user', 'content': content})
        elif role == 'assistant':
            anthropic_messages.append({'role': 'assistant', 'content': content})
        elif role == 'tool':
            # Tool results handled separately
            pass
    
    result = {
        'model': openai_body.get('model', ''),
        'messages': anthropic_messages,
        'max_tokens': openai_body.get('max_tokens', 4096),
        'stream': openai_body.get('stream', False),
    }
    if system:
        result['system'] = system
    if 'temperature' in openai_body:
        result['temperature'] = openai_body['temperature']
    if 'top_p' in openai_body:
        result['top_p'] = openai_body['top_p']
    
    return result

def convert_anthropic_to_openai(anthropic_body: dict) -> dict:
    """Convert Anthropic format to OpenAI chat/completions"""
    messages = []
    if anthropic_body.get('system'):
        messages.append({'role': 'system', 'content': anthropic_body['system']})
    for msg in anthropic_body.get('messages', []):
        messages.append({'role': msg['role'], 'content': msg['content']})
    
    return {
        'model': anthropic_body.get('model', ''),
        'messages': messages,
        'max_tokens': anthropic_body.get('max_tokens', 4096),
        'stream': anthropic_body.get('stream', False),
        'temperature': anthropic_body.get('temperature', 0.7),
        'top_p': anthropic_body.get('top_p', 1.0),
    }

# ─── Zen2API Service (Port 9015) ────────────────────────────────────────
class Zen2APIService:
    def __init__(self):
        self.app = FastAPI(title="zen2api", version="4.9.3")
        self.setup_routes()
    
    def setup_routes(self):
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        @self.app.get("/health")
        async def health():
            return {"status": "ok", "service": "zen2api", "version": "4.9.3"}
        
        @self.app.get("/v1/models")
        async def list_models():
            try:
                resp = await http_client.get(Config.ZEN_MODELS_URL)
                return resp.json()
            except Exception as e:
                logger.error(f"Models fetch failed: {e}")
                return {"data": [{"id": "zen-auto", "object": "model"}]}
        
        @self.app.post("/v1/messages")
        async def anthropic_messages(request: Request):
            body = await request.json()
            return await self.proxy_anthropic(body, request.headers)
        
        @self.app.post("/v1/chat/completions")
        async def openai_chat(request: Request):
            body = await request.json()
            return await self.proxy_openai(body, request.headers)
        
        @self.app.post("/v1/messages/count_tokens")
        async def count_tokens(request: Request):
            body = await request.json()
            # Simple estimation
            text = json.dumps(body.get('messages', []))
            return {"input_tokens": len(text) // 4}
    
    async def proxy_anthropic(self, body: dict, headers: dict):
        api_key = Config.ZEN2API_KEY or headers.get('x-api-key', '')
        if not api_key:
            raise HTTPException(401, "API key required")
        
        upstream_headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'User-Agent': 'ai-sdk/anthropic/2.0.65',
            'anthropic-version': '2023-06-01',
        }
        
        try:
            if body.get('stream'):
                return StreamingResponse(
                    self.stream_anthropic(body, upstream_headers),
                    media_type="text/event-stream"
                )
            else:
                resp = await http_client.post(Config.ZEN_UPSTREAM_URL, json=body, headers=upstream_headers)
                return JSONResponse(content=resp.json(), status_code=resp.status_code)
        except Exception as e:
            logger.error(f"Zen2API anthropic proxy error: {e}")
            raise HTTPException(502, str(e))
    
    async def proxy_openai(self, body: dict, headers: dict):
        api_key = Config.ZEN2API_KEY or headers.get('authorization', '').replace('Bearer ', '')
        if not api_key:
            raise HTTPException(401, "API key required")
        
        # Convert to Anthropic format
        anthropic_body = convert_openai_to_anthropic(body)
        
        upstream_headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'User-Agent': 'ai-sdk/anthropic/2.0.65',
            'anthropic-version': '2023-06-01',
        }
        
        try:
            if body.get('stream'):
                return StreamingResponse(
                    self.stream_openai(anthropic_body, upstream_headers),
                    media_type="text/event-stream"
                )
            else:
                resp = await http_client.post(Config.ZEN_CHAT_COMPLETIONS_URL, json=anthropic_body, headers=upstream_headers)
                data = resp.json()
                # Convert back to OpenAI format
                return JSONResponse(content=self.anthropic_to_openai_response(data), status_code=resp.status_code)
        except Exception as e:
            logger.error(f"Zen2API openai proxy error: {e}")
            raise HTTPException(502, str(e))
    
    async def stream_anthropic(self, body: dict, headers: dict) -> AsyncIterator[str]:
        async with http_client.client.stream('POST', Config.ZEN_UPSTREAM_URL, json=body, headers=headers) as resp:
            async for chunk in resp.aiter_text():
                yield chunk
    
    async def stream_openai(self, body: dict, headers: dict) -> AsyncIterator[str]:
        async with http_client.client.stream('POST', Config.ZEN_CHAT_COMPLETIONS_URL, json=body, headers=headers) as resp:
            async for chunk in resp.aiter_text():
                # Convert SSE from Anthropic to OpenAI format
                yield self.convert_sse_anthropic_to_openai(chunk)
    
    def convert_sse_anthropic_to_openai(self, chunk: str) -> str:
        # Simplified conversion
        return chunk
    
    def anthropic_to_openai_response(self, data: dict) -> dict:
        return {
            "id": data.get("id", "chatcmpl-" + str(int(time.time()))),
            "object": "chat.completion",
            "created": int(time.time()),
            "model": data.get("model", ""),
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": data.get("content", [{}])[0].get("text", "") if data.get("content") else ""},
                "finish_reason": data.get("stop_reason", "stop")
            }],
            "usage": {
                "prompt_tokens": data.get("usage", {}).get("input_tokens", 0),
                "completion_tokens": data.get("usage", {}).get("output_tokens", 0),
                "total_tokens": data.get("usage", {}).get("input_tokens", 0) + data.get("usage", {}).get("output_tokens", 0)
            }
        }

# ─── AnyRouter Service (Port 18888) ─────────────────────────────────────
class AnyRouterService:
    def __init__(self):
        self.app = FastAPI(title="anyrouter-proxy")
        self.setup_routes()
    
    def setup_routes(self):
        self.app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
        
        @self.app.get("/health")
        async def health():
            return {"status": "ok", "service": "anyrouter"}
        
        @self.app.get("/v1/models")
        async def models():
            return {"data": [{"id": "anyrouter-auto", "object": "model"}]}
        
        @self.app.post("/v1/messages")
        async def messages(request: Request):
            body = await request.json()
            return await self.proxy_anthropic(body, request.headers)
        
        @self.app.post("/v1/chat/completions")
        async def chat(request: Request):
            body = await request.json()
            anthropic_body = convert_openai_to_anthropic(body)
            result = await self.proxy_anthropic(anthropic_body, request.headers)
            # Convert back if needed for openai format
            return result
    
    async def proxy_anthropic(self, body: dict, headers: dict):
        api_key = Config.ANYROUTER_API_KEY or headers.get('x-api-key', '')
        if not api_key:
            raise HTTPException(401, "AnyRouter API key required")
        
        upstream_headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'anthropic-version': '2023-06-01',
        }
        
        try:
            resp = await http_client.post(f"{Config.ANYROUTER_UPSTREAM}/v1/messages", json=body, headers=upstream_headers)
            return JSONResponse(content=resp.json(), status_code=resp.status_code)
        except Exception as e:
            logger.error(f"AnyRouter proxy error: {e}")
            raise HTTPException(502, str(e))

# ─── OpenRouter Service (Port 9020) ─────────────────────────────────────
class OpenRouterService:
    def __init__(self):
        self.app = FastAPI(title="openrouter-proxy")
        self.key_index = 0
        self.setup_routes()
    
    def setup_routes(self):
        self.app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
        
        @self.app.get("/health")
        async def health():
            return {"status": "ok", "service": "openrouter"}
        
        @self.app.get("/v1/models")
        async def models():
            return await self.fetch_models()
        
        @self.app.post("/v1/chat/completions")
        async def chat(request: Request):
            body = await request.json()
            return await self.proxy_chat(body, request.headers)
        
        @self.app.post("/v1/messages")
        async def anthropic_messages(request: Request):
            body = await request.json()
            # Convert to openai format
            openai_body = convert_anthropic_to_openai(body)
            result = await self.proxy_chat(openai_body, request.headers)
            # Convert back
            return result
    
    async def fetch_models(self):
        if not Config.OPENROUTER_API_KEYS:
            return {"data": [{"id": "openrouter/free", "object": "model"}]}
        
        try:
            headers = {'Authorization': f'Bearer {Config.OPENROUTER_API_KEYS[0]}'}
            resp = await http_client.get(f"{Config.OPENROUTER_UPSTREAM}/models", headers=headers)
            data = resp.json()
            # Filter free models
            free_models = [m for m in data.get('data', []) if ':free' in m.get('id', '') or m.get('pricing', {}).get('prompt') == '0']
            return {"data": free_models or data['data'][:20]}
        except Exception as e:
            logger.error(f"OpenRouter models fetch failed: {e}")
            return {"data": [{"id": "openrouter/auto", "object": "model"}]}
    
    def get_next_key(self):
        if not Config.OPENROUTER_API_KEYS:
            return None
        key = Config.OPENROUTER_API_KEYS[self.key_index]
        self.key_index = (self.key_index + 1) % len(Config.OPENROUTER_API_KEYS)
        return key
    
    async def proxy_chat(self, body: dict, headers: dict):
        api_key = self.get_next_key() or headers.get('authorization', '').replace('Bearer ', '')
        if not api_key:
            raise HTTPException(401, "OpenRouter API key required")
        
        upstream_headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'HTTP-Referer': 'https://zen2api.android',
            'X-Title': 'Zen2API Android',
        }
        
        try:
            if body.get('stream'):
                return StreamingResponse(
                    self.stream_chat(body, upstream_headers),
                    media_type="text/event-stream"
                )
            else:
                resp = await http_client.post(f"{Config.OPENROUTER_UPSTREAM}/chat/completions", json=body, headers=upstream_headers)
                return JSONResponse(content=resp.json(), status_code=resp.status_code)
        except Exception as e:
            logger.error(f"OpenRouter proxy error: {e}")
            raise HTTPException(502, str(e))
    
    async def stream_chat(self, body: dict, headers: dict) -> AsyncIterator[str]:
        async with http_client.client.stream('POST', f"{Config.OPENROUTER_UPSTREAM}/chat/completions", json=body, headers=headers) as resp:
            async for chunk in resp.aiter_text():
                yield chunk

# ─── Codebuff Service (Port 9025) ───────────────────────────────────────
class CodebuffService:
    def __init__(self):
        self.app = FastAPI(title="codebuff-proxy")
        self.session_cache = {}
        self.setup_routes()
    
    def setup_routes(self):
        self.app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
        
        @self.app.get("/health")
        async def health():
            return {"status": "ok", "service": "codebuff"}
        
        @self.app.post("/v1/chat/completions")
        async def chat(request: Request):
            body = await request.json()
            return await self.proxy_chat(body)
        
        @self.app.post("/v1/messages")
        async def anthropic(request: Request):
            body = await request.json()
            openai_body = convert_anthropic_to_openai(body)
            return await self.proxy_chat(openai_body)
    
    async def get_session(self):
        """Get or create a Codebuff free session"""
        if not Config.CODEBUFF_AUTH_TOKEN:
            raise HTTPException(401, "Codebuff auth token required")
        
        # Check cache
        if 'session' in self.session_cache:
            session = self.session_cache['session']
            if time.time() - session.get('created', 0) < 3600:  # 1 hour
                return session
        
        # Create new session
        headers = {
            'Authorization': f'Bearer {Config.CODEBUFF_AUTH_TOKEN}',
            'Content-Type': 'application/json',
        }
        
        try:
            resp = await http_client.post(f"{Config.CODEBUFF_BASE_URL}/api/v1/freebuff/session", json={}, headers=headers)
            session = resp.json()
            self.session_cache['session'] = {**session, 'created': time.time()}
            return session
        except Exception as e:
            logger.error(f"Codebuff session creation failed: {e}")
            raise HTTPException(502, f"Codebuff session error: {e}")
    
    async def proxy_chat(self, body: dict):
        session = await self.get_session()
        instance_id = session.get('instance_id') or session.get('id')
        
        if not instance_id:
            raise HTTPException(502, "Invalid session")
        
        headers = {
            'Authorization': f'Bearer {Config.CODEBUFF_AUTH_TOKEN}',
            'Content-Type': 'application/json',
            'X-Instance-ID': instance_id,
        }
        
        try:
            if body.get('stream'):
                return StreamingResponse(
                    self.stream_chat(body, headers),
                    media_type="text/event-stream"
                )
            else:
                resp = await http_client.post(f"{Config.CODEBUFF_BASE_URL}/api/v1/chat/completions", json=body, headers=headers)
                return JSONResponse(content=resp.json(), status_code=resp.status_code)
        except Exception as e:
            logger.error(f"Codebuff proxy error: {e}")
            # Invalidate session on error
            self.session_cache.clear()
            raise HTTPException(502, str(e))
    
    async def stream_chat(self, body: dict, headers: dict) -> AsyncIterator[str]:
        async with http_client.client.stream('POST', f"{Config.CODEBUFF_BASE_URL}/api/v1/chat/completions", json=body, headers=headers) as resp:
            async for chunk in resp.aiter_text():
                yield chunk

# ─── Grok/NVIDIA/Modal/Kilo Service (Port 9030) ────────────────────────
class GrokService:
    """Unified proxy for NVIDIA, Modal, Kilo, and other OpenAI-compatible upstreams"""
    
    def __init__(self):
        self.app = FastAPI(title="grok2api")
        self.key_indices = {'nvidia': 0, 'modal': 0}
        self.setup_routes()
    
    def setup_routes(self):
        self.app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
        
        @self.app.get("/health")
        async def health():
            return {"status": "ok", "service": "grok2api", "providers": ["nvidia", "modal", "kilo"]}
        
        @self.app.get("/v1/models")
        async def models():
            return {"data": [
                {"id": "nvidia/nemotron-3-ultra", "object": "model"},
                {"id": "modal/glm-5.1", "object": "model"},
                {"id": "kilo/auto", "object": "model"},
            ]}
        
        @self.app.post("/v1/chat/completions")
        async def chat(request: Request):
            body = await request.json()
            model = body.get('model', '').lower()
            
            if 'nvidia' in model or 'nemotron' in model:
                return await self.proxy_nvidia(body)
            elif 'modal' in model or 'glm' in model or 'zai' in model:
                return await self.proxy_modal(body)
            elif 'kilo' in model:
                return await self.proxy_kilo(body)
            else:
                # Default to NVIDIA
                return await self.proxy_nvidia(body)
        
        @self.app.post("/v1/messages")
        async def anthropic(request: Request):
            body = await request.json()
            openai_body = convert_anthropic_to_openai(body)
            return await self.chat(openai_body)  # reuse logic
    
    def get_next_nvidia_key(self):
        if not Config.NVIDIA_API_KEYS:
            return None
        key = Config.NVIDIA_API_KEYS[self.key_indices['nvidia']]
        self.key_indices['nvidia'] = (self.key_indices['nvidia'] + 1) % len(Config.NVIDIA_API_KEYS)
        return key
    
    def get_next_modal_token(self):
        if not Config.MODAL_TOKENS:
            return None
        token = Config.MODAL_TOKENS[self.key_indices['modal']]
        self.key_indices['modal'] = (self.key_indices['modal'] + 1) % len(Config.MODAL_TOKENS)
        return token
    
    async def proxy_nvidia(self, body: dict):
        api_key = self.get_next_nvidia_key()
        if not api_key:
            raise HTTPException(401, "NVIDIA API key required")
        
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        }
        
        try:
            if body.get('stream'):
                return StreamingResponse(
                    self.stream_upstream(Config.NVIDIA_UPSTREAM, body, headers),
                    media_type="text/event-stream"
                )
            else:
                resp = await http_client.post(Config.NVIDIA_UPSTREAM, json=body, headers=headers)
                return JSONResponse(content=resp.json(), status_code=resp.status_code)
        except Exception as e:
            logger.error(f"NVIDIA proxy error: {e}")
            raise HTTPException(502, str(e))
    
    async def proxy_modal(self, body: dict):
        token = self.get_next_modal_token()
        if not token:
            raise HTTPException(401, "Modal token required")
        
        # Apply Modal max_tokens limit
        if body.get('max_tokens', 0) > 131072:
            body['max_tokens'] = 131072
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        }
        
        try:
            if body.get('stream'):
                return StreamingResponse(
                    self.stream_upstream(Config.MODAL_UPSTREAM, body, headers),
                    media_type="text/event-stream"
                )
            else:
                resp = await http_client.post(Config.MODAL_UPSTREAM, json=body, headers=headers)
                return JSONResponse(content=resp.json(), status_code=resp.status_code)
        except Exception as e:
            logger.error(f"Modal proxy error: {e}")
            raise HTTPException(502, str(e))
    
    async def proxy_kilo(self, body: dict):
        headers = {'Content-Type': 'application/json'}
        
        try:
            if body.get('stream'):
                return StreamingResponse(
                    self.stream_upstream(f"{Config.KILO_UPSTREAM}/chat/completions", body, headers),
                    media_type="text/event-stream"
                )
            else:
                resp = await http_client.post(f"{Config.KILO_UPSTREAM}/chat/completions", json=body, headers=headers)
                return JSONResponse(content=resp.json(), status_code=resp.status_code)
        except Exception as e:
            logger.error(f"Kilo proxy error: {e}")
            raise HTTPException(502, str(e))
    
    async def stream_upstream(self, url: str, body: dict, headers: dict) -> AsyncIterator[str]:
        async with http_client.client.stream('POST', url, json=body, headers=headers) as resp:
            async for chunk in resp.aiter_text():
                yield chunk

# ─── Service Manager ────────────────────────────────────────────────────
class ServiceManager:
    def __init__(self):
        self.services = {}
        self.servers = {}
        self.running = False
    
    def create_services(self):
        if Config.ZEN2API_ENABLED:
            self.services['zen2api'] = Zen2APIService()
        if Config.ANYROUTER_ENABLED:
            self.services['anyrouter'] = AnyRouterService()
        if Config.OPENROUTER_ENABLED:
            self.services['openrouter'] = OpenRouterService()
        if Config.CODEBUFF_ENABLED:
            self.services['codebuff'] = CodebuffService()
        if Config.GROK_ENABLED:
            self.services['grok'] = GrokService()
    
    async def start_all(self):
        self.create_services()
        self.running = True
        
        port_map = {
            'zen2api': Config.ZEN2API_PORT,
            'anyrouter': Config.ANYROUTER_PORT,
            'openrouter': Config.OPENROUTER_PORT,
            'codebuff': Config.CODEBUFF_PORT,
            'grok': Config.GROK_PORT,
        }
        
        for name, service in self.services.items():
            port = port_map.get(name, 9015)
            config = uvicorn.Config(
                service.app,
                host=Config.HOST,
                port=port,
                log_level=Config.LOG_LEVEL.lower(),
                access_log=False
            )
            server = uvicorn.Server(config)
            self.servers[name] = server
            
            # Run in background thread
            thread = threading.Thread(target=lambda: asyncio.run(server.serve()), daemon=True)
            thread.start()
            logger.info(f"Started {name} on port {port}")
    
    async def stop_all(self):
        self.running = False
        for name, server in self.servers.items():
            server.should_exit = True
            logger.info(f"Stopped {name}")
        await http_client.close()

# ─── Android Entry Points ──────────────────────────────────────────────
service_manager = ServiceManager()

def start_services():
    """Called from Android/Java via Chaquopy or from command line"""
    if not FASTAPI_AVAILABLE:
        logger.error("FastAPI/uvicorn not available. Install requirements.")
        return False
    
    asyncio.run(service_manager.start_all())
    return True

def stop_services():
    asyncio.run(service_manager.stop_all())

# For direct execution
if __name__ == "__main__":
    import signal
    
    def signal_handler(sig, frame):
        logger.info("Shutdown signal received")
        stop_services()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("=" * 50)
    logger.info("Zen2API Android - Starting all services")
    logger.info(f"  zen2api:     http://{Config.HOST}:{Config.ZEN2API_PORT}")
    logger.info(f"  anyrouter:   http://{Config.HOST}:{Config.ANYROUTER_PORT}")
    logger.info(f"  openrouter:  http://{Config.HOST}:{Config.OPENROUTER_PORT}")
    logger.info(f"  codebuff:    http://{Config.HOST}:{Config.CODEBUFF_PORT}")
    logger.info(f"  grok2api:    http://{Config.HOST}:{Config.GROK_PORT}")
    logger.info("=" * 50)
    
    try:
        asyncio.run(service_manager.start_all())
        # Keep running
        while service_manager.running:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Interrupted")
    finally:
        stop_services()