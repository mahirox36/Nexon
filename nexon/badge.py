"""
nexon.badge
~~~~~~~~~~

Badge system implementation for tracking user achievements.

:copyright: (c) 2025 Mahirox36
:license: MIT, see LICENSE for more details.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Union, Callable
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from datetime import datetime, timedelta


from .enums import ComparisonType, Rarity, RequirementType
import re
from typing import Any
from .utils import extract_emojis
from .message import Message
from .interactions import Interaction
from .data.user import UserManager, UserData

if TYPE_CHECKING:
    from .user import User
    from .member import Member

from .dataManager import DataManager

__all__ = (
    "Badge",
    "BadgeManager",
    "BadgeRequirement",
    "onBadgeEarned",
)



class BadgeRequirement:
    """Represents a requirement for earning a badge.
    
    This class defines the conditions that must be met for a user to earn a badge.

    .. versionadded:: Nexon 0.2.3

    Parameters
    -----------
    requirement_type: :class:`RequirementType`
        The type of requirement to check
    value: :class:`int`
        The numeric value to compare against
    comparison: :class:`ComparisonType`
        How to compare the values
    specific_value: :class:`str`
        Additional string data needed for some requirement types
    """
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
class Badge:
    """A data container for badge information.

    .. versionadded:: Nexon 0.2.3

    Parameters
    -----------
    name: :class:`str`
        The name of the badge
    description: :class:`str`
        A description of how to earn the badge
    icon_url: :class:`str`
        URL to the badge's icon image
    guild_id: Optional[:class:`int`]
        The guild this badge belongs to, if any
    requirements: List[Dict[:class:`str`, Union[:class:`str`, :class:`int`]]]
        The requirements that must be met to earn this badge
    rarity: :class:`Rarity`
        How rare/difficult the badge is to obtain
    hidden: :class:`bool`
        Whether this badge should be hidden from users
    """
    name: str
    description: str
    icon_url: str
    _last_id: int = -1
    _data_manager = DataManager(
        name="BadgeCounter",
        server_id=None,
        default={"last_id": -1},
        entity_type="System",
        add_name_folder=False
    )
    
    id: int = field(init=False)  # Make id field not required in constructor
    created_at: datetime = field(default_factory=datetime.now)
    guild_id: Optional[int] = None  # None means global badge
    requirements: List[Dict[str, Union[str, int]]] = field(default_factory=list)
    rarity: Rarity = Rarity.common
    hidden: bool = False
    
    def __post_init__(self):
        # Load the last ID from disk if not already loaded
        if Badge._last_id == -1:
            Badge._last_id = Badge._data_manager["last_id"]
        
        # Auto-generate ID when instance is created
        Badge._last_id += 1
        self.id = Badge._last_id
        
        # Save the new last_id to disk
        Badge._data_manager["last_id"] = Badge._last_id
        Badge._data_manager.save()
    
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
    def from_dict(cls, data: dict) -> 'Badge':
        data = data.copy()
        if isinstance(data.get("created_at"), str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        # Update _last_id if loaded ID is higher
        if data.get("id", -1) > cls._last_id:
            cls._last_id = data["id"]
            cls._data_manager["last_id"] = cls._last_id
            cls._data_manager.save()
        return cls(**data)

    @classmethod
    def reset_id_counter(cls):
        """Reset the ID counter back to -1"""
        cls._last_id = -1
        cls._data_manager["last_id"] = -1
        cls._data_manager.save()

def onBadgeEarned(badge: Badge, user: Union['User', 'Member']) -> None:
    """Default event handler called when a user earns a badge.
    
    .. versionadded:: Nexon 0.2.3
    
    Parameters
    ----------
    badge: :class:`Badge`
        The badge that was earned
    user: Union[:class:`User`, :class:`Member`]
        The user who earned the badge
    """
    # Suppress unused parameter warnings
    _ = (badge, user)

class BadgeManager:
    """Manages the badge system for tracking user achievements.

    .. versionadded:: Nexon 0.2.3

    Parameters
    -----------
    guild_id: Optional[:class:`int`]
        The guild ID if this manager is for a specific guild
    """
    badge_earned_callback = staticmethod(onBadgeEarned)
    
    def __init__(self, guild_id: Optional[int] = None):
        self.data_manager = DataManager(
            name="Badges",
            server_id=guild_id,
            default={"badges": {}},
            entity_type= "Badges",
            add_name_folder= True if guild_id else False
        )
    
    @classmethod
    def set_badge_earned_callback(cls, callback: Callable) -> None:
        """Set a new callback function for badge earning events"""
        cls.badge_earned_callback = staticmethod(callback)
        
    async def add_badge(self, badge: Badge) -> None:
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

    async def get_badge(self, badge_id: int) -> Optional[Badge]:
        """Get a badge by ID"""
        badges = self.data_manager["badges"]
        if badge_data := badges.get(str(badge_id)):
            return Badge.from_dict(badge_data)
        return None

    async def get_all_badges(self) -> List[Badge]:
        """Get all badges"""
        return [Badge.from_dict(b) for b in self.data_manager["badges"].values()]

    async def update_badge(self, badge_id: int, updated_badge: Badge) -> None:
        """Update an existing badge"""
        badges = self.data_manager["badges"]
        if str(badge_id) not in badges:
            raise ValueError(f"Badge with ID {badge_id} does not exist")
        badges[str(badge_id)] = updated_badge.to_dict()
        self.data_manager.save()

    async def award_badge(self, user: Union['User', 'Member'], badge_id: int) -> None:
        """Award a badge to a user"""
        
        badge = await self.get_badge(badge_id)
        if not badge:
            raise ValueError(f"Badge with ID {badge_id} does not exist")
            
        user_manager = UserManager(user)
        user_data = user_manager.user_data
        if not isinstance(user_data, UserData):
            return
        
        if badge_id not in user_data.badges:
            user_data.badges.add(badge_id)
            user_manager.save()
            self.badge_earned_callback(badge, user)

    async def remove_user_badge(self, user: Union['User', 'Member'], badge_id: int) -> None:
        """Remove a badge from a user"""
        user_manager = UserManager(user)
        user_data = user_manager.user_data
        
        if not isinstance(user_data, UserData):
            return
        
        if badge_id in user_data.badges:
            user_data.badges.remove(badge_id)
            user_manager.save()

    async def get_user_badges(self, user: Union['User', 'Member']) -> List[Badge]:
        """Get all badges a user has"""
        user_manager = UserManager(user)
        user_badges = []
        
        if not isinstance(user_manager.user_data, UserData):
            return []
        
        for badge_id in user_manager.user_data.badges:
            if badge := await self.get_badge(badge_id):
                user_badges.append(badge)
                
        return user_badges
    
    async def add_badges_from_list(self, badges: List[Badge]) -> None:
        """Add multiple badges from a list"""
        for badge in badges:
            try:
                await self.add_badge(badge)
            except ValueError:
                continue

    async def sync_badges_with_list(self, badges: List[Badge]) -> None:
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

    async def get_user_unowned_badges(self, user: Union['User', 'Member']) -> List[Badge]:
        """Get all badges the user doesn't have"""
        all_badges = await self.get_all_badges()
        user_badges = await self.get_user_badges(user)
        return [badge for badge in all_badges if badge not in user_badges]

    async def get_user_hidden_badges(self, user: Union['User', 'Member']) -> List[Badge]:
        """Get all hidden badges the user has"""
        user_badges = await self.get_user_badges(user)
        return [badge for badge in user_badges if badge.hidden]

    async def get_user_unowned_hidden_badges(self, user: Union['User', 'Member']) -> List[Badge]:
        """Get all hidden badges the user doesn't have"""
        unowned_badges = await self.get_user_unowned_badges(user)
        return [badge for badge in unowned_badges if badge.hidden]

    async def verify_requirement(
        self, 
        requirement: Dict[str, Any], 
        user_data: 'UserData',
        context: Optional[Union[Message, Interaction]] = None
    ) -> bool:
        """Verify if a single requirement is met"""
        req = BadgeRequirement.from_dict(requirement)
        
        # Basic numeric requirements
        if req.type == RequirementType.MESSAGE_COUNT:
            return req.check(user_data.total_messages)
        elif req.type == RequirementType.REACTION_RECEIVED:
            return req.check(user_data.reactions_received)
        elif req.type == RequirementType.REACTION_GIVEN:
            return req.check(user_data.reactions_given)
        elif req.type == RequirementType.ATTACHMENT_COUNT:
            return req.check(user_data.attachments_sent)
        elif req.type == RequirementType.MENTION_COUNT:
            return req.check(user_data.mentions_count)
        elif req.type == RequirementType.LINK_SHARED:
            return req.check(user_data.links_shared)
        elif req.type == RequirementType.GIF_COUNT:
            return req.check(user_data.gif_sent)
        elif req.type == RequirementType.MESSAGE_DELETE_COUNT:
            return req.check(user_data.deleted_messages)
        elif req.type == RequirementType.MESSAGE_EDIT_COUNT:
            return req.check(user_data.edited_messages)
        elif req.type == RequirementType.TIME_BASED:
            try:
                time_str = req.specific_value.strip().upper()
                current_time = datetime.now()

                hour, minute = map(int, time_str.replace(' ', ':').split(':')[:2])
                if 'PM' in time_str and hour != 12:
                    hour += 12
                elif 'AM' in time_str and hour == 12:
                    hour = 0

                return req.check(
                    current_time.hour * 60 + current_time.minute,
                    hour * 60 + minute
                )
            except ValueError:
                return False
        elif req.type == RequirementType.INACTIVE_DURATION:
            if not user_data.last_message is None:
                if user_data.last_message + timedelta(hours=float(req.value)) < datetime.now():
                    return True
            return False
        elif req.type == RequirementType.UNIQUE_EMOJI_COUNT:
            return req.check(len(user_data.unique_emojis_used) + len(user_data.unique_custom_emojis_used))
            
        # Special requirements that need context
        if context:
            if isinstance(context, Message):
                if req.type == RequirementType.CONTENT_MATCH:
                    if not req.specific_value:
                        return False
                    try:
                        pattern = re.compile(req.specific_value, re.IGNORECASE)
                        return bool(pattern.search(context.content.lower()))
                    except re.error:
                        return req.specific_value.lower() in context.content.lower()
                
                elif req.type == RequirementType.CONTENT_LENGTH:
                    return req.check(len(context.content))
                
                elif req.type == RequirementType.MESSAGE_SENT:
                    return True
                
                elif req.type == RequirementType.SPECIFIC_EMOJI:
                    emojisExtracted = extract_emojis(req.specific_value)
                    return any(emoji in context.content for emoji in emojisExtracted)
                elif req.type == RequirementType.GIF_SENT:
                    # Using a simpler pattern to match common GIF URLs
                    gif_count = len(re.findall(r'https?://[^\s]+\.(gif|mp4)|https?://(tenor\.com|gfycat\.com)/[^\s]+', context.content))
                    return req.check(gif_count)
                    return req.check(gif_count)
                
                elif req.type == RequirementType.SPECIFIC_USER_INTERACTION:
                    if context.reference and context.reference.message_id:
                        cachedMessage = context.reference.cached_message
                        messageReferenced = cachedMessage if cachedMessage else await context.channel.fetch_message(context.reference.message_id)
                    else:
                        return False
                    return str(messageReferenced.author.id) == req.specific_value

                elif req.type == RequirementType.ATTACHMENT_SENT:
                    return req.check(len(context.attachments))
                
                elif req.type == RequirementType.UNIQUE_MENTION_COUNT:
                    unique_mentions = len(user_data.unique_users_mentioned)
                    return req.check(unique_mentions)
                        
                elif req.type == RequirementType.EMOJI_USED:
                    emoji_count = len(re.findall(r'[\U0001F300-\U0001F9FF]|[\u2600-\u26FF\u2700-\u27BF]', context.content))
                    return req.check(emoji_count)
                    
                elif req.type == RequirementType.CUSTOM_EMOJI_USED:
                    custom_emoji_count = len(re.findall(r'<:\w+:\d+>', context.content))
                    return req.check(custom_emoji_count)
                    
            elif isinstance(context, Interaction):
                if req.type == RequirementType.ALL_COMMANDS:
                    total_commands = len(context.client.application_commands)
                    used_commands = len(user_data.favorite_commands)
                    return total_commands == used_commands
                    
        # Channel-specific requirements
        elif req.type == RequirementType.CHANNEL_ACTIVITY:
            channel_msgs = user_data.preferred_channels.get(req.specific_value, 0)
            return req.check(channel_msgs)
            
        # Command usage requirements
        elif req.type == RequirementType.COMMAND_USE:
            cmd_usage = user_data.favorite_commands.get(req.specific_value.lower(), 0)
            return req.check(cmd_usage)

        return False

    async def check_for_new_badges(
        self,
        user: Union['User', 'Member'],
        context: Optional[Union[Message, Interaction]] = None
    ) -> List[Badge]:
        """Check if the user has earned any new badges and award them"""
        
        
        user_manager = UserManager(user)
        user_data = user_manager.user_data
        earned_badges: List[Badge] = []
        
        if not isinstance(user_data, UserData):
            return []
        
        if not user_data:
            return earned_badges

        all_badges = await self.get_all_badges()
        current_badges = set(user_data.badges)
        
        for badge in all_badges:
            if badge.id in current_badges:
                continue
                
            requirements_met = True
            for requirement in badge.requirements:
                if not await self.verify_requirement(requirement, user_data, context):
                    requirements_met = False
                    break
                    
            if requirements_met:
                await self.award_badge(user, badge.id)
                earned_badges.append(badge)
                
        return earned_badges

    async def process_event(
        self,
        user: Union['User', 'Member'],
        context: Optional[Union[Message, Interaction]] = None
    ) -> List[Badge]:
        """Process an event and check for new badges"""
        return await self.check_for_new_badges(user, context)