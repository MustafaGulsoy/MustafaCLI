"""
Model Provider Abstraction Layer
================================

Bu modül, farklı LLM provider'ları için unified interface sağlar.

Desteklenen provider'lar:
1. Ollama (local) - Qwen, DeepSeek, CodeLlama, Llama
2. OpenAI Compatible APIs (LM Studio, vLLM, text-generation-webui)
3. Anthropic Claude (API key gerekli)

Author: Mustafa (Kardelen Yazılım)
License: MIT
"""

from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional
import asyncio

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    RetryError,
)

from .constants import (
    MAX_RETRY_ATTEMPTS,
    RETRY_MIN_WAIT,
    RETRY_MAX_WAIT,
    RETRY_MULTIPLIER,
    DEFAULT_HTTP_TIMEOUT,
    NATIVE_TOOL_MODELS,
    OLLAMA_DEFAULT_URL,
    OPENAI_COMPATIBLE_DEFAULT_URL,
    ANTHROPIC_API_URL,
)
from .exceptions import (
    ModelAPIError,
    ModelTimeoutError,
    ModelRateLimitError,
    ProviderConnectionError,
)
from .logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class ModelResponse:
    """
    Unified model response
    
    Tüm provider'lardan gelen yanıtlar bu formata dönüştürülür.
    """
    id: str
    content: str
    tool_calls: list[dict]
    thinking: Optional[str] = None
    finish_reason: Optional[str] = None
    usage: Optional[dict] = None
    raw_response: Optional[dict] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "tool_calls": self.tool_calls,
            "thinking": self.thinking,
            "finish_reason": self.finish_reason,
            "usage": self.usage,
        }


class ModelProvider(ABC):
    """
    Abstract base class for model providers
    
    Tüm provider'lar bu interface'i implement etmeli.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider adı"""
        pass
    
    @property
    @abstractmethod
    def supports_tools(self) -> bool:
        """Tool calling desteği var mı"""
        pass
    
    @property
    @abstractmethod
    def supports_streaming(self) -> bool:
        """Streaming desteği var mı"""
        pass
    
    @abstractmethod
    async def complete(
        self,
        messages: list[dict],
        system: Optional[str] = None,
        tools: Optional[list[dict]] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs
    ) -> dict:
        """
        Model completion
        
        Args:
            messages: Conversation messages
            system: System prompt
            tools: Tool definitions
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            
        Returns:
            Dict with 'content', 'tool_calls', etc.
        """
        pass
    
    async def stream(
        self,
        messages: list[dict],
        system: Optional[str] = None,
        tools: Optional[list[dict]] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs
    ) -> AsyncIterator[str]:
        """
        Streaming completion (optional)
        
        Default implementation: yield full response
        """
        response = await self.complete(
            messages=messages,
            system=system,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        yield response.get("content", "")


class OllamaProvider(ModelProvider):
    """
    Ollama provider - local model çalıştırma
    
    Önerilen modeller:
    - qwen2.5-coder:32b - En iyi coding performansı
    - deepseek-coder-v2:16b - Hızlı ve iyi
    - codellama:34b - Meta'nın code modeli
    - llama3.2:latest - Genel amaçlı
    
    Tool calling:
    - Qwen ve Llama 3.1+ native tool calling destekler
    - Diğer modeller için prompt-based tool calling
    """
    
    name = "ollama"
    supports_streaming = True
    
    def __init__(
        self,
        model: str = "qwen2.5-coder:32b",
        base_url: str = OLLAMA_DEFAULT_URL,
        timeout: int = DEFAULT_HTTP_TIMEOUT,
        max_retries: int = MAX_RETRY_ATTEMPTS,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.client = httpx.AsyncClient(timeout=timeout)

        # Model'e göre tool calling stratejisi
        self._native_tool_models = NATIVE_TOOL_MODELS
    
    @property
    def supports_tools(self) -> bool:
        """Native tool calling desteği"""
        return any(m in self.model.lower() for m in self._native_tool_models)
    
    async def complete(
        self,
        messages: list[dict],
        system: Optional[str] = None,
        tools: Optional[list[dict]] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs
    ) -> dict:
        """Ollama API call"""
        
        # Messages'ı hazırla
        ollama_messages = []
        
        if system:
            ollama_messages.append({"role": "system", "content": system})
        
        for msg in messages:
            ollama_messages.append({
                "role": msg["role"],
                "content": msg.get("content", ""),
            })
        
        # Tool calling stratejisi
        if tools and self.supports_tools:
            # Native tool calling
            return await self._complete_with_native_tools(
                ollama_messages, tools, temperature, max_tokens
            )
        elif tools:
            # Prompt-based tool calling
            return await self._complete_with_prompt_tools(
                ollama_messages, tools, temperature, max_tokens
            )
        else:
            # No tools
            return await self._complete_simple(
                ollama_messages, temperature, max_tokens
            )
    
    async def stream_complete(
        self,
        messages: list[dict],
        system: Optional[str] = None,
        tools: Optional[list[dict]] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs,
    ):
        """Streaming version — yields content chunks as they arrive.

        Yields dicts with keys:
          {"type": "content", "text": "..."} — text token
          {"type": "done", "content": "full text", "tool_calls": [...], "usage": {...}}
        """
        ollama_messages = []
        if system:
            ollama_messages.append({"role": "system", "content": system})
        for msg in messages:
            ollama_messages.append({"role": msg["role"], "content": msg.get("content", "")})

        payload = {
            "model": self.model,
            "messages": ollama_messages,
            "stream": True,
            "keep_alive": "10m",
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": 8192,
            },
        }
        if tools and self.supports_tools:
            payload["tools"] = tools

        full_content = ""
        in_think = False
        first_chunk = True

        # Use longer timeout for streaming — model may take 60s+ for thinking before first token
        stream_timeout = httpx.Timeout(timeout=600.0, connect=30.0)
        async with self.client.stream(
            "POST", f"{self.base_url}/api/chat", json=payload, timeout=stream_timeout
        ) as response:
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if data.get("done"):
                    # Final chunk — parse tool calls if present
                    tool_calls = []
                    msg = data.get("message", {})
                    if "tool_calls" in msg:
                        for tc in msg["tool_calls"]:
                            tool_calls.append({
                                "id": tc.get("id", f"call_{len(tool_calls)}"),
                                "name": tc.get("function", {}).get("name", ""),
                                "arguments": tc.get("function", {}).get("arguments", {}),
                            })
                    # Fallback: parse from accumulated content
                    if not tool_calls and full_content:
                        tool_calls = self._parse_tool_calls_from_text(full_content)

                    yield {
                        "type": "done",
                        "content": full_content,
                        "tool_calls": tool_calls,
                        "usage": {
                            "prompt_tokens": data.get("prompt_eval_count", 0),
                            "completion_tokens": data.get("eval_count", 0),
                            "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
                        },
                    }
                    return

                # Streaming content chunk
                chunk = data.get("message", {}).get("content", "")
                if not chunk:
                    continue

                # Filter <think>...</think> blocks (qwen3 thinking mode)
                if "<think>" in chunk:
                    in_think = True
                if in_think:
                    full_content += chunk
                    if "</think>" in chunk:
                        in_think = False
                        # Extract text after </think>
                        after = chunk.split("</think>", 1)[-1]
                        if after:
                            yield {"type": "content", "text": after}
                    continue

                full_content += chunk
                yield {"type": "content", "text": chunk}

    @retry(
        stop=stop_after_attempt(MAX_RETRY_ATTEMPTS),
        wait=wait_exponential(multiplier=RETRY_MULTIPLIER, min=RETRY_MIN_WAIT, max=RETRY_MAX_WAIT),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=True,
    )
    async def _complete_simple(
        self,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> dict:
        """Simple completion without tools"""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "keep_alive": "10m",
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": 8192,
            }
        }

        try:
            logger.debug(
                "provider_request",
                provider="ollama",
                model=self.model,
                messages_count=len(messages),
            )

            response = await self.client.post(
                f"{self.base_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()

            data = response.json()

            logger.debug(
                "provider_response",
                provider="ollama",
                model=self.model,
                tokens=data.get("eval_count", 0),
            )

        except httpx.TimeoutException as e:
            logger.error("provider_timeout", provider="ollama", model=self.model)
            raise ModelTimeoutError(f"Ollama API timeout: {str(e)}")
        except httpx.NetworkError as e:
            logger.error("provider_network_error", provider="ollama", model=self.model, error=str(e))
            raise ProviderConnectionError(
                message=f"Failed to connect to Ollama: {str(e)}",
                provider="ollama",
            )
        except httpx.HTTPStatusError as e:
            logger.error(
                "provider_http_error",
                provider="ollama",
                model=self.model,
                status_code=e.response.status_code,
            )
            raise ModelAPIError(
                message=f"Ollama API error: {e.response.text}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            )
        
        return {
            "id": data.get("created_at", ""),
            "content": data.get("message", {}).get("content", ""),
            "tool_calls": [],
            "finish_reason": data.get("done_reason", "stop"),
            "usage": {
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
                "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            }
        }
    
    async def _complete_with_native_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> dict:
        """Native tool calling (Qwen, Llama 3.1+)"""
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "stream": False,
            "keep_alive": "10m",
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": 8192,
            }
        }

        response = await self.client.post(
            f"{self.base_url}/api/chat",
            json=payload,
        )
        response.raise_for_status()
        
        data = response.json()
        message = data.get("message", {})
        
        # Tool calls'ı parse et
        tool_calls = []
        if "tool_calls" in message:
            # Native tool calling format (Ollama's official format)
            for tc in message["tool_calls"]:
                tool_calls.append({
                    "id": tc.get("id", f"call_{len(tool_calls)}"),
                    "name": tc.get("function", {}).get("name", ""),
                    "arguments": tc.get("function", {}).get("arguments", {}),
                })

        # Fallback: If no native tool calls, try parsing from content
        # Some models (like qwen2.5-coder:7b) output JSON in content instead
        content = message.get("content", "")
        if not tool_calls and content:
            tool_calls = self._parse_tool_calls_from_text(content)
            # Clean content if we found tool calls
            if tool_calls:
                content = self._clean_content_from_tool_calls(content)

        return {
            "id": data.get("created_at", ""),
            "content": content,
            "tool_calls": tool_calls,
            "finish_reason": data.get("done_reason", "stop"),
            "usage": {
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
                "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            }
        }
    
    async def _complete_with_prompt_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> dict:
        """
        Prompt-based tool calling for models without native support
        
        Tool definitions'ı system prompt'a ekle ve JSON output parse et.
        """
        # Tool prompt oluştur
        tool_prompt = self._build_tool_prompt(tools)
        
        # System message'a ekle veya yeni oluştur
        if messages and messages[0]["role"] == "system":
            messages[0]["content"] = f"{messages[0]['content']}\n\n{tool_prompt}"
        else:
            messages.insert(0, {"role": "system", "content": tool_prompt})
        
        # Completion al
        response = await self._complete_simple(messages, temperature, max_tokens)
        
        # Tool calls'ı parse et
        content = response.get("content", "")
        tool_calls = self._parse_tool_calls_from_text(content)
        
        # Tool calls varsa content'i temizle
        if tool_calls:
            content = self._clean_content_from_tool_calls(content)
        
        response["content"] = content
        response["tool_calls"] = tool_calls
        
        return response
    
    def _build_tool_prompt(self, tools: list[dict]) -> str:
        """Tool definitions için prompt oluştur"""
        tool_descriptions = []
        
        for tool in tools:
            func = tool.get("function", {})
            name = func.get("name", "")
            desc = func.get("description", "")
            params = json.dumps(func.get("parameters", {}), indent=2)
            
            tool_descriptions.append(f"""### {name}
{desc}

Parameters:
```json
{params}
```""")
        
        return f"""## Available Tools

You have access to the following tools. To use a tool, respond with a JSON block in this exact format:

```tool
{{
    "name": "tool_name",
    "arguments": {{
        "param1": "value1",
        "param2": "value2"
    }}
}}
```

You can use multiple tools by including multiple ```tool blocks.
After using tools, wait for the results before proceeding.

{chr(10).join(tool_descriptions)}
"""
    
    def _parse_tool_calls_from_text(self, text: str) -> list[dict]:
        """Text'ten tool calls parse et"""
        tool_calls = []

        # ```tool ... ``` pattern
        pattern = r'```tool\s*\n?(.*?)\n?```'
        matches = re.findall(pattern, text, re.DOTALL)

        for i, match in enumerate(matches):
            try:
                data = json.loads(match.strip())
                tool_calls.append({
                    "id": f"call_{i}",
                    "name": data.get("name", ""),
                    "arguments": data.get("arguments", {}),
                })
            except json.JSONDecodeError:
                continue

        # Fallback: Try to find JSON objects with "name" and "arguments"
        if not tool_calls:
            # Find all potential JSON objects in the text
            # Use a simple brace counting approach for nested objects
            # Find all JSON-like objects that contain "name" and "arguments"
            i = 0
            while i < len(text):
                if text[i] == '{':
                    # Try to extract a complete JSON object starting here
                    brace_count = 0
                    start = i

                    for j in range(i, len(text)):
                        if text[j] == '{':
                            brace_count += 1
                        elif text[j] == '}':
                            brace_count -= 1

                        if brace_count == 0:
                            # Found complete JSON object
                            json_str = text[start:j+1]
                            try:
                                data = json.loads(json_str)
                                # Check if it looks like a tool call
                                if isinstance(data, dict) and "name" in data and "arguments" in data:
                                    tool_calls.append({
                                        "id": f"call_{len(tool_calls)}",
                                        "name": data.get("name", ""),
                                        "arguments": data.get("arguments", {}),
                                    })
                            except (json.JSONDecodeError, ValueError):
                                pass
                            i = j + 1
                            break
                    else:
                        i += 1
                else:
                    i += 1

        return tool_calls
    
    def _clean_content_from_tool_calls(self, text: str) -> str:
        """Tool call bloklarını content'ten temizle"""
        # ```tool ... ``` pattern'ını temizle
        text = re.sub(r'```tool\s*\n?.*?\n?```', '', text, flags=re.DOTALL)
        return text.strip()
    
    async def stream(
        self,
        messages: list[dict],
        system: Optional[str] = None,
        tools: Optional[list[dict]] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs
    ) -> AsyncIterator[str]:
        """Streaming completion"""
        ollama_messages = []
        
        if system:
            ollama_messages.append({"role": "system", "content": system})
        
        for msg in messages:
            ollama_messages.append({
                "role": msg["role"],
                "content": msg.get("content", ""),
            })
        
        payload = {
            "model": self.model,
            "messages": ollama_messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            }
        }
        
        async with self.client.stream(
            "POST",
            f"{self.base_url}/api/chat",
            json=payload,
        ) as response:
            async for line in response.aiter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        content = data.get("message", {}).get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue
    
    async def close(self):
        """Client'ı kapat"""
        await self.client.aclose()


class OpenAICompatibleProvider(ModelProvider):
    """
    OpenAI-compatible API provider
    
    Desteklenen backend'ler:
    - LM Studio
    - vLLM
    - text-generation-webui (oobabooga)
    - LocalAI
    - Anything with OpenAI-compatible API
    """
    
    name = "openai_compatible"
    supports_tools = True
    supports_streaming = True
    
    def __init__(
        self,
        model: str = "local-model",
        base_url: str = "http://localhost:1234/v1",
        api_key: str = "not-needed",
        timeout: int = 300,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
        )
    
    async def complete(
        self,
        messages: list[dict],
        system: Optional[str] = None,
        tools: Optional[list[dict]] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs
    ) -> dict:
        """OpenAI-compatible completion"""
        
        # Messages hazırla
        openai_messages = []
        
        if system:
            openai_messages.append({"role": "system", "content": system})
        
        for msg in messages:
            openai_messages.append({
                "role": msg["role"],
                "content": msg.get("content", ""),
            })
        
        payload = {
            "model": self.model,
            "messages": openai_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        
        response = await self.client.post(
            f"{self.base_url}/chat/completions",
            json=payload,
        )
        response.raise_for_status()
        
        data = response.json()
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        
        # Tool calls parse
        tool_calls = []
        if "tool_calls" in message:
            for tc in message["tool_calls"]:
                try:
                    args = tc.get("function", {}).get("arguments", "{}")
                    if isinstance(args, str):
                        args = json.loads(args)
                    
                    tool_calls.append({
                        "id": tc.get("id", ""),
                        "name": tc.get("function", {}).get("name", ""),
                        "arguments": args,
                    })
                except json.JSONDecodeError:
                    continue
        
        return {
            "id": data.get("id", ""),
            "content": message.get("content", "") or "",
            "tool_calls": tool_calls,
            "finish_reason": choice.get("finish_reason", "stop"),
            "usage": data.get("usage", {}),
        }
    
    async def close(self):
        await self.client.aclose()


class AnthropicProvider(ModelProvider):
    """
    Anthropic Claude API provider
    
    Claude modelleri için native provider.
    Tool calling ve extended thinking desteği.
    """
    
    name = "anthropic"
    supports_tools = True
    supports_streaming = True
    
    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        api_key: Optional[str] = None,
        timeout: int = 300,
    ):
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.timeout = timeout
        self.client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
        )
    
    async def complete(
        self,
        messages: list[dict],
        system: Optional[str] = None,
        tools: Optional[list[dict]] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs
    ) -> dict:
        """Anthropic API completion"""
        
        # Messages'ı Anthropic formatına çevir
        anthropic_messages = []
        
        for msg in messages:
            role = msg["role"]
            if role == "system":
                continue  # System ayrı gönderiliyor
            
            if role == "tool":
                # Tool result
                anthropic_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.get("tool_call_id", ""),
                        "content": msg.get("content", ""),
                    }]
                })
            else:
                anthropic_messages.append({
                    "role": role,
                    "content": msg.get("content", ""),
                })
        
        payload = {
            "model": self.model,
            "messages": anthropic_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        
        if system:
            payload["system"] = system
        
        if tools:
            # Anthropic tool format
            anthropic_tools = []
            for tool in tools:
                func = tool.get("function", {})
                anthropic_tools.append({
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {}),
                })
            payload["tools"] = anthropic_tools
        
        response = await self.client.post(
            "https://api.anthropic.com/v1/messages",
            json=payload,
        )
        response.raise_for_status()
        
        data = response.json()
        
        # Content ve tool_calls parse
        content = ""
        tool_calls = []
        
        for block in data.get("content", []):
            if block["type"] == "text":
                content += block.get("text", "")
            elif block["type"] == "tool_use":
                tool_calls.append({
                    "id": block.get("id", ""),
                    "name": block.get("name", ""),
                    "arguments": block.get("input", {}),
                })
        
        return {
            "id": data.get("id", ""),
            "content": content,
            "tool_calls": tool_calls,
            "finish_reason": data.get("stop_reason", "end_turn"),
            "usage": {
                "prompt_tokens": data.get("usage", {}).get("input_tokens", 0),
                "completion_tokens": data.get("usage", {}).get("output_tokens", 0),
            }
        }
    
    async def close(self):
        await self.client.aclose()


def create_provider(
    provider_type: str,
    model: Optional[str] = None,
    **kwargs
) -> ModelProvider:
    """
    Provider factory function
    
    Args:
        provider_type: "ollama", "openai", "anthropic"
        model: Model name (optional, uses default)
        **kwargs: Provider-specific arguments
        
    Returns:
        ModelProvider instance
    """
    providers = {
        "ollama": OllamaProvider,
        "openai": OpenAICompatibleProvider,
        "openai_compatible": OpenAICompatibleProvider,
        "anthropic": AnthropicProvider,
    }
    
    if provider_type not in providers:
        raise ValueError(f"Unknown provider: {provider_type}. Available: {list(providers.keys())}")
    
    provider_class = providers[provider_type]
    
    if model:
        return provider_class(model=model, **kwargs)
    else:
        return provider_class(**kwargs)
