from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Set, Optional, Type, Union, TYPE_CHECKING
import re
import json
from datetime import datetime
from ..message import Message
from ..dataManager import DataManager
from ..utils import extract_emojis

if TYPE_CHECKING:
    from ..member import Member
    from ..user import User
    from ..interactions import Interaction

@dataclass
class AttachmentTypes:
    images: int = 0
    videos: int = 0
    audio: int = 0
    other: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> 'AttachmentTypes':
        if isinstance(data, cls):
            return data
        return cls(**data)

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class BotStatistics:
    joined_at: str
    messages_sent: int = 0
    commands_processed: int = 0
    errors_encountered: int = 0
    features_used: Dict[str, int] = field(default_factory=dict)
    command_errors: Dict[str, List[str]] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'BotStatistics':
        if isinstance(data, cls):
            return data
        return cls(**data)
    
    @classmethod
    def from_member(cls, member: Union['Member', 'User']) -> 'BotStatistics':
        return cls(
            joined_at=str(member.created_at)
        )

@dataclass
class UserData:
    # Basic Info
    name: str 
    joined_at: str
    unique_names: Set[str] = field(default_factory=set)
    last_updated: Optional[datetime] = None
    
    # Message Statistics
    total_messages: int = 0
    character_count: int = 0
    word_count: int = 0
    
    # Content Analysis
    attachments_sent: int = 0
    attachment_types: AttachmentTypes = field(default_factory=AttachmentTypes)
    gif_sent: int = 0
    mentions_count: int = 0
    unique_users_mentioned: Set[int] = field(default_factory=set)
    emoji_count: int = 0
    custom_emoji_count: int = 0
    unique_emojis_used: Set[str] = field(default_factory=set)
    unique_custom_emojis_used: Set[str] = field(default_factory=set)
    preferred_channels: Dict[str, int] = field(default_factory=dict)
    
    # Interaction Patterns
    replies_count: int = 0
    reactions_received: int = 0 # didn't added yet
    reactions_given: int = 0    # didn't added yet
    
    # Command Usage
    commands_used: int = 0
    favorite_commands: Dict[str, int] = field(default_factory=dict)
    
    # Link Sharing
    links_shared: int = 0
    unique_domains: Set[str] = field(default_factory=set)
    
    # Message Types
    edited_messages: int = 0    # didn't added yet
    deleted_messages: int = 0   # didn't added yet
    
    # Special Events
    birthdate: Optional[datetime] = None
    
    # Achievement Tracking
    badges: Set[int] = field(default_factory=set)
    
    #Version
    version: int = 2

    custom_data: Dict[str, Any] = field(default_factory=dict)
    
    def set_custom_data(self, key: str, value: Any) -> None:
        """Set a custom data field"""
        self.custom_data[key] = value
        
    def get_custom_data(self, key: str, default: Any = None) -> Any:
        """Get a custom data field"""
        return self.custom_data.get(key, default)
    
    def __getitem__(self, key: str) -> Any:
        return self.get_custom_data(key)
        
    def __setitem__(self, key: str, value: Any) -> None:
        self.set_custom_data(key, value)
    
    @classmethod
    def migrate_user_data(cls, data: dict) -> dict:
        version = data.get('version', 0)
        if version == 0:
            data['version'] = 1
            if data.get("badges"):
                data["badges"] = set()
        if version == 1:
            data['version'] = 2
            data.pop("milestones")
            data.pop("reputation")
            
        return data
    
    @classmethod
    def from_dict(cls, data: Optional[dict] = None) -> 'UserData':
        """
        Safely create a UserData instance from a dictionary with default values for missing fields.
        """
        if data is None:
            data = {}

        data = data.copy()
        data = cls.migrate_user_data(data)

        # Extract and handle custom data separately
        custom_data = data.pop('custom_data', {})

        # Define defaults for all fields
        defaults = {
            'name': "Unknown",
            'birthdate': None,
            'joined_at': None,
            'last_updated': datetime.now(),
            'unique_users_mentioned': set(),
            'unique_emojis_used': set(),
            'unique_custom_emojis_used': set(),
            'unique_domains': set(),
            'unique_names': set(),
            'badges': set(),
            'favorite_commands': {},
            'preferred_channels': {},
            'attachment_types': AttachmentTypes()
        }

        # Process datetime fields
        for field in ['birthdate', 'last_updated']:
            if isinstance(data.get(field), str):
                try:
                    data[field] = datetime.fromisoformat(data[field])
                except (ValueError, TypeError):
                    data[field] = defaults[field]
            elif field not in data:
                data[field] = defaults[field]

        # Process set fields
        set_fields = [
            'unique_users_mentioned', 'unique_emojis_used', 
            'unique_custom_emojis_used', 'unique_domains',
            'unique_names', 'badges'
        ]
        for field in set_fields:
            try:
                data[field] = set(data.get(field, []))
            except (TypeError, ValueError):
                data[field] = set()

        # Process dictionary fields
        dict_fields = ['favorite_commands', 'preferred_channels',]
        for field in dict_fields:
            if not isinstance(data.get(field), dict):
                data[field] = {}

        # Handle complex objects
        if 'attachment_types' in data:
            if isinstance(data['attachment_types'], dict):
                try:
                    data['attachment_types'] = AttachmentTypes.from_dict(data['attachment_types'])
                except (ValueError, TypeError):
                    data['attachment_types'] = AttachmentTypes()
            elif not isinstance(data['attachment_types'], AttachmentTypes):
                data['attachment_types'] = AttachmentTypes()
        else:
            data['attachment_types'] = AttachmentTypes()

        # Create instance with processed data
        instance = cls(**{k: data.get(k, v) for k, v in defaults.items()})
        instance.custom_data = custom_data
        return instance

    def to_dict(self) -> dict:
        data = {
            # Basic Info
            "name": self.name,
            "joined_at": self.joined_at,
            "unique_names": list(self.unique_names),
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
            
            # Message Statistics
            "total_messages": self.total_messages,
            "character_count": self.character_count,
            "word_count": self.word_count,
            
            # Content Analysis
            "attachments_sent": self.attachments_sent,
            "attachment_types": self.attachment_types.to_dict(),
            "gif_sent": self.gif_sent,
            "mentions_count": self.mentions_count,
            "unique_users_mentioned": list(self.unique_users_mentioned),
            "emoji_count": self.emoji_count,
            "custom_emoji_count": self.custom_emoji_count,
            "unique_emojis_used": list(self.unique_emojis_used),
            "unique_custom_emojis_used": list(self.unique_custom_emojis_used),
            
            # Interaction Patterns
            "replies_count": self.replies_count,
            "reactions_received": self.reactions_received,
            "reactions_given": self.reactions_given,
            
            # Command Usage
            "commands_used": self.commands_used,
            "favorite_commands": self.favorite_commands,
            
            # Link Sharing
            "links_shared": self.links_shared,
            "unique_domains": list(self.unique_domains),
            
            # Message Types
            "edited_messages": self.edited_messages,
            "deleted_messages": self.deleted_messages,
            
            # Special Events
            "birthdate": self.birthdate.isoformat() if self.birthdate else None,
            
            # Preferences
            "preferred_channels": self.preferred_channels,
            
            # Achievement Tracking
            "badges": list(self.badges),
            
            #Version
            'version': self.version,
        }
        data['custom_data'] = self.custom_data
        return data

    @classmethod
    def from_member(cls, member: Union['Member', 'User']) -> 'UserData':
        return cls(
            name=member.display_name,
            joined_at=str(member.created_at),
            last_updated=datetime.now()
        )


class UserManager(DataManager):
    __slots__ = (
        "user_id",
        "_user_data",
        )
    def __init__(self, user: Union['Member', 'User'], defaultClass: Type[UserData | BotStatistics] = UserData):
        self.data: Dict[str, Any] = {}
        super().__init__(
            name="Users",
            file_name=str(user.id),
            default=defaultClass.from_member(user).to_dict(),
            entity_type="Users",
            add_name_folder=False
        )
        self.user_id = user.id
        self._user_data: UserData = self._load_user_data()
        self._user = user
        
    def _load_user_data(self) -> UserData:
        """Convert raw data to UserData object"""
        return UserData.from_dict(self.data)

    def save(self) -> None:
        """Save UserData to JSON file"""
        self.data = self._user_data.to_dict()
        super().save()
    
    def load(self) -> UserData:
        """Load JSON file and return as UserData object"""
        super().load()
        self._user_data = self._load_user_data()
        return self._user_data
    
    def delete(self):
        """Deletes the user data"""
        return super().delete(None)

    @property
    def user_data(self) -> UserData:
        """Access the UserData object"""
        return self._user_data
    
    def generalUpdateInfo(self):
        if self._user.display_name == self.user_data.name:
            return
        else:
            self.user_data.unique_names.add(self.user_data.name)
            self.user_data.name = self._user.display_name
            self.user_data.last_updated = datetime.now()
            return self.save()
    
    async def incrementMessageCount(self, message: Message):
        self.generalUpdateInfo()
        # await self.BadgeDetect(message)
        content = message.content
        self.user_data.total_messages += 1
        self.user_data.character_count += len(content.replace(" ", ""))
        self.user_data.word_count += len(content.split())
        self.user_data.preferred_channels[str(message.channel.id)] = \
            self.user_data.preferred_channels.get(str(message.channel.id), 0) + 1

        self.user_data.attachments_sent += len(message.attachments)
        if len(message.attachments) >= 1:
            for att in message.attachments:
                if att.content_type and (
                    att.content_type.startswith("image") or
                    att.content_type.startswith("video") or  
                    att.content_type.startswith("audio")
                ):
                    media_type = att.content_type.split('/')[0]
                    if media_type == 'image':
                        self.user_data.attachment_types.images += 1
                    elif media_type == 'video':
                        self.user_data.attachment_types.videos += 1
                    elif media_type == 'audio':
                        self.user_data.attachment_types.audio += 1
                else:
                    self.user_data.attachment_types.other += 1
        mentions = re.findall(r"<@(\d+)>", content)
        self.user_data.mentions_count += len(mentions)
        self.user_data.unique_users_mentioned.update(mentions)
        #<a:dddd:706660674780266536>
        emojis = extract_emojis(content)
        self.user_data.emoji_count += len(emojis)
        self.user_data.unique_emojis_used.update(emojis)
        customEmojis = re.findall(r"<a?:[a-zA-Z0-9_]+:(\d+)>", content)
        self.user_data.custom_emoji_count += len(customEmojis)
        self.user_data.unique_custom_emojis_used.update(customEmojis)
        self.user_data.replies_count += 1 if message.reference else 0
        links = re.findall(r"https?://(?:www\.)?([a-zA-Z0-9.-]+)", content)
        self.user_data.links_shared += len(links)
        self.user_data.unique_domains.update(links)
        gifs = re.findall(r'https?://tenor\.com/\S+', content)
        self.user_data.gif_sent += len(gifs)
        
        self.save()
    
    async def commandCount(self, interaction: 'Interaction'):
        """Command track usage"""
        if interaction.application_command is None:
            return
        if interaction.application_command.name is None:
            return
        self.generalUpdateInfo()
        try:
            command_name = interaction.application_command.name
            self.increment_command_count(command_name)
            # await cls.BadgeDetect(user_manager, interaction)
        except:
            pass
        finally:
            self.save()
    
    def increment_command_count(self, command_name: str) -> None:
        """Increment the command usage count"""
        
        self._user_data.commands_used += 1
        self._user_data.favorite_commands[command_name] = \
            self._user_data.favorite_commands.get(command_name, 0) + 1
        self.save()
    
    def __getattr__(self, name: str) -> Any:
        """Delegate unknown attributes to UserData object"""
        if hasattr(self._user_data, name):
            return getattr(self._user_data, name)
        raise AttributeError(f"'UserManager' object has no attribute '{name}'")
    
class BotManager(UserManager):
    def __init__(self, user: Union['Member', 'User']):
        super().__init__(user=user, defaultClass=BotStatistics)
        self._user_data: BotStatistics = self._load_user_data()
    
    def _load_user_data(self) -> BotStatistics:
        """Convert raw data to UserData object"""
        return BotStatistics.from_dict(self.data)
    
    @property
    def user_data(self) -> BotStatistics:
        """Access the BotStatistics object"""
        return self._user_data
    
    def record_bot_message(self):
        """Record a message sent by the bot"""
        self.init_bot_stats()
        self.user_data.messages_sent += 1
        self.save()

    def record_command_processed(self, command_name: str):
        """Record a processed command"""
        self.init_bot_stats()
        self.user_data.commands_processed += 1
        self.user_dat.features_used[command_name] = \
            self.user_data.features_used.get(command_name, 0) + 1
        self.save()

    def record_error(self, command_name: str, error_message: str):
        """Record an error that occurred"""
        self.init_bot_stats()
        self.user_data.errors_encountered += 1
        if command_name not in self.user_data.command_errors:
            self.user_data.command_errors[command_name] = []
        self.user_data.command_errors[command_name].append(error_message)
        self.save()