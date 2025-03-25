"""
nexon.data.models
~~~~~~~~~~~~~~

models for the bot's database.

:copyright: (c) 2025 Mahirox36
:license: MIT, see LICENSE for more details.
"""
import json
from tortoise import Model, fields
from typing import Dict, Set, Union, Optional, TYPE_CHECKING

from ..enums import ComparisonType, Rarity, RequirementType

if TYPE_CHECKING:
    from ..user import User, BaseUser
    from ..member import Member

__all__ = (
    "SetJSONEncoder",
    "set_json_decoder",
    "BotUser",
    "UserData",
    "Badge",
    "BadgeRequirement",
    "UserBadge",
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

class UserData(Model):
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
    level                       = fields.IntField(default=0)
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
    async def get_or_create_user(cls, user: Union['Member', 'User', 'BaseUser']):
        """Get the unique user row or create it if not exists."""
        return await cls.get_or_create(id=user.id, name=user.display_name, created_at=user.created_at)

    
    class Meta:
        table = "users_data"

# 🏅 Badge Model
class Badge(Model):
    id = fields.IntField(pk=True)  # Primary Key
    name = fields.CharField(max_length=100, unique=True)
    description = fields.TextField()
    icon_url = fields.CharField(max_length=255)  # Image URL
    created_at = fields.DatetimeField(auto_now_add=True)  # Creation timestamp
    guild_id = fields.IntField(null=True)  # Nullable, for guild-specific badges
    rarity = fields.CharEnumField(Rarity, default=Rarity.common)  # Enum for rarity
    hidden = fields.BooleanField(default=False)  # If the badge is hidden

    # Relationship with BadgeRequirement
    requirements: fields.ReverseRelation["BadgeRequirement"]
    
    class Meta:
        table = "badges"
        
    


# 📝 Badge Requirement Model (For tracking badge conditions)
class BadgeRequirement(Model):
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
    id = fields.IntField(pk=True)
    user_id = fields.BigIntField()
    badge = fields.ForeignKeyField("models.Badge", related_name="user_badges", on_delete=fields.CASCADE)
    obtained_at = fields.DatetimeField(auto_now_add=True)
    
    class Meta:
        table = "user_badges"

class GuildData(Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=100)
    
    class Meta:
        table = "guilds_data"