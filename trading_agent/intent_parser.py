"""
IntentParser — парсер намерений из естественного языка.

Распознаёт команды вида:
- "AAVE SOL BTC - купить по $10"
- "докупи ETH до 50 долларов"
- "продай все XRP"
- "сколько у меня BTC?"
"""

import re
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum


class IntentType(Enum):
    """Типы намерений пользователя."""
    BATCH_BUY = "batch_buy"           # Купить несколько монет
    SINGLE_BUY = "single_buy"          # Купить одну монету
    REBALANCE = "rebalance"            # Докупить до целевой суммы
    SELL = "sell"                       # Продать
    BALANCE_CHECK = "balance_check"    # Проверить баланс
    UNKNOWN = "unknown"


@dataclass
class ParsedIntent:
    """Результат парсинга намерения."""
    intent: IntentType
    symbols: List[str] = field(default_factory=list)
    target_amount: float = 0.0
    rebalance: bool = False
    sell_all: bool = False
    raw_text: str = ""
    confidence: float = 0.0


class IntentParser:
    """
    Парсер торговых намерений из естественного языка.

    Примеры:
        parser = IntentParser()

        # Batch buy
        result = parser.parse("AAVE SOL BTC - купить по $10")
        # -> IntentType.BATCH_BUY, symbols=["AAVE", "SOL", "BTC"], target_amount=10

        # Rebalance
        result = parser.parse("докупи ETH до 50 долларов")
        # -> IntentType.REBALANCE, symbols=["ETH"], target_amount=50, rebalance=True
    """

    # Паттерны для распознавания намерений
    BUY_KEYWORDS = [
        r'куп[ий]', r'купить', r'докуп[ий]', r'докупить',
        r'buy', r'приобрести', r'взять', r'добавь', r'добавить',
        r'возьми', r'бери', r'набери', r'закупи',
    ]

    SELL_KEYWORDS = [
        r'прода[йм]', r'продать', r'sell', r'слей', r'слить',
        r'избавься', r'скинь', r'выведи', r'ликвидируй',
    ]

    REBALANCE_KEYWORDS = [
        r'учитыва[яй]', r'уже куплен', r'докуп[ий].*до',
        r'доведи.*до', r'ребаланс', r'rebalance',
        r'чтобы.*было.*по', r'до.*каждой', r'каждую.*до',
    ]

    BALANCE_KEYWORDS = [
        r'скольк[ои]', r'баланс', r'balance', r'позици[яи]',
        r'что у меня', r'мои монеты', r'портфель',
    ]

    # Паттерны для извлечения суммы
    AMOUNT_PATTERNS = [
        r'\$\s*(\d+(?:[.,]\d+)?)',                    # $10, $ 10.5
        r'(\d+(?:[.,]\d+)?)\s*(?:долл|usdt|usd|\$)',  # 10 долларов, 10 usdt
        r'(\d+(?:[.,]\d+)?)\s*(?:бакс|баксов)',       # 10 баксов
        r'по\s+(\d+(?:[.,]\d+)?)',                    # по 10
        r'на\s+(\d+(?:[.,]\d+)?)\s*(?:долл|usdt|usd|\$)?',  # на 10 долларов
    ]

    # Стоп-слова для фильтрации (не монеты)
    STOP_WORDS = {
        'USDT', 'USD', 'КУПИТЬ', 'ПРОДАТЬ', 'ДОЛЛАРОВ', 'КАЖДУЮ',
        'МОНЕТ', 'МНЕ', 'НУЖНО', 'ХОЧУ', 'НАДО', 'ВСЕ', 'ВСЁ',
        'ПО', 'НА', 'ДО', 'ЗА', 'ОТ', 'ИЗ', 'ДЛЯ', 'БЕЗ',
        'СЕЙЧАС', 'СРОЧНО', 'БЫСТРО', 'ТИХО', 'МОЖЕШЬ', 'ПОЖАЛУЙСТА',
    }

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def parse(self, text: str) -> ParsedIntent:
        """
        Парсит текст и извлекает намерение.

        Args:
            text: Текст сообщения пользователя

        Returns:
            ParsedIntent с распознанным намерением и параметрами
        """
        normalized = text.strip()
        lower = normalized.lower()

        result = ParsedIntent(
            intent=IntentType.UNKNOWN,
            raw_text=text,
        )

        # Определяем тип намерения
        is_buy = self._matches_keywords(lower, self.BUY_KEYWORDS)
        is_sell = self._matches_keywords(lower, self.SELL_KEYWORDS)
        is_rebalance = self._matches_keywords(lower, self.REBALANCE_KEYWORDS)
        is_balance = self._matches_keywords(lower, self.BALANCE_KEYWORDS)

        # Извлекаем символы
        symbols = self._extract_symbols(normalized)
        result.symbols = symbols

        # Извлекаем сумму
        amount = self._extract_amount(lower)
        result.target_amount = amount

        # Определяем итоговое намерение
        if is_balance:
            result.intent = IntentType.BALANCE_CHECK
            result.confidence = 0.8

        elif is_sell:
            result.intent = IntentType.SELL
            result.sell_all = 'все' in lower or 'всё' in lower
            result.confidence = 0.85

        elif is_buy or is_rebalance:
            if len(symbols) >= 2:
                result.intent = IntentType.BATCH_BUY
                result.confidence = 0.9
            elif len(symbols) == 1:
                result.intent = IntentType.SINGLE_BUY
                result.confidence = 0.85
            else:
                result.intent = IntentType.UNKNOWN
                result.confidence = 0.3

            result.rebalance = is_rebalance
            if is_rebalance:
                result.confidence = min(result.confidence + 0.05, 1.0)

        # Если нашли символы и сумму - повышаем уверенность
        if symbols and amount > 0:
            result.confidence = min(result.confidence + 0.1, 1.0)

        self.logger.debug(
            "Parsed intent: %s, symbols=%s, amount=%.2f, rebalance=%s",
            result.intent.value, result.symbols, result.target_amount, result.rebalance
        )

        return result

    def _matches_keywords(self, text: str, keywords: List[str]) -> bool:
        """Проверяет наличие ключевых слов в тексте."""
        for keyword in keywords:
            if re.search(keyword, text, re.IGNORECASE):
                return True
        return False

    def _extract_symbols(self, text: str) -> List[str]:
        """
        Извлекает символы криптовалют из текста.

        Args:
            text: Исходный текст

        Returns:
            Список уникальных символов
        """
        # Ищем слова 2-10 заглавных букв (возможно с _USDT)
        pattern = r'\b([A-Z]{2,10})(?:_USDT)?\b'
        matches = re.findall(pattern, text.upper())

        # Фильтруем стоп-слова и дубликаты
        seen = set()
        result = []

        for symbol in matches:
            if symbol not in self.STOP_WORDS and symbol not in seen:
                seen.add(symbol)
                result.append(symbol)

        return result

    def _extract_amount(self, text: str) -> float:
        """
        Извлекает сумму в долларах из текста.

        Args:
            text: Текст в нижнем регистре

        Returns:
            Сумма или 0 если не найдена
        """
        for pattern in self.AMOUNT_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amount_str = match.group(1).replace(',', '.')
                try:
                    return float(amount_str)
                except ValueError:
                    continue

        return 0.0

    def is_trading_command(self, text: str) -> bool:
        """
        Быстрая проверка - является ли текст торговой командой.

        Args:
            text: Текст сообщения

        Returns:
            True если похоже на торговую команду
        """
        lower = text.lower()

        # Проверяем ключевые слова
        if self._matches_keywords(lower, self.BUY_KEYWORDS):
            return True
        if self._matches_keywords(lower, self.SELL_KEYWORDS):
            return True

        # Проверяем наличие символов монет + суммы
        symbols = self._extract_symbols(text)
        amount = self._extract_amount(lower)

        if len(symbols) >= 1 and amount > 0:
            return True

        return False

    def format_parsed(self, result: ParsedIntent) -> str:
        """
        Форматирует результат парсинга для отображения.

        Args:
            result: ParsedIntent

        Returns:
            Отформатированная строка
        """
        lines = [
            f"🔍 **Распознано:**",
            f"• Намерение: {result.intent.value}",
            f"• Символы: {', '.join(result.symbols) if result.symbols else 'не найдены'}",
            f"• Сумма: ${result.target_amount:.2f}" if result.target_amount else "• Сумма: не указана",
            f"• Уверенность: {result.confidence:.0%}",
        ]

        if result.rebalance:
            lines.append("• Режим: Rebalance (учёт имеющихся)")

        if result.sell_all:
            lines.append("• Режим: Продать всё")

        return "\n".join(lines)


# === Тесты ===
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    parser = IntentParser()

    test_cases = [
        "AAVE_USDT ZEC_USDT NMR_USDT SOL_USDT BTC_USDT - мне нужно купить 5 этих монет на 10 долларов каждую",
        "купи BTC на $50",
        "докупи ETH до 100 долларов учитывая уже купленные",
        "AAVE SOL - купить по 10 долларов",
        "продай все XRP",
        "сколько у меня биткоина?",
        "BTC ETH SOL - по 20 баксов каждую",
    ]

    for text in test_cases:
        print(f"\n📝 Input: {text}")
        result = parser.parse(text)
        print(parser.format_parsed(result))
