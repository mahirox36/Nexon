# SPDX-License-Identifier: MIT

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict, Union
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from datetime import datetime
from .enums import ComparisonType, Rarity, RequirementType

if TYPE_CHECKING:
    from .user import User
    from .member import Member

from .dataManager import DataManager

__all__ = (
    "BadgePayload",
    "BadgeManager"
)



class BadgeRequirement:
    """Represents a requirement for earning a badge"""
    def __init__(self, 
                 requirement_type: RequirementType, 
                 value: int = 1,
                 comparison: ComparisonType = ComparisonType.GREATER_EQUAL,
                 specific_value: str = ""):
        self.type = requirement_type
        self.value = value
        self.comparison = comparison
        self.specific_value = specific_value

    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "value": self.value, 
            "comparison": self.comparison.value,
            "specific_value": self.specific_value
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'BadgeRequirement':
        return cls(
            requirement_type=RequirementType(data["type"]),
            value=data.get("value", 1),
            comparison=ComparisonType(data.get("comparison", "greater_equal")),
            specific_value=data.get("specific_value", "")
        )

    def check(self, actual_value: int, second_value: Optional[int] = None) -> bool:
        """Check if the requirement is met based on comparison type"""
        if second_value is not None:
            # For time-based comparisons that need two values
            return self._compare_values(actual_value, second_value)
        
        # For standard numeric comparisons
        return self._compare_values(actual_value, self.value)
    
    def _compare_values(self, value1: int, value2: int) -> bool:
        """Helper method to compare values based on comparison type"""
        return {
            ComparisonType.EQUAL: lambda: value1 == value2,
            ComparisonType.GREATER: lambda: value1 > value2,
            ComparisonType.LESS: lambda: value1 < value2,
            ComparisonType.GREATER_EQUAL: lambda: value1 >= value2,
            ComparisonType.LESS_EQUAL: lambda: value1 <= value2,
        }[self.comparison]()

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

    async def get_user_unowned_badges(self, user: Union['User', 'Member']) -> List[BadgePayload]:
        """Get all badges the user doesn't have"""
        all_badges = await self.get_all_badges()
        user_badges = await self.get_user_badges(user)
        return [badge for badge in all_badges if badge not in user_badges]

    async def get_user_hidden_badges(self, user: Union['User', 'Member']) -> List[BadgePayload]:
        """Get all hidden badges the user has"""
        user_badges = await self.get_user_badges(user)
        return [badge for badge in user_badges if badge.hidden]

    async def get_user_unowned_hidden_badges(self, user: Union['User', 'Member']) -> List[BadgePayload]:
        """Get all hidden badges the user doesn't have"""
        unowned_badges = await self.get_user_unowned_badges(user)
        return [badge for badge in unowned_badges if badge.hidden]