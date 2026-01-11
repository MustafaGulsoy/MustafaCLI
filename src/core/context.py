"""
Context Management System
=========================

Bu modül, conversation history ve context window yönetimini sağlar.

Claude Code'un uzun session'larda çalışabilmesinin sırrı:
1. Akıllı message truncation
2. Conversation compaction (summarization)
3. Token counting ve budget management
4. Selective context loading

Author: Mustafa (Kardelen Yazılım)
License: MIT
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from collections import deque


class MessageRole(Enum):
    """Message rolleri - OpenAI/Anthropic uyumlu"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class Message:
    """
    Conversation message
    
    Tool calls ve tool results için özel alanlar var.
    """
    role: MessageRole
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    
    # Tool-related fields
    tool_calls: Optional[list[dict]] = None  # Assistant'ın tool çağrıları
    tool_call_id: Optional[str] = None  # Tool result için
    tool_name: Optional[str] = None  # Tool result için
    
    # Metadata
    tokens: Optional[int] = None  # Estimated token count
    metadata: Optional[dict] = None
    
    def to_dict(self) -> dict:
        """Dict formatına çevir"""
        result = {
            "role": self.role.value,
            "content": self.content,
        }
        
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        
        if self.tool_name:
            result["name"] = self.tool_name
        
        return result


class TokenEstimator:
    """
    Token count estimator
    
    Gerçek tokenization yapmadan yaklaşık token sayısı hesaplar.
    Farklı modeller için farklı katsayılar kullanılabilir.
    
    Formül: ~4 karakter = 1 token (İngilizce için ortalama)
    """
    
    def __init__(self, chars_per_token: float = 4.0):
        self.chars_per_token = chars_per_token
    
    def estimate(self, text: str) -> int:
        """Text için token sayısı tahmin et"""
        return int(len(text) / self.chars_per_token)
    
    def estimate_message(self, message: Message) -> int:
        """Message için token sayısı tahmin et"""
        # Base content
        tokens = self.estimate(message.content)
        
        # Role overhead (~4 tokens)
        tokens += 4
        
        # Tool calls overhead
        if message.tool_calls:
            tokens += self.estimate(json.dumps(message.tool_calls))
        
        return tokens
    
    def estimate_messages(self, messages: list[Message]) -> int:
        """Message listesi için toplam token sayısı"""
        return sum(self.estimate_message(m) for m in messages)


class ContextManager:
    """
    Context window manager
    
    Bu class, conversation history'yi yönetir ve context window
    limitlerini aşmamak için gerekli compaction'ları yapar.
    
    Attributes:
        max_tokens: Maximum context window size
        reserve_tokens: Response için ayrılan token sayısı
        messages: Conversation history
    """
    
    def __init__(
        self,
        max_tokens: int = 32000,
        reserve_tokens: int = 4000,
        estimator: Optional[TokenEstimator] = None,
    ):
        self.max_tokens = max_tokens
        self.reserve_tokens = reserve_tokens
        self.estimator = estimator or TokenEstimator()
        
        self._messages: list[Message] = []
        self._compacted_summary: Optional[str] = None
        self._total_tokens: int = 0
    
    @property
    def available_tokens(self) -> int:
        """Kullanılabilir token sayısı"""
        return self.max_tokens - self.reserve_tokens - self._total_tokens
    
    @property
    def messages(self) -> list[Message]:
        """Tüm mesajlar"""
        return self._messages.copy()
    
    def add_message(self, message: Message) -> None:
        """
        Mesaj ekle
        
        Token count hesapla ve gerekirse eski mesajları compact et.
        """
        # Token estimate
        if message.tokens is None:
            message.tokens = self.estimator.estimate_message(message)
        
        self._messages.append(message)
        self._total_tokens += message.tokens
    
    def should_compact(self, threshold: float = 0.8) -> bool:
        """
        Compaction gerekli mi?
        
        Args:
            threshold: Doluluk oranı (0-1)
            
        Returns:
            bool: Compaction gerekli mi
        """
        used_ratio = self._total_tokens / (self.max_tokens - self.reserve_tokens)
        return used_ratio >= threshold
    
    def get_recent_messages(self, n: int) -> list[Message]:
        """Son n mesajı al"""
        return self._messages[-n:] if n <= len(self._messages) else self._messages.copy()
    
    def get_old_messages(self, keep_recent: int = 10) -> list[Message]:
        """Eski mesajları al (compact edilecekler)"""
        if len(self._messages) <= keep_recent:
            return []
        return self._messages[:-keep_recent]
    
    def compact(self, summary: str, keep_recent: int = 10) -> None:
        """
        Context'i compact et
        
        Eski mesajları özetle ve sil.
        
        Args:
            summary: Eski mesajların özeti
            keep_recent: Korunacak son mesaj sayısı
        """
        if len(self._messages) <= keep_recent:
            return
        
        # Eski mesajları sil
        old_messages = self._messages[:-keep_recent]
        self._messages = self._messages[-keep_recent:]
        
        # Summary'yi sakla
        if self._compacted_summary:
            self._compacted_summary = f"{self._compacted_summary}\n\n{summary}"
        else:
            self._compacted_summary = summary
        
        # Token count güncelle
        self._total_tokens = self.estimator.estimate_messages(self._messages)
        if self._compacted_summary:
            self._total_tokens += self.estimator.estimate(self._compacted_summary)
    
    def to_model_format(self) -> list[dict]:
        """
        Model'e gönderilecek format
        
        Compacted summary varsa ilk mesaj olarak ekle.
        """
        result = []
        
        # Compacted summary ekle
        if self._compacted_summary:
            result.append({
                "role": "system",
                "content": f"Previous conversation summary:\n{self._compacted_summary}"
            })
        
        # Mesajları ekle
        for message in self._messages:
            result.append(message.to_dict())
        
        return result
    
    def clear(self) -> None:
        """Context'i temizle"""
        self._messages.clear()
        self._compacted_summary = None
        self._total_tokens = 0
    
    def get_stats(self) -> dict:
        """Context istatistikleri"""
        return {
            "total_messages": len(self._messages),
            "total_tokens": self._total_tokens,
            "max_tokens": self.max_tokens,
            "reserve_tokens": self.reserve_tokens,
            "available_tokens": self.available_tokens,
            "has_compacted_summary": self._compacted_summary is not None,
            "usage_ratio": self._total_tokens / (self.max_tokens - self.reserve_tokens),
        }


class SlidingWindowContext(ContextManager):
    """
    Sliding window context manager
    
    Sabit bir pencere boyutu tutar ve eski mesajları otomatik siler.
    Compaction yapmaz, sadece kırpar.
    
    Daha basit ama daha az context preservation.
    """
    
    def __init__(
        self,
        window_size: int = 20,
        max_tokens: int = 32000,
        reserve_tokens: int = 4000,
    ):
        super().__init__(max_tokens, reserve_tokens)
        self.window_size = window_size
    
    def add_message(self, message: Message) -> None:
        """Mesaj ekle ve pencereyi koru"""
        super().add_message(message)
        
        # Pencere boyutunu aş
        while len(self._messages) > self.window_size:
            removed = self._messages.pop(0)
            self._total_tokens -= removed.tokens or 0


class PriorityContext(ContextManager):
    """
    Priority-based context manager
    
    Mesajlara öncelik atar ve düşük öncelikli mesajları önce siler.
    
    Öncelik sırası (yüksekten düşüğe):
    1. User messages
    2. Tool results with errors
    3. Assistant messages with tool calls
    4. Tool results (success)
    5. General assistant messages
    """
    
    PRIORITY_MAP = {
        (MessageRole.USER, False): 5,
        (MessageRole.TOOL, True): 4,  # Error
        (MessageRole.ASSISTANT, True): 3,  # Has tool calls
        (MessageRole.TOOL, False): 2,  # Success
        (MessageRole.ASSISTANT, False): 1,
        (MessageRole.SYSTEM, False): 0,
    }
    
    def _get_priority(self, message: Message) -> int:
        """Mesaj önceliğini al"""
        has_special = bool(message.tool_calls) or (
            message.role == MessageRole.TOOL and 
            message.content.startswith("Error")
        )
        return self.PRIORITY_MAP.get((message.role, has_special), 0)
    
    def get_old_messages(self, keep_recent: int = 10) -> list[Message]:
        """Düşük öncelikli eski mesajları al"""
        if len(self._messages) <= keep_recent:
            return []
        
        # Son mesajları koru
        old_messages = self._messages[:-keep_recent]
        
        # Önceliğe göre sırala (düşük öncelik önce)
        old_messages.sort(key=lambda m: self._get_priority(m))
        
        return old_messages


class ConversationBuffer:
    """
    Circular buffer for conversation history
    
    Sabit boyutlu buffer - eski mesajlar otomatik silinir.
    Memory-efficient for very long conversations.
    """
    
    def __init__(self, max_messages: int = 100):
        self._buffer: deque[Message] = deque(maxlen=max_messages)
    
    def add(self, message: Message) -> None:
        """Mesaj ekle"""
        self._buffer.append(message)
    
    def get_all(self) -> list[Message]:
        """Tüm mesajları al"""
        return list(self._buffer)
    
    def get_recent(self, n: int) -> list[Message]:
        """Son n mesajı al"""
        return list(self._buffer)[-n:]
    
    def clear(self) -> None:
        """Buffer'ı temizle"""
        self._buffer.clear()
    
    def __len__(self) -> int:
        return len(self._buffer)
