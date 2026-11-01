from functools import lru_cache

from restaurant_management_system.config import get_settings
from restaurant_management_system.messaging.base import MessageProvider
from restaurant_management_system.messaging.console import ConsoleProvider


@lru_cache
def get_provider() -> MessageProvider:
    name = get_settings().messaging_provider
    if name == "console":
        return ConsoleProvider()
    raise ValueError(f"Unknown messaging provider: {name!r}")
