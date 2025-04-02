"""
nexon.data.user
~~~~~~~~~~~~~~

Represents Discord users with statistical data tracking.

:copyright: (c) 2025 Mahirox36
:license: MIT, see LICENSE for more details.
"""

from datetime import datetime
from tortoise.exceptions import DoesNotExist
import re
from typing import TYPE_CHECKING, Union
from ..utils import extract_emojis
from .models import UserData

if TYPE_CHECKING:
    from ..member import Member
    from ..user import User, BaseUser
    from ..interactions import Interaction
    from ..message import Message

__all__ = (
    "UserManager",
)

class UserManager:
    def __init__(self, user: Union['User', 'Member', 'BaseUser']):
        self.user = user
        # no need to put Optional as long as the person who uses this class uses only by the from_user method
        self.data: UserData

    @classmethod
    async def from_user(cls, user: Union['User', 'Member', 'BaseUser']):
        instance = cls(user)
        instance.data, _ = await UserData.get_or_create_user(user)
        return instance
    
    async def save(self):
        if not self.data:
            raise ValueError("User data not initialized.")
        await self.data.save()
    
    async def delete(self):
        if not self.data:
            raise ValueError("User data not initialized.")
        await self.data.delete()
    async def update(self, **kwargs):
        if not self.data:
            raise ValueError("User data not initialized.")
        for key, value in kwargs.items():
            if hasattr(self.data, key):
                setattr(self.data, key, value)
            else:
                raise ValueError(f"Invalid field: {key}")
        await self.data.save()
        
    async def generalUpdateInfo(self):
        """Only call this method for UserData instances"""
        if not self.data:
            raise ValueError("User data not initialized.")
            
        if self.user.display_name == self.data.name:
            return
            
        self.data.unique_names.add(self.data.name)
        self.data.name = self.user.display_name
        self.data.last_updated = datetime.now()
        await self.save()

    async def incrementMessageCount(self, message: 'Message'):
        """Only call this method for UserData instances"""
        if not self.data:
            raise ValueError("User data not initialized.")
            
        await self.generalUpdateInfo()
        self.data.last_message = datetime.now()
        # await self.BadgeDetect(message)
        content = message.content
        self.data.total_messages += 1
        self.data.character_count += len(content.replace(" ", ""))
        self.data.word_count += len(content.split())
        self.data.preferred_channels[str(message.channel.id)] = \
            self.data.preferred_channels.get(str(message.channel.id), 0) + 1

        self.data.attachment_count += len(message.attachments)
        if len(message.attachments) >= 1:
            for att in message.attachments:
                if att.content_type and (
                    att.content_type.startswith("image") or
                    att.content_type.startswith("video") or  
                    att.content_type.startswith("audio")
                ):
                    media_type = att.content_type.split('/')[0]
                    if media_type == 'image':
                        self.data.attachment_image_count += 1
                    elif media_type == 'video':
                        self.data.attachment_video_count += 1
                    elif media_type == 'audio':
                        self.data.attachment_audio_count += 1
                else:
                    self.data.attachment_other_count += 1
        mentions = re.findall(r"<@(\d+)>", content)
        self.data.mention_count += len(mentions)
        self.data.unique_users_mentioned.update(mentions)
        #<a:dddd:706660674780266536>
        emojis = extract_emojis(content)
        self.data.emoji_count += len(emojis)
        self.data.unique_emojis_used.update(emojis)
        customEmojis = re.findall(r"<a?:[a-zA-Z0-9_]+:(\d+)>", content)
        self.data.custom_emoji_count += len(customEmojis)
        self.data.unique_custom_emojis_used.update(customEmojis)
        self.data.replies_count += 1 if message.reference else 0
        links = re.findall(r"https?://(?:www\.)?([a-zA-Z0-9.-]+)", content)
        self.data.links_count += len(links)
        self.data.unique_domains.update(links)
        gifs = re.findall(r'https?://tenor\.com/\S+', content)
        self.data.gif_count += len(gifs)
        
        await self.save()
    
    async def commandCount(self, interaction: 'Interaction'):
        """Command track usage"""
        if not self.data:
            raise ValueError("User data not initialized.")
        
        if interaction.application_command is None:
            return
        if interaction.application_command.name is None:
            return
        await self.generalUpdateInfo()
        try:
            command_name = interaction.application_command.name
            await self.increment_command_count(command_name)
            # await cls.BadgeDetect(user_manager, interaction)
        except:
            pass
        finally:
            await self.save()
    
    async def increment_command_count(self, command_name: str) -> None:
        """Increment the command usage count"""
        if not self.data:
            raise ValueError("User data not initialized.")
        
        self.data.commands_used_count += 1
        self.data.favorites_commands[command_name] = \
            self.data.favorites_commands.get(command_name, 0) + 1
        await self.save()
    
    async def set_birthdate(self, birthdate: datetime | str) -> None:
        """Set the user's birthdate"""
        if not self.data:
            raise ValueError("User data not initialized.")
        
        try:
            self.data.birthdate = datetime.strptime(birthdate, "%Y-%m-%d").date() if isinstance(birthdate, str) else birthdate
            await self.save()
        except ValueError:
            raise ValueError("Invalid date format. Use YYYY-MM-DD.")