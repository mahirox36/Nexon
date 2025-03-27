"""
nexon.data.models
~~~~~~~~~~~~~~

Database models for the Nexon Discord bot.

Models:
- BotUser: Tracks bot-wide statistics and settings
- User: Stores user activity and statistics
- Badge/UserBadge: Achievement system
- Guild: Server-specific settings and data
- Feature system: Modular feature management

Usage:
    from nexon.data.models import User
    user = await User.get_or_create_user(member)
    await user.increment_messages()
"""
import json
from math import floor, sqrt
from tortoise import fields, Model
from typing import Any, Dict, Set, Union, Optional, TYPE_CHECKING

from ..enums import ComparisonType, Rarity, RequirementType, ScopeType

if TYPE_CHECKING:
    from ..user import User as UserClass, BaseUser
    from ..member import Member

__all__ = (
    "SetJSONEncoder",
    "set_json_decoder",
    "BotUser",
    "UserData",
    "Badge",
    "BadgeRequirement",
    "UserBadge",
    "GuildData",
    "Feature",
)

class SetJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, set):
            return {'__type__': 'set', 'items': list(obj)}
        return super().default(obj)

def set_json_decoder(obj):
    if '__type__' in obj and obj['__type__'] == 'set':
        return set(obj['items'])
    return obj

class BotUser(Model):
    """Bot-wide statistics and settings tracker.
    
    This model stores global bot metrics like total messages processed,
    command usage, and error tracking.
    
    Attributes:
        id (int): Bot's unique identifier
        total_messages (int): Total messages processed
        commands_processed (int): Total commands handled
        errors_encountered (int): Number of errors caught
        
    .. versionadded:: Nexon 0.3.0
    """
    # Required fields
    id                          = fields.BigIntField(pk=True)
    
    # Integer fields
    total_messages              = fields.IntField(default=0)
    commands_processed          = fields.IntField(default=0)
    errors_encountered          = fields.IntField(default=0)
    
    # Date/Time fields
    created_at                  = fields.DatetimeField(null=True)
    last_update                 = fields.DatetimeField(auto_now=True)
    
    # JSON fields
    commands_errors             = fields.JSONField(default=dict)# Dict[str, List[str]]
    features_used               = fields.JSONField(default=dict) # Dict[str, int]
    class Meta:
        table = "bot_user"
    
    @classmethod
    async def get_or_create_bot(cls):
        """Get the unique bot user row or create it if not exists."""
        # try: bot_user = await cls.get(id=1)
        # except DoesNotExist: bot_user = await cls.create(id=1)
        # return bot_user
        return await cls.get_or_create(id=1)
    
    async def log_command(self, command_name: str) -> None:
        """Log a command execution, updating usage statistics."""
        self.commands_processed += 1
        if command_name not in self.features_used:
            self.features_used[command_name] = 0
        self.features_used[command_name] += 1
        await self.save()

class UserData(Model):
    """User activity and statistics tracker.
    
    Stores comprehensive user metrics including message stats,
    activity patterns, and progression data.
    
    Attributes:
        id (int): User's Discord ID
        name (str): Current display name
        level (int): User's current level
        xp (int): Experience points
        
    .. versionadded:: Nexon 0.3.0
    """
    # Required fields
    id                          = fields.BigIntField(pk=True, unique=True)
    name                        = fields.CharField(max_length=32)
    
    # Integer fields
    total_messages              = fields.IntField(default=0)
    character_count             = fields.IntField(default=0)
    word_count                  = fields.IntField(default=0)
    attachment_count            = fields.IntField(default=0)
    attachment_image_count      = fields.IntField(default=0)
    attachment_video_count      = fields.IntField(default=0)
    attachment_audio_count      = fields.IntField(default=0)
    attachment_other_count      = fields.IntField(default=0)
    gif_count                   = fields.IntField(default=0)
    mention_count               = fields.IntField(default=0)
    emoji_count                 = fields.IntField(default=0)
    custom_emoji_count          = fields.IntField(default=0)
    sticker_count               = fields.IntField(default=0)
    replies_count               = fields.IntField(default=0)
    reactions_given_count       = fields.IntField(default=0)
    reactions_received_count    = fields.IntField(default=0)
    commands_used_count         = fields.IntField(default=0)
    links_count                 = fields.IntField(default=0)
    edited_messages_count       = fields.IntField(default=0)
    deleted_messages_count      = fields.IntField(default=0)
    level                       = fields.IntField(default=1)
    xp                          = fields.IntField(default=0)
    
    # Date/Time fields
    created_at                  = fields.DatetimeField(null=True)
    birthdate                   = fields.DateField(null=True) 
    last_update                 = fields.DatetimeField(auto_now=True)
    last_message                = fields.DatetimeField(null=True)
    
    # JSON fields with proper encoder/decoder
    unique_names                : Set[str]   = fields.JSONField(default=lambda: {'__type__': 'set', 'items': []}, encoder=SetJSONEncoder().encode, decoder=lambda s: json.loads(s, object_hook=set_json_decoder)) # type: ignore
    unique_users_mentioned      : Set[int]   = fields.JSONField(default=lambda: {'__type__': 'set', 'items': []}, encoder=SetJSONEncoder().encode, decoder=lambda s: json.loads(s, object_hook=set_json_decoder)) # type: ignore
    unique_emojis_used          : Set[str]   = fields.JSONField(default=lambda: {'__type__': 'set', 'items': []}, encoder=SetJSONEncoder().encode, decoder=lambda s: json.loads(s, object_hook=set_json_decoder)) # type: ignore
    unique_custom_emojis_used   : Set[str]   = fields.JSONField(default=lambda: {'__type__': 'set', 'items': []}, encoder=SetJSONEncoder().encode, decoder=lambda s: json.loads(s, object_hook=set_json_decoder)) # type: ignore
    unique_domains              : Set[str]   = fields.JSONField(default=lambda: {'__type__': 'set', 'items': []}, encoder=SetJSONEncoder().encode, decoder=lambda s: json.loads(s, object_hook=set_json_decoder)) # type: ignore
    favorites_commands          : Dict[str, int]  = fields.JSONField(default=dict)  # type: ignore
    preferred_channels          : Dict[str, int]  = fields.JSONField(default=dict)  # type: ignore
    
    @classmethod
    async def get_or_create_user(cls, user: Union['Member', 'UserClass', 'BaseUser']):
        """Get the unique user row or create it if not exists."""
        return await cls.get_or_create(id=user.id, name=user.display_name, created_at=user.created_at)
    
    async def add_xp(self, amount: int) -> Optional[dict]:
        """
        Add XP to a user and handle level ups with XP carryover.

        Each level requires XP based on a triangular number formula:
            XP required for level n = 100 * n(n+1) / 2

        Returns:
            bool: True if the user leveled up.
        """
        
        if amount < 0:
            raise ValueError("XP amount must be non-negative")

        old_level = self.level
        self.xp += amount
        new_level = floor((sqrt(1 + (8 * self.xp / 100)) - 1) / 2) + 1
        previous_level_xp_threshold = (100 * (new_level - 1) * new_level) // 2
        if new_level > old_level:
            self.level = new_level
            self.xp -= previous_level_xp_threshold
            level_up_info = {
                'old_level': old_level,
                'new_level': new_level,
                'xp_gained': amount,
                'xp_carried_over': self.xp
            }
            await self.save()
            return level_up_info
        await self.save()
        return None

    class Meta:
        table = "users_data"

# 🏅 Badge Model
class Badge(Model):
    """Badge model for achievements.
    
    Attributes:
        id (int): Badge ID
        name (str): Badge name
        description (str): Badge description
        icon_url (str): URL to badge icon
        created_at (datetime): Creation timestamp
        guild_id (int): Guild-specific badge ID
        rarity (Rarity): Badge rarity
        hidden (bool): If the badge is hidden
        
    .. versionadded:: Nexon 0.3.0
    """
    id = fields.IntField(pk=True)  # Primary Key
    name = fields.CharField(max_length=100, unique=True)
    description = fields.TextField()
    icon_url = fields.CharField(max_length=255)  # Image URL
    created_at = fields.DatetimeField(auto_now_add=True)  # Creation timestamp
    guild_id = fields.IntField(null=True)  # Nullable, for guild-specific badges
    rarity = fields.IntEnumField(Rarity, default=Rarity.common)  # Enum for rarity
    hidden = fields.BooleanField(default=False)  # If the badge is hidden

    # Relationship with BadgeRequirement
    requirements: fields.ReverseRelation["BadgeRequirement"]
    
    class Meta:
        table = "badges"
    
    async def get_requirements(self) -> list[tuple[RequirementType, ComparisonType, str]]:
        """Retrieve a list of badge requirements.

        Returns:
            list of tuples containing (Requirement Type, Comparison, Value)
        """
        requirements = await self.requirements.all()  # Fetch all related requirements
        return [(req.type, req.comparison, req.value) for req in requirements]
    
    @classmethod
    async def create_badge_with_requirements(
        cls,
        name: str,
        description: str,
        icon_url: str,
        rarity: Rarity,
        hidden: bool,
        guild_id: Optional[int],
        requirements: Optional[list[tuple[RequirementType, ComparisonType, str]]]
    ) -> 'Badge':
        """Creates a badge with its associated requirements.

        Args:
            name (str): Badge name.
            description (str): Badge description.
            icon_url (str): URL to the badge icon.
            rarity (Rarity): Rarity enum.
            hidden (bool): Whether the badge is hidden.
            guild_id (Optional[int]): Guild ID if it's a guild-specific badge.
            requirements (list[tuple[RequirementType, ComparisonType, str]]): 
                List of requirements where each entry is (type, comparison, value).

        Returns:
            Badge: The created badge object.
        """
        badge = await cls.create(
            name=name,
            description=description,
            icon_url=icon_url,
            rarity=rarity,
            hidden=hidden,
            guild_id=guild_id
        )

        if requirements:
            requirement_objs = [
                BadgeRequirement(badge=badge, type=req_type, comparison=req_comparison, value=req_value)
                for req_type, req_comparison, req_value in requirements
            ]
    
            await BadgeRequirement.bulk_create(requirement_objs)  # Efficient batch insert
        return badge
    async def to_dict(self) -> dict:
        """Convert the Badge object into a dictionary, including its requirements."""
        requirements = await self.requirements.all()  # Fetch all requirements

        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "icon_url": self.icon_url,
            "created_at": self.created_at.isoformat(),  # Convert datetime to string
            "guild_id": self.guild_id,
            "rarity": self.rarity.name,  # Convert Enum to string
            "hidden": self.hidden,
            "requirements": [
                {
                    "type": req.type.name,
                    "comparison": req.comparison.name,
                    "value": req.value
                }
                for req in requirements
            ]
        }

    


# 📝 Badge Requirement Model (For tracking badge conditions)
class BadgeRequirement(Model):
    """Badge requirement model.
    
    Attributes:
        id (int): Requirement ID
        badge (Badge): Related badge
        type (RequirementType): Type of requirement
        value (str): Requirement value
        comparison (ComparisonType): Comparison operator
        
    .. versionadded:: Nexon 0.3.0
    """
    id = fields.IntField(pk=True)
    badge = fields.ForeignKeyField("models.Badge", related_name="requirements", on_delete=fields.CASCADE)
    type = fields.CharEnumField(RequirementType)  # Enum for requirement type
    value = fields.CharField(max_length=255, default="1")  # Numeric value (e.g., level 5, messages 100)
    comparison = fields.CharEnumField(ComparisonType, default=ComparisonType.GREATER_EQUAL)
    
    class Meta:
        table = "badge_requirements"
        unique_together = ("badge", "type")
    
    def compare(self, user_value: int, second_value: Optional[int] = None) -> bool:
        """Compare integer values based on the requirement type and comparison operator."""
        value = second_value or int(self.value)
        if self.comparison == ComparisonType.GREATER_EQUAL:
            return user_value >= value
        elif self.comparison == ComparisonType.LESS_EQUAL:
            return user_value <= value
        elif self.comparison == ComparisonType.EQUAL:
            return user_value == value
        elif self.comparison == ComparisonType.GREATER:
            return user_value > value
        elif self.comparison == ComparisonType.LESS:
            return user_value < value
        return False

class UserBadge(Model):
    """User badge model.
    
    Attributes:
        id (int): User badge ID
        user_id (int): User ID
        badge (Badge): Related badge
        obtained_at (datetime): Timestamp when badge was obtained
        
    .. versionadded:: Nexon 0.3.0
    """
    id = fields.IntField(pk=True)
    user_id = fields.BigIntField()
    badge = fields.ForeignKeyField("models.Badge", related_name="user_badges", on_delete=fields.CASCADE)
    obtained_at = fields.DatetimeField(auto_now_add=True)
    
    class Meta:
        table = "user_badges"

class GuildData(Model):
    """Guild-specific settings and data.
    
    Attributes:
        id (int): Guild ID
        name (str): Guild name
        created_at (datetime): Guild creation timestamp
        total_messages (int): Total messages in the guild
        last_update (datetime): Last update timestamp
        features_enabled (dict): Enabled features in the guild
        
    .. versionadded:: Nexon 0.3.0
    """
    # Required fields
    id                          = fields.BigIntField(pk=True)
    name                        = fields.CharField(max_length=100)
    created_at                  = fields.DatetimeField()
    
    # Integer fields
    total_messages              = fields.IntField(default=0)
    
    # Date/Time fields
    last_update                 = fields.DatetimeField(auto_now=True)
    
    # JSON fields
    features_enabled            = fields.JSONField(default=dict)
    
    class Meta:
        table = "guilds_data"
    
    @classmethod
    async def get_or_create_guild(cls, guild):
        """Get the unique guild row or create it if not exists."""
        return await cls.get_or_create(
            id=guild.id,
            name=guild.name,
            created_at=guild.created_at
        )

class Feature(Model):
    """Feature configuration storage model.
    
    This model stores feature settings for guilds, users, or globally.
    Similar to FeatureManager but persisted in database.
    
    Attributes:
        id (int): Feature entry ID
        name (str): Feature identifier/name
        scope_type (str): Type of scope ('guild', 'user', 'global')
        scope_id (int): ID of the guild/user (null for global)
        settings (dict): Feature settings and configuration
        enabled (bool): Whether feature is enabled
        updated_at (datetime): Last update timestamp
        
    .. versionadded:: Nexon 0.3.0
    """
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=255)
    scope_type = fields.CharEnumField(ScopeType, default= ScopeType.GLOBAL, max_length=15)  # 'guild', 'user', 'global'
    scope_id = fields.BigIntField(null=True)  # null for global features
    settings = fields.JSONField(default=dict)
    enabled = fields.BooleanField(default=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "features"
        unique_together = (("name", "scope_type", "scope_id"),)

    @classmethod
    async def get_guild_feature(cls, guild_id: int, feature_name: str) -> Optional['Feature']:
        """Get a feature for a specific guild."""
        feature,_ = await cls.get_or_create(
            name=feature_name,
            scope_type=ScopeType.GUILD,
            scope_id=guild_id,
            defaults={'settings': {}}
        )
        return feature

    @classmethod
    async def get_user_feature(cls, user_id: int, feature_name: str) -> Optional['Feature']:
        """Get a feature for a specific user."""
        feature, _ = await cls.get_or_create(
            name=feature_name,
            scope_type=ScopeType.USER,
            scope_id=user_id,
            defaults={'settings': {}}
        )
        return feature

    async def set_setting(self, key: str, value: Any) -> None:
        """Set a feature setting."""
        self.settings[key] = value
        await self.save()

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a feature setting."""
        return self.settings.get(key, default)

    async def enable(self) -> None:
        """Enable this feature."""
        self.enabled = True
        await self.save()

    async def disable(self) -> None:
        """Disable this feature."""
        self.enabled = False
        await self.save()

    async def delete_setting(self, key: str) -> bool:
        """Delete a feature setting."""
        if key in self.settings:
            del self.settings[key]
            await self.save()
            return True
        return False