"""
nexon.dataManager
~~~~~~~~~~~~~~~~

A unified data management system for handling JSON data storage.

:copyright: (c) 2024 Mahirox36
:license: MIT, see LICENSE for more details.
"""

from __future__ import annotations
from tortoise import Tortoise, connections
from tortoise.exceptions import ConfigurationError
from .data.config import TORTOISE_ORM


__all__ = (
    "init_db",
    "close_db",
    "is_db_initialized",
)

async def init_db() -> None:

    # Make sure you're passing the TORTOISE_ORM as a config to Tortoise.init()
    await Tortoise.init(config=TORTOISE_ORM)
    await Tortoise.generate_schemas()

async def close_db():
    await connections.close_all()

async def is_db_initialized() -> bool:
    """
    Check if the database is initialized.
    """
    try:
        return connections.all() != {}
    except ConfigurationError:
        return False