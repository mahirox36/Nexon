"""
nexon.data.guild
~~~~~~~~~~~~~~

Represents Discord guilds with statistical data tracking.

:copyright: (c) 2025 Mahirox36
:license: MIT, see LICENSE for more details.
"""

from datetime import datetime
from tortoise.exceptions import DoesNotExist
import re
from typing import TYPE_CHECKING, Union
from ..utils import extract_emojis
from .models import UserData, BotUser

if TYPE_CHECKING:
    from ..member import Member
    from ..user import User, BaseUser
    from ..guild import Guild


__all__ = (

)