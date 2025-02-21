# SPDX-License-Identifier: MIT

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict, Union
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from datetime import datetime
from .enums import Rarity

if TYPE_CHECKING:
    from .user import User
    from .member import Member

from .dataManager import DataManager

__all__ = (
    "BadgePayload",
    "BadgeManager"
)


@dataclass
class BadgePayload:
    id: int
    name: str
    description: str
    icon_url: str
    created_at: datetime = field(default_factory=datetime.now)
    guild_id: Optional[int] = None  # None means global badge
    requirements: Dict[str, Any] = field(default_factory=dict)
    rarity: Rarity = Rarity.common
    hidden: bool = False
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name, 
            "description": self.description,
            "icon_url": self.icon_url,
            "created_at": self.created_at.isoformat(),
            "guild_id": self.guild_id,
            "requirements": self.requirements,
            "rarity": self.rarity,
            "hidden": self.hidden
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'BadgePayload':
        data = data.copy()
        if isinstance(data.get("created_at"), str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        return cls(**data)

class BadgeManager:
    def __init__(self, guild_id: Optional[int] = None):
        self.guild_id = guild_id
        self.data_manager = DataManager(
            name="Badges",
            server_id=guild_id,
            default={"badges": {}},
            entity_type= "Badges",
            add_name_folder= True if guild_id else False
        )
        
    async def add_badge(self, badge: BadgePayload) -> None:
        """Add a new badge"""
        badges = self.data_manager["badges"]
        if str(badge.id) in badges:
            raise ValueError(f"Badge with ID {badge.id} already exists")
        badges[str(badge.id)] = badge.to_dict()
        self.data_manager.save()

    async def remove_badge(self, badge_id: int) -> None:
        """Remove a badge by ID"""
        badges = self.data_manager["badges"]
        if str(badge_id) not in badges:
            raise ValueError(f"Badge with ID {badge_id} does not exist")
        del badges[str(badge_id)]
        self.data_manager.save()

    async def get_badge(self, badge_id: int) -> Optional[BadgePayload]:
        """Get a badge by ID"""
        badges = self.data_manager["badges"]
        if badge_data := badges.get(str(badge_id)):
            return BadgePayload.from_dict(badge_data)
        return None

    async def get_all_badges(self) -> List[BadgePayload]:
        """Get all badges"""
        return [BadgePayload.from_dict(b) for b in self.data_manager["badges"].values()]

    async def update_badge(self, badge_id: int, updated_badge: BadgePayload) -> None:
        """Update an existing badge"""
        badges = self.data_manager["badges"]
        if str(badge_id) not in badges:
            raise ValueError(f"Badge with ID {badge_id} does not exist")
        badges[str(badge_id)] = updated_badge.to_dict()
        self.data_manager.save()

    async def award_badge(self, user: Union['User', 'Member'], badge_id: int) -> None:
        """Award a badge to a user"""
        from .data.user import UserManager  # Import here to avoid circular imports
        
        badge = await self.get_badge(badge_id)
        if not badge:
            raise ValueError(f"Badge with ID {badge_id} does not exist")
            
        user_manager = UserManager(user)
        user_data = user_manager.user_data
        
        if badge_id not in user_data.badges:
            user_data.badges.add(badge_id)
            user_manager.save()

    async def remove_user_badge(self, user: Union['User', 'Member'], badge_id: int) -> None:
        """Remove a badge from a user"""
        
        from .data.user import UserManager
        user_manager = UserManager(user)
        user_data = user_manager.user_data
        
        if badge_id in user_data.badges:
            user_data.badges.remove(badge_id)
            user_manager.save()

    async def get_user_badges(self, user: Union['User', 'Member']) -> List[BadgePayload]:
        """Get all badges a user has"""
        
        from .data.user import UserManager
        user_manager = UserManager(user)
        user_badges = []
        
        for badge_id in user_manager.user_data.badges:
            if badge := await self.get_badge(badge_id):
                user_badges.append(badge)
                
        return user_badges
    
    async def add_badges_from_list(self, badges: List[BadgePayload]) -> None:
        """Add multiple badges from a list"""
        for badge in badges:
            try:
                await self.add_badge(badge)
            except ValueError:
                continue

    async def sync_badges_with_list(self, badges: List[BadgePayload]) -> None:
        """Sync badges with a list - add missing and remove extra badges"""
        current_badges = await self.get_all_badges()
        new_badge_ids = {badge.id for badge in badges}
        current_badge_ids = {badge.id for badge in current_badges}

        # Remove badges not in the new list
        for badge_id in current_badge_ids - new_badge_ids:
            await self.remove_badge(badge_id)

        # Add new badges
        for badge in badges:
            if badge.id not in current_badge_ids:
                await self.add_badge(badge)