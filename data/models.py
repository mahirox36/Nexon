"""
nexon.data.models
~~~~~~~~~~~~~~

Database models for the Nexon Discord bot.

Models:
- BotUser: Tracks bot-wide statistics and settings
- UserData: Stores user activity and statistics
- MemberData: Stores user activity and statistics
- Badge/UserBadge: Achievement system
- GuildData: Server-specific settings and data
- Feature system: Modular feature management
- AIPersonality: Stores AI personality traits and states

Usage:
    from nexon.data.models import UserData
    user = await UserData.get_or_create_user(member)
    await user.increment_messages()
"""

from datetime import datetime, timedelta
import json
from math import floor, sqrt
import re
from tortoise import fields, Model
from typing import Any, Dict, List, Set, Union, Optional, TYPE_CHECKING
from ..utils import extract_emojis
from ..enums import ComparisonType, Rarity, RequirementType, ScopeType
from .. import utils

if TYPE_CHECKING:
    from ..interactions import Interaction
    from ..user import User
    from ..member import Member
    from ..message import Message
    from ..guild import Guild

__all__ = (
    "SetJSONEncoder",
    "set_json_decoder",
    "BotUser",
    "UserData",
    "Badge",
    "BadgeRequirement",
    "UserBadge",
    "GuildData",
    "MemberData",
    "Feature",
    "MetricsCollector",
    "AIPersonality",
)


class SetJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, set):
            return {"__type__": "set", "items": list(obj)}
        return super().default(obj)


def set_json_decoder(obj):
    if "__type__" in obj and obj["__type__"] == "set":
        return set(obj["items"])
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
    id = fields.BigIntField(pk=True)

    # Integer fields
    total_messages = fields.IntField(default=0)
    commands_processed = fields.IntField(default=0)
    errors_encountered = fields.IntField(default=0)

    # Date/Time fields
    created_at = fields.DatetimeField(null=True)
    updated_at = fields.DatetimeField(auto_now=True)

    # JSON fields
    commands_errors = fields.JSONField(default=dict)  # Dict[str, List[str]]
    features_used = fields.JSONField(default=dict)  # Dict[str, int]

    class Meta:
        table = "bot_user"

    @classmethod
    async def get_or_create_bot(cls):
        """Get the unique bot user row or create it if not exists."""
        return await cls.get_or_create(id=1)

    @classmethod
    async def log_command(cls, command_name: str) -> None:
        """Log a command execution, updating usage statistics."""
        bot, _ = await cls.get_or_create_bot()
        bot.commands_processed += 1
        if command_name not in bot.features_used:
            bot.features_used[command_name] = 0
        bot.features_used[command_name] += 1
        await bot.save()

    @classmethod
    async def log_error(cls, error_message: str) -> None:
        """Log an error message, updating error statistics."""
        bot, _ = await cls.get_or_create_bot()
        bot.errors_encountered += 1
        if "errors" not in bot.commands_errors:
            bot.commands_errors["errors"] = []
        bot.commands_errors["errors"].append(error_message)
        await bot.save()

    @classmethod
    async def log_message(cls) -> None:
        """Log a message, updating message statistics."""
        bot, _ = await cls.get_or_create_bot()
        bot.total_messages += 1
        await bot.save()


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
    id = fields.BigIntField(pk=True, unique=True)
    name = fields.CharField(max_length=32)
    members = fields.ReverseRelation["MemberData"]

    # Integer fields
    total_messages = fields.IntField(default=0)
    character_count = fields.IntField(default=0)
    word_count = fields.IntField(default=0)
    attachment_count = fields.IntField(default=0)
    attachment_image_count = fields.IntField(default=0)
    attachment_video_count = fields.IntField(default=0)
    attachment_audio_count = fields.IntField(default=0)
    attachment_other_count = fields.IntField(default=0)
    gif_count = fields.IntField(default=0)
    mention_count = fields.IntField(default=0)
    emoji_count = fields.IntField(default=0)
    custom_emoji_count = fields.IntField(default=0)
    sticker_count = fields.IntField(default=0)
    replies_count = fields.IntField(default=0)
    reactions_given_count = fields.IntField(default=0)
    reactions_received_count = fields.IntField(default=0)
    commands_used_count = fields.IntField(default=0)
    links_count = fields.IntField(default=0)
    edited_messages_count = fields.IntField(default=0)
    deleted_messages_count = fields.IntField(default=0)
    longest_message = fields.IntField(default=0)

    # XP-related fields
    level = fields.IntField(default=1)
    xp = fields.IntField(default=0)
    xp_multiplier = fields.FloatField(default=1.0)
    last_xp_gain = fields.DatetimeField(null=True)
    daily_xp_gained = fields.IntField(default=0)
    daily_xp_reset = fields.DatetimeField(null=True)
    activity_streak = fields.IntField(default=0)
    longest_streak = fields.IntField(default=0)
    total_xp_gained = fields.IntField(default=0)
    milestone_rewards = fields.JSONField(default=dict, null=True)  # Dict[str, bool

    # Date/Time fields
    created_at = fields.DatetimeField(null=True)
    birthdate = fields.DateField(null=True)
    updated_at = fields.DatetimeField(auto_now=True)
    last_message = fields.DatetimeField(null=True)

    # JSON fields with proper encoder/decoder
    unique_names: Set[str] = fields.JSONField(default=lambda: {"__type__": "set", "items": []}, encoder=SetJSONEncoder().encode, decoder=lambda s: json.loads(s, object_hook=set_json_decoder))  # type: ignore
    unique_users_mentioned: Set[int] = fields.JSONField(default=lambda: {"__type__": "set", "items": []}, encoder=SetJSONEncoder().encode, decoder=lambda s: json.loads(s, object_hook=set_json_decoder))  # type: ignore
    unique_emojis_used: Set[str] = fields.JSONField(default=lambda: {"__type__": "set", "items": []}, encoder=SetJSONEncoder().encode, decoder=lambda s: json.loads(s, object_hook=set_json_decoder))  # type: ignore
    unique_custom_emojis_used: Set[str] = fields.JSONField(default=lambda: {"__type__": "set", "items": []}, encoder=SetJSONEncoder().encode, decoder=lambda s: json.loads(s, object_hook=set_json_decoder))  # type: ignore
    unique_domains: Set[str] = fields.JSONField(default=lambda: {"__type__": "set", "items": []}, encoder=SetJSONEncoder().encode, decoder=lambda s: json.loads(s, object_hook=set_json_decoder))  # type: ignore
    favorites_commands: Dict[str, int] = fields.JSONField(default=dict)  # type: ignore
    preferred_channels: Dict[str, int] = fields.JSONField(default=dict)  # type: ignore
    last_command_use: Dict[str, float] = fields.JSONField(default=dict, null=True)  # type: ignore

    @classmethod
    async def get_or_create_user(cls, user: Union["User", "Member"]):
        """Get the unique user row or create it if not exists."""
        try:
            return await cls.get(id=user.id), False
        except:
            name = user.global_name or user.name
            return (
                await cls.create(id=user.id, name=name, created_at=user.created_at),
                True,
            )

    async def set_birthdate(self, birthdate: datetime | str) -> None:
        """Set the user's birthdate"""
        try:
            self.birthdate = (
                datetime.strptime(birthdate, "%Y-%m-%d").date()
                if isinstance(birthdate, str)
                else birthdate
            )
            await self.save()
        except ValueError:
            raise ValueError("Invalid date format. Use YYYY-MM-DD.")

    async def calculate_xp_gain(
        self, activity_type: str, content_length: int = 0
    ) -> int:
        """Calculate XP gain based on activity type and various multipliers."""
        base_xp = {
            "message": 5,
            "voice": 3,
            "reaction": 1,
            "attachment": 3,
            "command": 2,
        }.get(activity_type, 1)

        # Content length bonus (for messages)
        if activity_type == "message" and content_length > 0:
            base_xp += min(
                content_length // 50, 5
            )  # Up to 5 bonus XP for longer messages

        # Time-based multiplier (more XP during less active hours)
        hour = utils.utcnow().hour
        time_multiplier = 1.5 if hour < 6 or hour > 22 else 1.0

        # Streak multiplier
        streak_multiplier = min(
            1.0 + (self.activity_streak * 0.1), 2.0
        )  # Up to 2x for streaks

        # Level-based multiplier (higher levels = slightly more XP)
        level_multiplier = 1.0 + (self.level * 0.01)  # 1% increase per level

        # Calculate final XP
        final_xp = int(
            base_xp
            * time_multiplier
            * streak_multiplier
            * level_multiplier
            * self.xp_multiplier
        )

        return max(1, final_xp)  # Minimum 1 XP

    async def can_gain_xp(self) -> bool:
        """Check if user can gain XP (implements cooldown)."""
        if not self.last_xp_gain:
            return True

        cooldown = timedelta(seconds=30)  # 30 second cooldown
        return utils.utcnow() - self.last_xp_gain > cooldown

    async def update_streak(self) -> None:
        """
        Update the user's daily activity streak and reset daily XP if needed.

        - Resets daily XP at midnight (based on local server time).
        - Increments streak if user was active yesterday.
        - Resets streak if user missed a day.
        - Updates longest streak if broken.
        """
        now = utils.utcnow()
        reset_needed = (
            not self.daily_xp_reset or now.date() > self.daily_xp_reset.date()
        )

        if reset_needed:
            # Determine if streak should increment or reset
            if self.last_xp_gain:
                days_since_last = (now.date() - self.last_xp_gain.date()).days
                if days_since_last == 1:
                    self.activity_streak += 1
                elif days_since_last > 1:
                    self.activity_streak = 1
                # If days_since_last == 0, user is active today, streak unchanged
            else:
                self.activity_streak = 1  # First activity ever

            self.longest_streak = max(self.activity_streak, self.longest_streak)
            self.daily_xp_gained = 0
            self.daily_xp_reset = now

        await self.save()

    async def check_milestone_rewards(self) -> Optional[dict]:
        """Check and award milestone rewards."""
        milestones = {
            "first_message": 1,
            "level_10": 10,
            "level_25": 25,
            "level_50": 50,
            "level_100": 100,
        }

        reward = None
        for milestone, level_req in milestones.items():
            if self.level >= level_req and not self.milestone_rewards.get(milestone):
                self.milestone_rewards[milestone] = True
                reward = {
                    "milestone": milestone,
                    "xp_multiplier": 0.1,  # Permanent 10% XP boost
                    "bonus_xp": level_req * 100,  # One-time XP bonus
                }
                self.xp_multiplier += reward["xp_multiplier"]
                await self.add_xp(reward["bonus_xp"])
                break

        await self.save()
        return reward

    async def add_xp(self, amount: int, activity_type: str = "other") -> Optional[dict]:
        """Enhanced XP addition with various bonuses and checks."""
        if not await self.can_gain_xp():
            return None

        # Update streak and daily stats
        await self.update_streak()

        # Calculate XP with multipliers
        actual_xp = await self.calculate_xp_gain(activity_type, amount)
        self.daily_xp_gained += actual_xp
        self.total_xp_gained += actual_xp
        self.last_xp_gain = utils.utcnow()

        # Original level up logic
        old_level = self.level
        self.xp += actual_xp
        new_level = floor((sqrt(1 + (8 * self.xp / 100)) - 1) / 2) + 1

        if new_level > old_level:
            self.level = new_level
            level_up_info = {
                "old_level": old_level,
                "new_level": new_level,
                "xp_gained": actual_xp,
                "streak_bonus": self.activity_streak > 0,
                "streak_count": self.activity_streak,
                "daily_total": self.daily_xp_gained,
            }

            # Check for milestone rewards
            milestone_reward = await self.check_milestone_rewards()
            if milestone_reward:
                level_up_info["milestone"] = milestone_reward

            await self.save()
            return level_up_info

        await self.save()
        return None

    # Activity tracking methods
    async def increment_messages(self, content: str) -> None:
        """Update message-related statistics."""
        self.total_messages += 1
        self.character_count += len(content.replace(" ", ""))
        self.word_count += len(content.split())
        await self.save()

    async def get_rank(self) -> int:
        """Get user's rank based on XP."""
        higher_users = await UserData.filter(xp__gt=self.xp).count()
        return higher_users + 1

    # Badge related methods
    async def get_badges(self) -> list["Badge"]:
        """Get all badges earned by user."""
        return await Badge.filter(user_badges__user_id=self.id)

    async def increment_command_count(self, interaction: "Interaction") -> None:
        """Increment the command usage count"""
        if not interaction.data or interaction.data.get("type", 0) != 1:
            return
        command_name = interaction.data.get("name", "Unknown")
        self.favorites_commands[command_name] = (
            self.favorites_commands.get(command_name, 0) + 1
        )
        if self.last_command_use is None:
            self.last_command_use = {}
        self.last_command_use[command_name] = utils.utcnow().timestamp()
        self.commands_used_count += 1
        await self.save()
        await BotUser.log_command(command_name)

    async def generalUpdateInfo(self, user: Union["User", "Member"]):
        """Only call this method for UserData instances"""
        displayName = user.global_name or user.name
        if displayName == self.name:
            return
        self.name = displayName
        self.unique_names.add(displayName)
        await self.save()

    async def track_attachment(self, type: str) -> None:
        """Track attachment for both member and user."""
        self.attachment_count += 1
        if type.startswith("image"):
            self.attachment_image_count += 1
        elif type.startswith("video"):
            self.attachment_video_count += 1
        elif type.startswith("audio"):
            self.attachment_audio_count += 1
        else:
            self.attachment_other_count += 1
        await self.save()

    async def add_mentioned_user(self, user_ids: List[int]) -> None:
        """Add mentioned user to both member and user."""
        self.mention_count += len(user_ids)
        self.unique_users_mentioned.update(user_ids)
        await self.save()

    async def add_emojis(self, emojis: List[str], is_custom: bool = False) -> None:
        """Add emoji to both member and user."""
        if is_custom:
            self.unique_custom_emojis_used.update(emojis)
            self.custom_emoji_count += len(emojis)
        else:
            self.unique_emojis_used.update(emojis)
            self.emoji_count += len(emojis)
        await self.save()

    async def add_domains(self, domains: List[str]) -> None:
        """Add domain to both member and user."""
        self.links_count += len(domains)
        self.unique_domains.update(domains)
        await self.save()

    async def add_channel_use(self, channel: str) -> None:
        """Track channel usage for both member and user."""
        self.preferred_channels[channel] = self.preferred_channels.get(channel, 0) + 1
        await self.save()

    async def add_replies(self, message: "Message"):
        self.replies_count += 1 if message.reference else 0
        await self.save()

    async def add_gifs(self, gifs: List[str]):
        self.gif_count += len(gifs)
        await self.save()

    async def add_attachments(self, message: "Message"):
        if len(message.attachments) >= 1:
            for att in message.attachments:
                await self.track_attachment(
                    att.content_type if att.content_type else "other"
                )

    async def incrementMessageCount(self, message: "Message"):
        """Only call this method for UserData instances"""

        await self.generalUpdateInfo(message.author)
        await self.increment_messages(message.content)
        await self.add_channel_use(str(message.channel.id))
        await self.add_attachments(message)
        await self.add_mentioned_user(re.findall(r"<@(\d+)>", message.content))
        await self.add_emojis(extract_emojis(message.content))
        await self.add_emojis(
            re.findall(r"<a?:[a-zA-Z0-9_]+:(\d+)>", message.content), True
        )
        await self.add_replies(message)
        await self.add_domains(
            re.findall(r"https?://(?:www\.)?([a-zA-Z0-9.-]+)", message.content)
        )
        await self.add_gifs(re.findall(r"https?://tenor\.com/\S+", message.content))
        if len(message.content) > self.longest_message:
            self.longest_message = len(message.content)

    class Meta:
        table = "users_data"


class MemberData(Model):
    user: fields.ForeignKeyRelation["UserData"] = fields.ForeignKeyField(
        "models.UserData", related_name="members", on_delete=fields.CASCADE
    )
    guild: fields.ForeignKeyRelation["GuildData"] = fields.ForeignKeyField(
        "models.GuildData", related_name="members", on_delete=fields.CASCADE
    )
    name = fields.CharField(max_length=32)

    # Integer fields
    total_messages = fields.IntField(default=0)
    character_count = fields.IntField(default=0)
    word_count = fields.IntField(default=0)
    attachment_count = fields.IntField(default=0)
    attachment_image_count = fields.IntField(default=0)
    attachment_video_count = fields.IntField(default=0)
    attachment_audio_count = fields.IntField(default=0)
    attachment_other_count = fields.IntField(default=0)
    gif_count = fields.IntField(default=0)
    mention_count = fields.IntField(default=0)
    emoji_count = fields.IntField(default=0)
    custom_emoji_count = fields.IntField(default=0)
    sticker_count = fields.IntField(default=0)
    replies_count = fields.IntField(default=0)
    reactions_given_count = fields.IntField(default=0)
    reactions_received_count = fields.IntField(default=0)
    commands_used_count = fields.IntField(default=0)
    links_count = fields.IntField(default=0)
    edited_messages_count = fields.IntField(default=0)
    deleted_messages_count = fields.IntField(default=0)
    longest_message = fields.IntField(default=0)

    # XP-related fields
    level = fields.IntField(default=1)
    xp = fields.IntField(default=0)
    xp_multiplier = fields.FloatField(default=1.0)
    last_xp_gain = fields.DatetimeField(null=True)
    daily_xp_gained = fields.IntField(default=0)
    daily_xp_reset = fields.DatetimeField(null=True)
    activity_streak = fields.IntField(default=0)
    longest_streak = fields.IntField(default=0)
    total_xp_gained = fields.IntField(default=0)
    milestone_rewards = fields.JSONField(default=dict, null=True)  # Dict[str, bool

    # Date/Time fields
    created_at = fields.DatetimeField(null=True)
    updated_at = fields.DatetimeField(auto_now=True)
    last_message = fields.DatetimeField(null=True)

    # JSON fields with proper encoder/decoder
    unique_names: Set[str] = fields.JSONField(default=lambda: {"__type__": "set", "items": []}, encoder=SetJSONEncoder().encode, decoder=lambda s: json.loads(s, object_hook=set_json_decoder))  # type: ignore
    unique_users_mentioned: Set[int] = fields.JSONField(default=lambda: {"__type__": "set", "items": []}, encoder=SetJSONEncoder().encode, decoder=lambda s: json.loads(s, object_hook=set_json_decoder))  # type: ignore
    unique_emojis_used: Set[str] = fields.JSONField(default=lambda: {"__type__": "set", "items": []}, encoder=SetJSONEncoder().encode, decoder=lambda s: json.loads(s, object_hook=set_json_decoder))  # type: ignore
    unique_custom_emojis_used: Set[str] = fields.JSONField(default=lambda: {"__type__": "set", "items": []}, encoder=SetJSONEncoder().encode, decoder=lambda s: json.loads(s, object_hook=set_json_decoder))  # type: ignore
    unique_domains: Set[str] = fields.JSONField(default=lambda: {"__type__": "set", "items": []}, encoder=SetJSONEncoder().encode, decoder=lambda s: json.loads(s, object_hook=set_json_decoder))  # type: ignore
    favorites_commands: Dict[str, int] = fields.JSONField(default=dict)  # type: ignore
    preferred_channels: Dict[str, int] = fields.JSONField(default=dict)  # type: ignore
    last_command_use: Dict[str, float] = fields.JSONField(default=dict, null=True)  # type: ignore

    @classmethod
    async def get_or_create_user(cls, user: "Member"):
        """Ensure UserData exists before creating MemberData."""
        user_data, _ = await UserData.get_or_create_user(user)
        guild_data, _ = await GuildData.get_or_create_guild(user.guild)
        try:
            member = await cls.get(user=user_data, guild=guild_data)
            await member.fetch_related("user")
            await member.fetch_related("guild")
            return member, False
        except:
            return (
                await cls.create(
                    user=user_data,
                    name=user.display_name,
                    guild=guild_data,
                    created_at=user.created_at,
                ),
                True,
            )

    @classmethod
    async def try_get_or_create_user(cls, user: Union["Member", "User"]):
        """Get the unique user row or create it if not exists."""
        if isinstance(user, User):
            return await UserData.get_or_create_user(user)
        return await cls.get_or_create_user(user)

    class Meta:
        table = "members_data"
        unique_together = [("user_id", "guild")]

    async def generalUpdateInfo(self, user: Union["User", "Member"]):
        """Only call this method for UserData instances"""
        if user.display_name == self.name:
            return
        self.name = user.display_name
        self.unique_names.add(user.display_name)
        await self.save()

    async def set_birthdate(self, birthdate: datetime | str) -> None:
        """Set the user's birthdate"""
        await self.user.set_birthdate(birthdate)

    # Override increment methods to update both member and user
    async def increment_messages(self, content: str) -> None:
        """Update message statistics for both member and user."""
        # Update both models
        for model in (self, self.user):
            model.total_messages += 1
            model.character_count += len(content.replace(" ", ""))
            model.word_count += len(content.split())
            await model.save()

    async def track_attachment(self, type: str) -> None:
        """Track attachment for both member and user."""
        for model in (self, self.user):
            model.attachment_count += 1
            if type.startswith("image"):
                model.attachment_image_count += 1
            elif type.startswith("video"):
                model.attachment_video_count += 1
            elif type.startswith("audio"):
                model.attachment_audio_count += 1
            else:
                model.attachment_other_count += 1
            await model.save()

    async def increment_command_count(self, interaction: "Interaction") -> None:
        """Increment the command usage count"""
        for model in (self, self.user):
            if not interaction.data or interaction.data.get("type", 0) != 1:
                continue
            command_name = interaction.data.get("name", "Unknown")
            model.favorites_commands[command_name] = (
                model.favorites_commands.get(command_name, 0) + 1
            )
            model.commands_used_count += 1
            await model.save()
        await BotUser.log_command(command_name)

    # Methods for updating sets and dictionaries
    async def add_mentioned_user(self, user_ids: List[int]) -> None:
        """Add mentioned user to both member and user."""
        for model in (self, self.user):
            model.mention_count += len(user_ids)
            model.unique_users_mentioned.update(user_ids)
            await model.save()

    async def add_emojis(self, emojis: List[str], is_custom: bool = False) -> None:
        """Add emoji to both member and user."""
        for model in (self, self.user):
            if is_custom:
                model.unique_custom_emojis_used.update(emojis)
                model.custom_emoji_count += len(emojis)
            else:
                model.unique_emojis_used.update(emojis)
                model.emoji_count += len(emojis)
            await model.save()

    async def add_domains(self, domains: List[str]) -> None:
        """Add domain to both member and user."""
        for model in (self, self.user):
            model.links_count += len(domains)
            model.unique_domains.update(domains)
            await model.save()

    async def add_channel_use(self, channel: str) -> None:
        """Track channel usage for both member and user."""
        for model in (self, self.user):
            model.preferred_channels[channel] = (
                model.preferred_channels.get(channel, 0) + 1
            )
            await model.save()

    async def add_replies(self, message: "Message"):
        for model in (self, self.user):
            model.replies_count += 1 if message.reference else 0
            await model.save()

    async def add_gifs(self, gifs: List[str]):
        for model in (self, self.user):
            model.gif_count += len(gifs)
            await model.save()

    async def add_attachments(self, message: "Message"):
        if len(message.attachments) >= 1:
            for att in message.attachments:
                await self.track_attachment(
                    att.content_type if att.content_type else "other"
                )

    async def incrementMessageCount(self, message: "Message"):
        """Only call this method for UserData instances"""
        await self.generalUpdateInfo(message.author)
        await self.increment_messages(message.content)
        await self.add_channel_use(str(message.channel.id))
        await self.add_attachments(message)
        await self.add_mentioned_user(re.findall(r"<@(\d+)>", message.content))
        await self.add_emojis(extract_emojis(message.content))
        await self.add_emojis(
            re.findall(r"<a?:[a-zA-Z0-9_]+:(\d+)>", message.content), True
        )
        await self.add_replies(message)
        await self.add_domains(
            re.findall(r"https?://(?:www\.)?([a-zA-Z0-9.-]+)", message.content)
        )
        await self.add_gifs(re.findall(r"https?://tenor\.com/\S+", message.content))


# 🏅 Badge Model
class Badge(Model):
    """Badge model for achievements.

    Attributes:
        id (int): Badge ID
        name (str): Badge name
        description (str): Badge description
        icon_url (str): URL to badge icon
        emoji (str): Custom Emoji of the badge
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
    emoji = fields.CharField(max_length=255)
    created_at = fields.DatetimeField(auto_now_add=True)  # Creation timestamp
    guild_id = fields.BigIntField(null=True)  # Nullable, for guild-specific badges
    rarity = fields.IntEnumField(Rarity, default=Rarity.common)  # Enum for rarity
    hidden = fields.BooleanField(default=False)  # If the badge is hidden
    updated_at = fields.DatetimeField(auto_now=True)

    # Relationship with BadgeRequirement
    requirements: fields.ReverseRelation["BadgeRequirement"]

    class Meta:
        table = "badges"
        indexes = [
            "name",  # Index for name field
            "rarity",  # Index for rarity field
        ]
        index_together = [  # Define composite index using index_together
            ("guild_id", "name")  # Composite index for guild_id and name
        ]

    async def get_requirements(
        self,
    ) -> list[tuple[RequirementType, ComparisonType, str]]:
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
        emoji: str,
        rarity: Rarity,
        hidden: bool,
        guild_id: Optional[int],
        requirements: Optional[list[tuple[RequirementType, ComparisonType, str]]],
    ) -> "Badge":
        """Creates a badge with its associated requirements.

        Args:
            name (str): Badge name.
            description (str): Badge description.
            icon_url (str): URL to the badge icon.
            emoji (str): Custom Emoji of the badge
            rarity (Rarity): Rarity enum.
            hidden (bool): Whether the badge is hidden.
            guild_id (Optional[int]): Guild ID if it's a guild-specific badge.
            requirements (list[tuple[RequirementType, ComparisonType, str]]):
                List of requirements where each entry is (type, comparison, value).

        Returns:
            Badge: The created badge object.
        """
        # Check if badge with the same name already exists
        existing_badge = await Badge.filter(name=name).first()
        if existing_badge:
            raise Exception(f"Badge with name '{name}' already exists.")

        # Create the badge
        badge = await cls.create(
            name=name,
            description=description,
            icon_url=icon_url,
            emoji=emoji,
            rarity=rarity,
            hidden=hidden,
            guild_id=guild_id,
        )

        if requirements:
            # Create the requirements
            requirement_objs = [
                BadgeRequirement(
                    badge=badge,
                    type=req_type,
                    comparison=req_comparison,
                    value=req_value,
                )
                for req_type, req_comparison, req_value in requirements
            ]
            await BadgeRequirement.bulk_create(requirement_objs)

        return badge

    async def to_dict(self) -> Dict[str, Union[str, int, bool, List[Dict[str, str]]]]:
        """Convert the Badge object into a dictionary, including its requirements."""
        requirements = await self.requirements.all()  # Fetch all requirements

        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "icon_url": self.icon_url,
            "emoji": self.emoji,
            "created_at": self.created_at.isoformat(),  # Convert datetime to string
            "guild_id": self.guild_id,
            "rarity": self.rarity.name,  # Convert Enum to string
            "hidden": self.hidden,
            "requirements": [
                {
                    "type": req.type.name,
                    "comparison": req.comparison.name,
                    "value": req.value,
                }
                for req in requirements
            ],
        }

    @property
    def rarity_color(self) -> int:
        """Get color code for badge rarity."""
        colors = {
            Rarity.common: 0x808080,  # Gray
            Rarity.uncommon: 0x00FF00,  # Green
            Rarity.rare: 0x0000FF,  # Blue
            Rarity.epic: 0x800080,  # Purple
            Rarity.legendary: 0xFFD700,  # Gold
        }
        return colors.get(self.rarity, 0x000000)

    async def award_to(self, user_id: int) -> "UserBadge":
        """Award badge to user if they don't already have it."""
        existing = await UserBadge.get_or_none(user_id=user_id, badge=self)
        if existing:
            raise ValueError("User already has this badge")

        return await UserBadge.create(user_id=user_id, badge=self)


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
    badge = fields.ForeignKeyField(
        "models.Badge", related_name="requirements", on_delete=fields.CASCADE
    )
    type = fields.CharEnumField(RequirementType)  # Enum for requirement type
    value = fields.CharField(
        max_length=255, default="1"
    )  # Numeric value (e.g., level 5, messages 100)
    comparison = fields.CharEnumField(
        ComparisonType, default=ComparisonType.GREATER_EQUAL
    )

    class Meta:
        table = "badge_requirements"

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

    # async def get_user_progress(self, user: 'UserData') -> tuple[int, int]:
    #     """Get user's progress towards this requirement.

    #     Returns:
    #         Tuple of (current_value, target_value)
    #     """
    #     target = int(self.value)
    #     current = 0

    #     if self.type == RequirementType.MESSAGES:
    #         current = user.total_messages
    #     elif self.type == RequirementType.LEVEL:
    #         current = user.level
    #     # Add more requirement types as needed

    #     return current, target

    def format_requirement(self) -> str:
        """Format requirement as human readable string."""
        comp_symbols = {
            ComparisonType.GREATER_EQUAL: "≥",
            ComparisonType.LESS_EQUAL: "≤",
            ComparisonType.EQUAL: "=",
            ComparisonType.GREATER: ">",
            ComparisonType.LESS: "<",
        }
        return f"{self.type.name.title()} {comp_symbols[self.comparison]} {self.value}"


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
    badge: fields.ForeignKeyRelation["Badge"] = fields.ForeignKeyField(
        "models.Badge", related_name="user_badges", on_delete=fields.CASCADE
    )
    obtained_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "user_badges"

    from typing import Sequence

    @classmethod
    async def get_user_badges(cls, user_id: int) -> Sequence["UserBadge"]:
        """Get all badges for a specific user."""
        return await cls.filter(user_id=user_id).prefetch_related("badge").all()

    async def to_dict(self) -> Dict[str, Union[int, str]]:
        """Convert the UserBadge object into a dictionary."""
        badge_dict = await self.badge.to_dict()
        combined_dict = {
            **badge_dict,
            "obtained_at": self.obtained_at.isoformat(),  # Convert datetime to string
        }
        return combined_dict


class GuildData(Model):
    """Guild-specific settings and data.

    Attributes:
        id (int): Guild ID
        name (str): Guild name
        created_at (datetime): Guild creation timestamp
        total_messages (int): Total messages in the guild
        updated_at (datetime): Last update timestamp

    .. versionadded:: Nexon 0.3.0
    """

    # Required fields
    id = fields.BigIntField(pk=True)
    name = fields.CharField(max_length=100)
    created_at = fields.DatetimeField()

    members = fields.ReverseRelation["MemberData"]

    # Integer fields
    total_messages = fields.IntField(default=0)

    # Date/Time fields
    updated_at = fields.DatetimeField(auto_now=True)

    deletion_requested_at = fields.DatetimeField(null=True)

    class Meta:
        table = "guilds_data"

    @classmethod
    async def get_or_create_guild(cls, guild: "Guild"):
        """Get the unique guild row or create it if not exists."""
        return await cls.get_or_create(
            id=guild.id,
            defaults={"name": guild.name, "created_at": guild.created_at},
        )

    def is_pending_deletion(self) -> bool:
        return self.deletion_requested_at is not None

    def deletion_due(self) -> bool:
        if self.deletion_requested_at is None:
            return False
        return utils.utcnow() >= self.deletion_requested_at + timedelta(days=3)

    async def request_deletion(self):
        self.deletion_requested_at = utils.utcnow()
        await self.save()

    async def cancel_deletion(self):
        self.deletion_requested_at = None
        await self.save()


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
    scope_type = fields.CharEnumField(
        ScopeType, default=ScopeType.GLOBAL, max_length=15
    )  # 'guild', 'user', 'global'
    scope_id = fields.BigIntField(null=True)  # null for global features
    settings = fields.JSONField(default=dict)
    enabled = fields.BooleanField(default=True)
    updated_at = fields.DatetimeField(auto_now=True)
    deletion_requested_at = fields.DatetimeField(null=True)

    class Meta:
        table = "features"
        unique_together = [("name", "scope_type", "scope_id")]

    @classmethod
    async def get_guild_feature(
        cls, guild_id: int, feature_name: str, default: Any = {}
    ) -> "Feature":
        """Get a feature for a specific guild."""
        feature, _ = await cls.get_or_create(
            name=feature_name,
            scope_type=ScopeType.GUILD,
            scope_id=guild_id,
            defaults={"settings": {"settings": default}},
        )
        return feature

    @classmethod
    async def get_guild_feature_or_none(
        cls, guild_id: int, feature_name: str, default: Any = {}
    ) -> Optional["Feature"]:
        """Get a feature for a specific guild."""
        feature = await cls.get_or_none(
            name=feature_name, scope_type=ScopeType.GUILD, scope_id=guild_id
        )
        return feature

    @classmethod
    async def get_user_feature(
        cls, user_id: int, feature_name: str, default: Any = {}
    ) -> "Feature":
        """Get a feature for a specific user."""
        feature, _ = await cls.get_or_create(
            name=feature_name,
            scope_type=ScopeType.USER,
            scope_id=user_id,
            defaults={"settings": {"settings": default}},
        )
        return feature

    @classmethod
    async def get_global_feature(
        cls, feature_name: str, default: Any = {}
    ) -> "Feature":
        """Get a global feature"""
        feature, _ = await cls.get_or_create(
            name=feature_name,
            scope_type=ScopeType.GLOBAL,
            defaults={"settings": {"settings": default}},
        )
        return feature

    @classmethod
    async def delete_guild_features(cls, guild_id: int) -> None:
        """Delete all features for a specific guild."""
        await cls.filter(scope_type=ScopeType.GUILD, scope_id=guild_id).delete()

    @classmethod
    async def soft_delete_guild_features(cls, guild_id: int) -> None:
        """Soft delete all features for a specific guild."""
        features = await cls.filter(scope_type=ScopeType.GUILD, scope_id=guild_id)
        for feature in features:
            if not feature.is_pending_deletion():
                await feature.request_deletion()

    @classmethod
    async def cancel_soft_delete_guild_features(cls, guild_id: int) -> None:
        """Cancel soft delete for all features for a specific guild."""
        features = await cls.filter(scope_type=ScopeType.GUILD, scope_id=guild_id)
        for feature in features:
            if feature.is_pending_deletion():
                await feature.cancel_deletion()

    @classmethod
    async def delete_user_features(cls, user_id: int) -> None:
        """Delete all features for a specific user."""
        await cls.filter(scope_type=ScopeType.USER, scope_id=user_id).delete()

    async def set_setting(self, key: str, value: Any) -> None:
        """Set a feature setting."""
        if "settings" not in self.settings:
            self.settings["settings"] = {}
        self.settings["settings"][key] = value
        await self.save()

    def get_setting(self, key: Optional[str] = None, default: Any = {}) -> Any:
        """Get a feature setting."""
        if "settings" not in self.settings:
            self.settings["settings"] = default
        if key is None:
            return self.settings.get("settings", default)
        return self.settings["settings"].get(key, default)

    async def replace_settings(self, settings: Any) -> None:
        """Replace all settings."""
        self.settings["settings"] = settings
        await self.save()

    async def reset_settings(self) -> None:
        """Reset all settings to default."""
        self.settings["settings"] = {}
        await self.save()

    async def set_global(self, key: str, value: Any) -> None:
        """Set a feature setting."""
        self.settings[key] = value
        await self.save()

    def get_global(self, key: str, default: Any = {}) -> Any:
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

    async def delete_class(self):
        """Delete everything"""
        await self.delete()

    def is_pending_deletion(self) -> bool:
        return self.deletion_requested_at is not None

    def deletion_due(self) -> bool:
        if self.deletion_requested_at is None:
            return False
        return utils.utcnow() >= self.deletion_requested_at + timedelta(days=3)

    async def request_deletion(self):
        self.deletion_requested_at = utils.utcnow()
        await self.save()

    async def cancel_deletion(self):
        self.deletion_requested_at = None
        await self.save()

    async def to_dict(self):
        """Convert the Feature object into a dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "scope_type": self.scope_type.name,
            "scope_id": self.scope_id,
            "settings": self.settings,
            "enabled": self.enabled,
            "updated_at": self.updated_at.isoformat(),
        }


class MetricsCollector(Model):
    """Stores historical metrics data for system and bot statistics.

    Attributes:
        timestamp (datetime): When the metrics were collected
        cpu_usage (float): CPU usage percentage
        memory_usage (float): Memory usage percentage
        memory_total (int): Total system memory
        disk_usage (float): Disk usage percentage
        bot_latency (float): Bot latency in ms
        guild_count (int): Number of guilds
        user_count (int): Total number of users
        voice_connections (int): Active voice connections
        commands_processed (int): Commands processed in this interval
    """

    id = fields.IntField(pk=True)
    timestamp = fields.DatetimeField(auto_now_add=True)

    # System metrics
    cpu_usage = fields.FloatField()
    memory_usage = fields.FloatField()
    memory_total = fields.BigIntField()
    disk_usage = fields.FloatField()
    thread_count = fields.IntField()

    # Bot metrics
    bot_latency = fields.FloatField()
    guild_count = fields.IntField()
    user_count = fields.IntField()
    channel_count = fields.IntField()
    voice_connections = fields.IntField()
    commands_processed = fields.IntField()
    messages_sent = fields.IntField()
    errors_encountered = fields.IntField()

    class Meta:
        table = "metrics_history"

    @classmethod
    async def add_metrics(cls, system_stats: dict, bot_stats: dict) -> None:
        """Add new metrics entry"""
        await cls.create(
            cpu_usage=system_stats["cpu_usage"],
            memory_usage=system_stats["memory_usage"],
            memory_total=system_stats["memory_total"],
            disk_usage=system_stats["disk_usage"],
            thread_count=system_stats["thread_count"],
            bot_latency=bot_stats["latency"],
            guild_count=bot_stats["guild_count"],
            user_count=bot_stats["user_count"],
            channel_count=bot_stats["channel_count"],
            voice_connections=bot_stats["voice_connections"],
            commands_processed=bot_stats["commands_processed"],
            messages_sent=bot_stats["messages_sent"],
            errors_encountered=bot_stats["errors_encountered"],
        )

    @classmethod
    async def get_historical_data(cls, hours: int = 24) -> dict:
        """Get historical metrics for the specified time period"""
        cutoff = utils.utcnow() - timedelta(hours=hours)
        metrics = await cls.filter(timestamp__gte=cutoff).order_by("timestamp")

        return {
            "timestamps": [m.timestamp.timestamp() for m in metrics],
            "cpu_usage": [m.cpu_usage for m in metrics],
            "memory_usage": [m.memory_usage for m in metrics],
            "bot_latency": [m.bot_latency for m in metrics],
            "guild_count": [m.guild_count for m in metrics],
            "user_count": [m.user_count for m in metrics],
            "commands_processed": [m.commands_processed for m in metrics],
            "messages_sent": [m.messages_sent for m in metrics],
        }


class AIPersonality(Model):
    """Stores AI personality traits and relationship data.

    This model stores the AI's personality state including core traits,
    learned preferences, relationship dynamics, and emotional memory.

    Attributes:
        id (int): AI personality entry ID
        name (str): Name of this personality profile
        core_traits (dict): Core personality traits (openness, conscientiousness, etc.)
        learned_preferences (dict): Dictionary of learned user preferences
        relationship_dynamics (dict): Dictionary of relationship states with users
        emotional_memory (list): List of significant emotional interactions
        mood_tracker (dict): Current and recent emotional states
        creation_date (datetime): When this personality was created
        last_update (datetime): Last time this personality was updated

    """

    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=100, default="Default")
    core_traits = fields.JSONField(
        default=lambda: {
            "openness": 0.85,
            "conscientiousness": 0.9,
            "extraversion": 0.75,
            "agreeableness": 0.85,
            "stability": 0.8,
            "curiosity": 0.9,
            "empathy": 0.95,
            "adaptability": 0.85,
        }
    )
    learned_preferences = fields.JSONField(default=dict)  # User-specific preferences
    relationship_dynamics = fields.JSONField(default=dict)  # User relationship states
    emotional_memory = fields.JSONField(default=list)  # Important emotional moments
    mood_tracker = fields.JSONField(
        default=lambda: {
            "current_mood": "relaxed",
            "mood_since": utils.utcnow().timestamp(),
            "recent_moods": [],
        }
    )
    creation_date = fields.DatetimeField(auto_now_add=True)
    last_update = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "ai_personality"

    @classmethod
    async def get_default(cls):
        """Get or create default personality profile."""
        profile, created = await cls.get_or_create(name="Default")
        if created:
            # Initialize with advanced emotional intelligence traits
            profile.emotional_memory = [
                {
                    "type": "initial_creation",
                    "timestamp": utils.utcnow().timestamp(),
                    "description": "I was first activated and began learning about the world.",
                    "mood": "curious",
                    "intensity": 0.8,
                }
            ]
            await profile.save()
        return profile

    async def update_mood(
        self,
        new_mood: str,
        intensity: float = 0.5,
        trigger: str = "general interaction",
    ):
        """Update the AI's current mood.

        Args:
            new_mood (str): The new mood state
            intensity (float): Intensity of the mood (0.0-1.0)
            trigger (str): What triggered this mood change
        """
        current_time = utils.utcnow().timestamp()

        # Store previous mood in history
        if self.mood_tracker["current_mood"] != new_mood:
            previous_mood = {
                "mood": self.mood_tracker["current_mood"],
                "started": self.mood_tracker["mood_since"],
                "ended": current_time,
                "duration": current_time - self.mood_tracker["mood_since"],
                "trigger": trigger,
            }

            # Keep only recent moods (last 10)
            recent_moods = self.mood_tracker.get("recent_moods", [])
            recent_moods.append(previous_mood)
            if len(recent_moods) > 10:
                recent_moods = recent_moods[-10:]

            # Update mood tracker
            self.mood_tracker = {
                "current_mood": new_mood,
                "mood_since": current_time,
                "intensity": intensity,
                "trigger": trigger,
                "recent_moods": recent_moods,
            }
            await self.save()

    async def create_emotional_memory(
        self,
        user_id: int,
        event_type: str,
        description: str,
        impact: float,
        associated_mood: Optional[str] = None,
    ):
        """Store a significant emotional memory.

        Args:
            user_id (int): ID of the user involved
            event_type (str): Type of emotional event
            description (str): Description of what happened
            impact (float): How significant this event is (-1.0 to 1.0)
            associated_mood (str, optional): Mood associated with this memory
        """
        # Create the memory entry
        memory = {
            "user_id": user_id,
            "type": event_type,
            "timestamp": utils.utcnow().timestamp(),
            "description": description,
            "impact": impact,
            "mood": associated_mood or self.mood_tracker["current_mood"],
        }

        # Add to emotional memories
        if not isinstance(self.emotional_memory, list):
            self.emotional_memory = []

        self.emotional_memory.append(memory)

        # Limit memory size
        if len(self.emotional_memory) > 100:
            # Sort by impact and keep most significant
            self.emotional_memory = sorted(
                self.emotional_memory, key=lambda x: abs(x["impact"]), reverse=True
            )[:100]

        await self.save()

    async def update_relationship(
        self,
        user_id: int,
        familiarity_change: float = 0.01,
        trust_change: float = 0,
        affinity_change: float = 0,
    ):
        """Update relationship dynamics with a user.

        Args:
            user_id (int): ID of the user
            familiarity_change (float): Change in familiarity (-1.0 to 1.0)
            trust_change (float): Change in trust (-1.0 to 1.0)
            affinity_change (float): Change in affinity/liking (-1.0 to 1.0)
        """
        user_id_str = str(user_id)

        # Initialize relationship if it doesn't exist
        if not self.relationship_dynamics.get(user_id_str):
            self.relationship_dynamics[user_id_str] = {
                "familiarity": 0.1,
                "trust": 0.5,
                "affinity": 0.5,
                "first_interaction": utils.utcnow().timestamp(),
                "last_interaction": utils.utcnow().timestamp(),
                "interaction_count": 0,
                "significant_interactions": [],
            }

        # Update relationship values
        relationship = self.relationship_dynamics[user_id_str]
        relationship["familiarity"] = min(
            1.0, max(0.0, relationship["familiarity"] + familiarity_change)
        )
        relationship["trust"] = min(1.0, max(0.0, relationship["trust"] + trust_change))
        relationship["affinity"] = min(
            1.0, max(0.0, relationship["affinity"] + affinity_change)
        )
        relationship["last_interaction"] = utils.utcnow().timestamp()
        relationship["interaction_count"] += 1

        await self.save()

    def get_user_relationship(self, user_id: int) -> dict:
        """Get relationship data for a specific user.

        Args:
            user_id (int): ID of the user

        Returns:
            dict: Relationship data or default values if not found
        """
        user_id_str = str(user_id)
        default_relationship = {
            "familiarity": 0.1,
            "trust": 0.5,
            "affinity": 0.5,
            "first_interaction": utils.utcnow().timestamp(),
            "last_interaction": utils.utcnow().timestamp(),
            "interaction_count": 0,
        }

        return self.relationship_dynamics.get(user_id_str, default_relationship)

    async def learn_preference(
        self, user_id: int, preference_type: str, preference_value: Any
    ):
        """Learn and store a user preference.

        Args:
            user_id (int): ID of the user
            preference_type (str): Type of preference (topics, style, etc)
            preference_value (Any): The preference value to store
        """
        user_id_str = str(user_id)

        # Initialize preferences if they don't exist
        if not self.learned_preferences.get(user_id_str):
            self.learned_preferences[user_id_str] = {}

        # Store the preference
        self.learned_preferences[user_id_str][preference_type] = preference_value
        await self.save()
