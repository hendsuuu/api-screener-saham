"""
Notifier Runner - Helper untuk menjalankan notifikasi dari scheduler
"""

import asyncio
import logging
from typing import List, Union

logger = logging.getLogger(__name__)


async def run_notification(token: str, chat_ids: List[Union[str, int]], message: str):
    """Kirim notifikasi tunggal."""
    from telegram_bot.bot import TelegramNotifier
    notifier = TelegramNotifier(token, chat_ids)
    await notifier.send_message(message)
