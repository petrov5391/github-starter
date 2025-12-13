"""
Trading Agent — Telegram бот для управления торговлей на Gate.io.

Модули:
- intent_parser: Парсер намерений из естественного языка
- position_manager: Управление позициями и балансами
- smart_batch_buy: Умный batch buy с rebalance
- chat_handler_mixin: Улучшенная обработка чата
"""

from .intent_parser import IntentParser, IntentType, ParsedIntent
from .position_manager import PositionManager, PositionInfo
from .smart_batch_buy import SmartBatchBuy, BatchBuyResult, OrderResult, integrate_smart_batch_buy
from .chat_handler_mixin import SmartChatHandler, DialogContext

__all__ = [
    # Intent Parser
    "IntentParser",
    "IntentType",
    "ParsedIntent",
    # Position Manager
    "PositionManager",
    "PositionInfo",
    # Smart Batch Buy
    "SmartBatchBuy",
    "BatchBuyResult",
    "OrderResult",
    "integrate_smart_batch_buy",
    # Chat Handler
    "SmartChatHandler",
    "DialogContext",
]

__version__ = "1.0.0"
