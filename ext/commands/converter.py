# SPDX-License-Identifier: MIT

from __future__ import annotations

import inspect
import re
from types import GenericAlias
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Generic,
    Iterable,
    List,
    Literal,
    Optional,
    Protocol,
    Tuple,
    Type,
    TypeVar,
    Union,
    runtime_checkable,
)

import nexon

from .errors import *

if TYPE_CHECKING:
    from typing import Callable

    from nexon.abc import PartialMessageableChannel
    from nexon.member import Member
    from nexon.user import User

    from .context import Context


__all__ = (
    "Converter",
    "ObjectConverter",
    "MemberConverter",
    "UserConverter",
    "MessageConverter",
    "PartialMessageConverter",
    "TextChannelConverter",
    "InviteConverter",
    "GuildConverter",
    "RoleConverter",
    "GameConverter",
    "ColourConverter",
    "ColorConverter",
    "VoiceChannelConverter",
    "StageChannelConverter",
    "EmojiConverter",
    "PartialEmojiConverter",
    "CategoryChannelConverter",
    "IDConverter",
    "ThreadConverter",
    "GuildChannelConverter",
    "GuildStickerConverter",
    "ScheduledEventConverter",
    "clean_content",
    "Greedy",
    "run_converters",
)


def _get_from_guilds(bot, getter, argument):
    result = None
    for guild in bot.guilds:
        result = getattr(guild, getter)(argument)
        if result:
            return result
    return result


_utils_get = nexon.utils.get
T = TypeVar("T")
T_co = TypeVar("T_co", covariant=True)
CT = TypeVar("CT", bound=nexon.abc.GuildChannel)
TT = TypeVar("TT", bound=nexon.Thread)


@runtime_checkable
class Converter(Protocol[T_co]):
    """The base class of custom converters that require the :class:`.Context`
    to be passed to be useful.

    This allows you to implement converters that function similar to the
    special cased ``discord`` classes.

    Classes that derive from this should override the :meth:`~.Converter.convert`
    method to do its conversion logic. This method must be a :ref:`coroutine <coroutine>`.
    """

    async def convert(self, ctx: Context, argument: str) -> T_co:
        """|coro|

        The method to override to do conversion logic.

        If an error is found while converting, it is recommended to
        raise a :exc:`.CommandError` derived exception as it will
        properly propagate to the error handlers.

        Parameters
        ----------
        ctx: :class:`.Context`
            The invocation context that the argument is being used in.
        argument: :class:`str`
            The argument that is being converted.

        Raises
        ------
        :exc:`.CommandError`
            A generic exception occurred when converting the argument.
        :exc:`.BadArgument`
            The converter failed to convert the argument.
        """
        raise NotImplementedError("Derived classes need to implement this.")


_ID_REGEX = re.compile(r"([0-9]{15,20})$")


class IDConverter(Converter[T_co]):
    @staticmethod
    def _get_id_match(argument):
        return _ID_REGEX.match(argument)


class ObjectConverter(IDConverter[nexon.Object]):
    """Converts to a :class:`~nexon.Object`.

    The argument must follow the valid ID or mention formats (e.g. ``<@80088516616269824>``).

    .. versionadded:: 2.0

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by member, role, or channel mention.
    """

    async def convert(self, ctx: Context, argument: str) -> nexon.Object:
        match = self._get_id_match(argument) or re.match(
            r"<(?:@(?:!|&)?|#)([0-9]{15,20})>$", argument
        )

        if match is None:
            raise ObjectNotFound(argument)

        result = int(match.group(1))

        return nexon.Object(id=result)


class MemberConverter(IDConverter[nexon.Member]):
    """Converts to a :class:`~nexon.Member`.

    All lookups are via the local guild. If in a DM context, then the lookup
    is done by the global cache.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by mention.
    3. Lookup by name#discrim
    4. Lookup by name
    5. Lookup by nickname

    .. versionchanged:: 1.5
         Raise :exc:`.MemberNotFound` instead of generic :exc:`.BadArgument`

    .. versionchanged:: 1.5.1
        This converter now lazily fetches members from the gateway and HTTP APIs,
        optionally caching the result if :attr:`.MemberCacheFlags.joined` is enabled.
    """

    async def query_member_named(self, guild, argument: str):
        cache = guild._state.member_cache_flags.joined
        if len(argument) > 5 and argument[-5] == "#":
            username, _, discriminator = argument.rpartition("#")
            members = await guild.query_members(username, limit=100, cache=cache)
            return nexon.utils.get(members, name=username, discriminator=discriminator)

        members = await guild.query_members(argument, limit=100, cache=cache)
        finder: Callable[[Member], bool] = lambda m: argument in {m.name, m.nick}
        return nexon.utils.find(finder, members)

    async def query_member_by_id(self, bot, guild, user_id):
        ws = bot._get_websocket(shard_id=guild.shard_id)
        cache = guild._state.member_cache_flags.joined
        if ws.is_ratelimited():
            # If we're being rate limited on the WS, then fall back to using the HTTP API
            # So we don't have to wait ~60 seconds for the query to finish
            try:
                member = await guild.fetch_member(user_id)
            except nexon.HTTPException:
                return None

            if cache:
                guild._add_member(member)
            return member

        # If we're not being rate limited then we can use the websocket to actually query
        members = await guild.query_members(limit=1, user_ids=[user_id], cache=cache)
        if not members:
            return None
        return members[0]

    async def convert(self, ctx: Context, argument: str) -> nexon.Member:
        bot = ctx.bot
        match = self._get_id_match(argument) or re.match(r"<@!?([0-9]{15,20})>$", argument)
        guild = ctx.guild
        result = None
        user_id = None
        if match is None:
            # not a mention...
            if guild:
                result = guild.get_member_named(argument)
            else:
                result = _get_from_guilds(bot, "get_member_named", argument)
        else:
            user_id = int(match.group(1))
            if guild:
                result = guild.get_member(user_id) or _utils_get(ctx.message.mentions, id=user_id)
            else:
                result = _get_from_guilds(bot, "get_member", user_id)

        if result is None:
            if guild is None:
                raise MemberNotFound(argument)

            if user_id is not None:
                result = await self.query_member_by_id(bot, guild, user_id)
            else:
                result = await self.query_member_named(guild, argument)

            if not result:
                raise MemberNotFound(argument)

        if not isinstance(result, nexon.Member):
            raise MemberNotFound(argument)

        return result


class UserConverter(IDConverter[nexon.User]):
    """Converts to a :class:`~nexon.User`.

    All lookups are via the global user cache.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by mention.
    3. Lookup by name#discrim
    4. Lookup by name

    .. versionchanged:: 1.5
         Raise :exc:`.UserNotFound` instead of generic :exc:`.BadArgument`

    .. versionchanged:: 1.6
        This converter now lazily fetches users from the HTTP APIs if an ID is passed
        and it's not available in cache.
    """

    async def convert(self, ctx: Context, argument: str) -> nexon.User:
        match = self._get_id_match(argument) or re.match(r"<@!?([0-9]{15,20})>$", argument)
        result = None
        state = ctx._state

        if match is not None:
            user_id = int(match.group(1))
            result = ctx.bot.get_user(user_id) or _utils_get(ctx.message.mentions, id=user_id)
            if result is None:
                try:
                    result = await ctx.bot.fetch_user(user_id)
                except nexon.HTTPException:
                    raise UserNotFound(argument) from None

            if not isinstance(result, nexon.User):
                raise UserNotFound(argument)

            return result

        arg = argument

        # Remove the '@' character if this is the first character from the argument
        if arg[0] == "@":
            # Remove first character
            arg = arg[1:]

        # check for discriminator if it exists,
        if len(arg) > 5 and arg[-5] == "#":
            discrim = arg[-4:]
            name = arg[:-5]
            predicate: Callable[[User], bool] = (
                lambda u: u.name == name and u.discriminator == discrim
            )
            result = nexon.utils.find(predicate, state._users.values())
            if result is not None:
                return result

        predicate = lambda u: u.name == arg
        result = nexon.utils.find(predicate, state._users.values())

        if result is None:
            raise UserNotFound(argument)

        return result


class PartialMessageConverter(Converter[nexon.PartialMessage]):
    """Converts to a :class:`nexon.PartialMessage`.

    .. versionadded:: 1.7

    The creation strategy is as follows (in order):

    1. By "{channel ID}-{message ID}" (retrieved by shift-clicking on "Copy ID")
    2. By message ID (The message is assumed to be in the context channel.)
    3. By message URL
    """

    @staticmethod
    def _get_id_matches(ctx, argument):
        id_regex = re.compile(r"(?:(?P<channel_id>[0-9]{15,20})-)?(?P<message_id>[0-9]{15,20})$")
        link_regex = re.compile(
            r"https?://(?:(ptb|canary|www)\.)?discord(?:app)?\.com/channels/"
            r"(?P<guild_id>[0-9]{15,20}|@me)"
            r"/(?P<channel_id>[0-9]{15,20})/(?P<message_id>[0-9]{15,20})/?$"
        )
        match = id_regex.match(argument) or link_regex.match(argument)
        if not match:
            raise MessageNotFound(argument)
        data = match.groupdict()
        channel_id = nexon.utils.get_as_snowflake(data, "channel_id")
        message_id = int(data["message_id"])
        guild_id = data.get("guild_id")
        if guild_id is None:
            guild_id = ctx.guild and ctx.guild.id
        elif guild_id == "@me":
            guild_id = None
        else:
            guild_id = int(guild_id)
        if channel_id is None:
            channel_id = ctx.channel.id
        return guild_id, message_id, channel_id

    @staticmethod
    def _resolve_channel(ctx, guild_id, channel_id) -> Optional[PartialMessageableChannel]:
        if guild_id is not None:
            guild = ctx.bot.get_guild(guild_id)
            if guild is not None and channel_id is not None:
                return guild._resolve_channel(channel_id)
            return None
        return ctx.bot.get_channel(channel_id) if channel_id else ctx.channel

    async def convert(self, ctx: Context, argument: str) -> nexon.PartialMessage:
        guild_id, message_id, channel_id = self._get_id_matches(ctx, argument)
        channel = self._resolve_channel(ctx, guild_id, channel_id)
        if not channel:
            raise ChannelNotFound(str(channel_id))
        return nexon.PartialMessage(channel=channel, id=message_id)


class MessageConverter(IDConverter[nexon.Message]):
    """Converts to a :class:`nexon.Message`.

    .. versionadded:: 1.1

    The lookup strategy is as follows (in order):

    1. Lookup by "{channel ID}-{message ID}" (retrieved by shift-clicking on "Copy ID")
    2. Lookup by message ID (the message **must** be in the context channel)
    3. Lookup by message URL

    .. versionchanged:: 1.5
         Raise :exc:`.ChannelNotFound`, :exc:`.MessageNotFound` or :exc:`.ChannelNotReadable` instead of generic :exc:`.BadArgument`
    """

    async def convert(self, ctx: Context, argument: str) -> nexon.Message:
        guild_id, message_id, channel_id = PartialMessageConverter._get_id_matches(ctx, argument)
        message = ctx.bot._connection._get_message(message_id)
        if message:
            return message
        channel = PartialMessageConverter._resolve_channel(ctx, guild_id, channel_id)
        if not channel:
            raise ChannelNotFound(str(channel_id))
        try:
            return await channel.fetch_message(message_id)
        except nexon.NotFound as e:
            raise MessageNotFound(argument) from e
        except nexon.Forbidden as e:
            raise ChannelNotReadable(channel) from e  # type: ignore  # weird type conflict


class GuildChannelConverter(IDConverter[nexon.abc.GuildChannel]):
    """Converts to a :class:`~nexon.abc.GuildChannel`.

    All lookups are via the local guild. If in a DM context, then the lookup
    is done by the global cache.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by mention.
    3. Lookup by name.

    .. versionadded:: 2.0
    """

    async def convert(self, ctx: Context, argument: str) -> nexon.abc.GuildChannel:
        return self._resolve_channel(ctx, argument, "channels", nexon.abc.GuildChannel)

    @staticmethod
    def _resolve_channel(ctx: Context, argument: str, attribute: str, type: Type[CT]) -> CT:
        bot = ctx.bot

        match = IDConverter._get_id_match(argument) or re.match(r"<#([0-9]{15,20})>$", argument)
        result = None
        guild = ctx.guild

        if match is None:
            # not a mention
            if guild:
                iterable: Iterable[CT] = getattr(guild, attribute)
                result: Optional[CT] = nexon.utils.get(iterable, name=argument)
            else:

                def check(c):
                    return isinstance(c, type) and c.name == argument

                result = nexon.utils.find(check, bot.get_all_channels())
        else:
            channel_id = int(match.group(1))
            if guild:
                result = guild.get_channel(channel_id)  # type: ignore
            else:
                result = _get_from_guilds(bot, "get_channel", channel_id)

        if not isinstance(result, type):
            raise ChannelNotFound(argument)

        return result

    @staticmethod
    def _resolve_thread(ctx: Context, argument: str, attribute: str, type: Type[TT]) -> TT:
        match = IDConverter._get_id_match(argument) or re.match(r"<#([0-9]{15,20})>$", argument)
        result = None
        guild = ctx.guild

        if match is None:
            # not a mention
            if guild:
                iterable: Iterable[TT] = getattr(guild, attribute)
                result: Optional[TT] = nexon.utils.get(iterable, name=argument)
        else:
            thread_id = int(match.group(1))
            if guild:
                result = guild.get_thread(thread_id)  # type: ignore  # handled below

        if not result or not isinstance(result, type):
            raise ThreadNotFound(argument)

        return result


class TextChannelConverter(IDConverter[nexon.TextChannel]):
    """Converts to a :class:`~nexon.TextChannel`.

    All lookups are via the local guild. If in a DM context, then the lookup
    is done by the global cache.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by mention.
    3. Lookup by name

    .. versionchanged:: 1.5
         Raise :exc:`.ChannelNotFound` instead of generic :exc:`.BadArgument`
    """

    async def convert(self, ctx: Context, argument: str) -> nexon.TextChannel:
        return GuildChannelConverter._resolve_channel(
            ctx, argument, "text_channels", nexon.TextChannel
        )


class VoiceChannelConverter(IDConverter[nexon.VoiceChannel]):
    """Converts to a :class:`~nexon.VoiceChannel`.

    All lookups are via the local guild. If in a DM context, then the lookup
    is done by the global cache.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by mention.
    3. Lookup by name

    .. versionchanged:: 1.5
         Raise :exc:`.ChannelNotFound` instead of generic :exc:`.BadArgument`
    """

    async def convert(self, ctx: Context, argument: str) -> nexon.VoiceChannel:
        return GuildChannelConverter._resolve_channel(
            ctx, argument, "voice_channels", nexon.VoiceChannel
        )


class StageChannelConverter(IDConverter[nexon.StageChannel]):
    """Converts to a :class:`~nexon.StageChannel`.

    .. versionadded:: 1.7

    All lookups are via the local guild. If in a DM context, then the lookup
    is done by the global cache.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by mention.
    3. Lookup by name
    """

    async def convert(self, ctx: Context, argument: str) -> nexon.StageChannel:
        return GuildChannelConverter._resolve_channel(
            ctx, argument, "stage_channels", nexon.StageChannel
        )


class CategoryChannelConverter(IDConverter[nexon.CategoryChannel]):
    """Converts to a :class:`~nexon.CategoryChannel`.

    All lookups are via the local guild. If in a DM context, then the lookup
    is done by the global cache.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by mention.
    3. Lookup by name

    .. versionchanged:: 1.5
         Raise :exc:`.ChannelNotFound` instead of generic :exc:`.BadArgument`
    """

    async def convert(self, ctx: Context, argument: str) -> nexon.CategoryChannel:
        return GuildChannelConverter._resolve_channel(
            ctx, argument, "categories", nexon.CategoryChannel
        )


class ThreadConverter(IDConverter[nexon.Thread]):
    """Coverts to a :class:`~nexon.Thread`.

    All lookups are via the local guild.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by mention.
    3. Lookup by name.

    .. versionadded: 2.0
    """

    async def convert(self, ctx: Context, argument: str) -> nexon.Thread:
        return GuildChannelConverter._resolve_thread(ctx, argument, "threads", nexon.Thread)


class ColourConverter(Converter[nexon.Colour]):
    """Converts to a :class:`~nexon.Colour`.

    .. versionchanged:: 1.5
        Add an alias named ColorConverter

    The following formats are accepted:

    - ``0x<hex>``
    - ``#<hex>``
    - ``0x#<hex>``
    - ``rgb(<number>, <number>, <number>)``
    - Any of the ``classmethod`` in :class:`~nexon.Colour`

        - The ``_`` in the name can be optionally replaced with spaces.

    Like CSS, ``<number>`` can be either 0-255 or 0-100% and ``<hex>`` can be
    either a 6 digit hex number or a 3 digit hex shortcut (e.g. #fff).

    .. versionchanged:: 1.5
         Raise :exc:`.BadColourArgument` instead of generic :exc:`.BadArgument`

    .. versionchanged:: 1.7
        Added support for ``rgb`` function and 3-digit hex shortcuts
    """

    RGB_REGEX = re.compile(
        r"rgb\s*\((?P<r>[0-9]{1,3}%?)\s*,\s*(?P<g>[0-9]{1,3}%?)\s*,\s*(?P<b>[0-9]{1,3}%?)\s*\)"
    )

    def parse_hex_number(self, argument):
        arg = "".join(i * 2 for i in argument) if len(argument) == 3 else argument
        try:
            value = int(arg, base=16)
            if not (0 <= value <= 0xFFFFFF):
                raise BadColourArgument(argument)
        except ValueError as e:
            raise BadColourArgument(argument) from e
        else:
            return nexon.Color(value=value)

    def parse_rgb_number(self, argument, number: str):
        if number[-1] == "%":
            value = int(number[:-1])
            if not (0 <= value <= 100):
                raise BadColourArgument(argument)
            return round(255 * (value / 100))

        value = int(number)
        if not (0 <= value <= 255):
            raise BadColourArgument(argument)
        return value

    def parse_rgb(self, argument, *, regex=RGB_REGEX):
        match = regex.match(argument)
        if match is None:
            raise BadColourArgument(argument)

        red = self.parse_rgb_number(argument, match.group("r"))
        green = self.parse_rgb_number(argument, match.group("g"))
        blue = self.parse_rgb_number(argument, match.group("b"))
        return nexon.Color.from_rgb(red, green, blue)

    async def convert(self, ctx: Context, argument: str) -> nexon.Colour:
        if argument[0] == "#":
            return self.parse_hex_number(argument[1:])

        if argument[0:2] == "0x":
            rest = argument[2:]
            # Legacy backwards compatible syntax
            if rest.startswith("#"):
                return self.parse_hex_number(rest[1:])
            return self.parse_hex_number(rest)

        arg = argument.lower()
        if arg[0:3] == "rgb":
            return self.parse_rgb(arg)

        arg = arg.replace(" ", "_")
        method = getattr(nexon.Colour, arg, None)
        if arg.startswith("from_") or method is None or not inspect.ismethod(method):
            raise BadColourArgument(arg)
        return method()


ColorConverter = ColourConverter


class RoleConverter(IDConverter[nexon.Role]):
    """Converts to a :class:`~nexon.Role`.

    All lookups are via the local guild. If in a DM context, the converter raises
    :exc:`.NoPrivateMessage` exception.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by mention.
    3. Lookup by name

    .. versionchanged:: 1.5
         Raise :exc:`.RoleNotFound` instead of generic :exc:`.BadArgument`
    """

    async def convert(self, ctx: Context, argument: str) -> nexon.Role:
        guild = ctx.guild
        if not guild:
            raise NoPrivateMessage

        match = self._get_id_match(argument) or re.match(r"<@&([0-9]{15,20})>$", argument)
        if match:
            result = guild.get_role(int(match.group(1)))
        else:
            result = nexon.utils.get(guild._roles.values(), name=argument)

        if result is None:
            raise RoleNotFound(argument)
        return result


class GameConverter(Converter[nexon.Game]):
    """Converts to :class:`~nexon.Game`."""

    async def convert(self, ctx: Context, argument: str) -> nexon.Game:
        return nexon.Game(name=argument)


class InviteConverter(Converter[nexon.Invite]):
    """Converts to a :class:`~nexon.Invite`.

    This is done via an HTTP request using :meth:`.Bot.fetch_invite`.

    .. versionchanged:: 1.5
         Raise :exc:`.BadInviteArgument` instead of generic :exc:`.BadArgument`
    """

    async def convert(self, ctx: Context, argument: str) -> nexon.Invite:
        try:
            return await ctx.bot.fetch_invite(argument)
        except Exception as exc:
            raise BadInviteArgument(argument) from exc


class GuildConverter(IDConverter[nexon.Guild]):
    """Converts to a :class:`~nexon.Guild`.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by name. (There is no disambiguation for Guilds with multiple matching names).

    .. versionadded:: 1.7
    """

    async def convert(self, ctx: Context, argument: str) -> nexon.Guild:
        match = self._get_id_match(argument)
        result = None

        if match is not None:
            guild_id = int(match.group(1))
            result = ctx.bot.get_guild(guild_id)

        if result is None:
            result = nexon.utils.get(ctx.bot.guilds, name=argument)

            if result is None:
                raise GuildNotFound(argument)
        return result


class EmojiConverter(IDConverter[nexon.Emoji]):
    """Converts to a :class:`~nexon.Emoji`.

    All lookups are done for the local guild first, if available. If that lookup
    fails, then it checks the client's global cache.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by extracting ID from the emoji.
    3. Lookup by name

    .. versionchanged:: 1.5
         Raise :exc:`.EmojiNotFound` instead of generic :exc:`.BadArgument`
    """

    async def convert(self, ctx: Context, argument: str) -> nexon.Emoji:
        match = self._get_id_match(argument) or re.match(
            r"<a?:[a-zA-Z0-9\_]{1,32}:([0-9]{15,20})>$", argument
        )
        result = None
        bot = ctx.bot
        guild = ctx.guild

        if match is None:
            # Try to get the emoji by name. Try local guild first.
            if guild:
                result = nexon.utils.get(guild.emojis, name=argument)

            if result is None:
                result = nexon.utils.get(bot.emojis, name=argument)
        else:
            emoji_id = int(match.group(1))

            # Try to look up emoji by id.
            result = bot.get_emoji(emoji_id)

        if result is None:
            raise EmojiNotFound(argument)

        return result


class PartialEmojiConverter(Converter[nexon.PartialEmoji]):
    """Converts to a :class:`~nexon.PartialEmoji`.

    This is done by extracting the animated flag, name and ID from the emoji.

    If the emoji is a unicode emoji, then the name is the unicode character.

    .. versionchanged:: 1.5
         Raise :exc:`.PartialEmojiConversionFailure` instead of generic :exc:`.BadArgument`

    .. versionchanged:: 2.1
        Add support for converting unicode emojis
    """

    async def convert(self, ctx: Context, argument: str) -> nexon.PartialEmoji:
        match = re.match(r"<(a?):([a-zA-Z0-9\_]{1,32}):([0-9]{15,20})>$", argument)

        if match:
            emoji_animated = bool(match.group(1))
            emoji_name = match.group(2)
            emoji_id = int(match.group(3))

            return nexon.PartialEmoji.with_state(
                ctx.bot._connection, animated=emoji_animated, name=emoji_name, id=emoji_id
            )

        # If the emoji is a unicode emoji, then the name is the unicode character.
        if re.match(r"^[\u0023-\u0039]?[\u00ae\u00a9\U00002000-\U0010ffff]+$", argument):
            return nexon.PartialEmoji.with_state(ctx.bot._connection, name=argument)

        raise PartialEmojiConversionFailure(argument)


class GuildStickerConverter(IDConverter[nexon.GuildSticker]):
    """Converts to a :class:`~nexon.GuildSticker`.

    All lookups are done for the local guild first, if available. If that lookup
    fails, then it checks the client's global cache.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    3. Lookup by name

    .. versionadded:: 2.0
    """

    async def convert(self, ctx: Context, argument: str) -> nexon.GuildSticker:
        match = self._get_id_match(argument)
        result = None
        bot = ctx.bot
        guild = ctx.guild

        if match is None:
            # Try to get the sticker by name. Try local guild first.
            if guild:
                result = nexon.utils.get(guild.stickers, name=argument)

            if result is None:
                result = nexon.utils.get(bot.stickers, name=argument)
        else:
            sticker_id = int(match.group(1))

            # Try to look up sticker by id.
            result = bot.get_sticker(sticker_id)

        if result is None:
            raise GuildStickerNotFound(argument)

        return result


_EVENT_INVITE_RE = re.compile(
    r"(?:https?\:\/\/)?discord(?:\.gg|(?:app)?\.com\/invite)\/(.+)?event=(\d+)"
)

_EVENT_API_RE = re.compile(
    r"(?:https?\:\/\/)?(?:(ptb|canary|www)\.)?discord(?:(?:app)?\.com\/events)\/(\d+)\/(\d+)"
)


class ScheduledEventConverter(IDConverter[nexon.ScheduledEvent]):
    """Converts to a :class:`~nexon.ScheduledEvent`.

    All lookups are done for the local guild first, if available. If that lookup
    fails, then it checks the client's global cache.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    3. Lookup by name
    3. Lookup by url (invite?event=id and /guildid/eventid)

    .. versionadded:: 2.0
    """

    async def convert(self, ctx: Context, argument: str) -> nexon.ScheduledEvent:
        match = self._get_id_match(argument)
        result = None
        bot = ctx.bot
        guild = ctx.guild

        if match is None:
            # Try to get the scheduled event by name. Try local guild first.
            if guild:
                result = nexon.utils.get(guild.scheduled_events, name=argument)

            if result is None:
                result = nexon.utils.get(bot.scheduled_events, name=argument)
        else:
            scheduled_event_id = int(match.group(1))

            # Try to look up scheduled event by id.
            result = bot.get_scheduled_event(scheduled_event_id)

        if result is None:
            match = _EVENT_INVITE_RE.match(argument)

            if match is not None:
                event_id = int(match.group(2))
                result = bot.get_scheduled_event(event_id)
            else:
                match = _EVENT_API_RE.match(argument)

                if not match:
                    raise ScheduledEventNotFound(argument)

                guild_id = int(match.group(2))
                guild = bot.get_guild(guild_id)
                if guild is not None:
                    result = guild.get_scheduled_event(int(match.group(3)))
                else:
                    raise ScheduledEventNotFound(argument)

                if result is None:
                    raise ScheduledEventNotFound(argument)

        return result


class clean_content(Converter[str]):
    """Converts the argument to mention scrubbed version of
    said content.

    This behaves similarly to :attr:`~nexon.Message.clean_content`.

    Attributes
    ----------
    fix_channel_mentions: :class:`bool`
        Whether to clean channel mentions.
    use_nicknames: :class:`bool`
        Whether to use nicknames when transforming mentions.
    escape_markdown: :class:`bool`
        Whether to also escape special markdown characters.
    remove_markdown: :class:`bool`
        Whether to also remove special markdown characters. This option is not supported with ``escape_markdown``

        .. versionadded:: 1.7
    """

    def __init__(
        self,
        *,
        fix_channel_mentions: bool = False,
        use_nicknames: bool = True,
        escape_markdown: bool = False,
        remove_markdown: bool = False,
    ) -> None:
        self.fix_channel_mentions = fix_channel_mentions
        self.use_nicknames = use_nicknames
        self.escape_markdown = escape_markdown
        self.remove_markdown = remove_markdown

    async def convert(self, ctx: Context, argument: str) -> str:
        msg = ctx.message

        if ctx.guild:

            def resolve_member(id: int) -> str:
                m = _utils_get(msg.mentions, id=id) or ctx.guild.get_member(id)  # type: ignore
                # [in a guild if we are here]
                return (
                    f"@{m.display_name if self.use_nicknames else m.name}" if m else "@deleted-user"
                )

            def resolve_role(id: int) -> str:  # pyright: ignore[reportRedeclaration]
                r = _utils_get(msg.role_mentions, id=id) or ctx.guild.get_role(id)  # type: ignore
                return f"@{r.name}" if r else "@deleted-role"

        else:

            def resolve_member(id: int) -> str:
                m = _utils_get(msg.mentions, id=id) or ctx.bot.get_user(id)
                return f"@{m.name}" if m else "@deleted-user"

            def resolve_role(_id: int) -> str:
                return "@deleted-role"

        if self.fix_channel_mentions and ctx.guild:

            def resolve_channel(id: int) -> str:
                c = ctx.guild.get_channel(id)  # type: ignore
                return f"#{c.name}" if c else "#deleted-channel"

        else:

            def resolve_channel(id: int) -> str:
                return f"<#{id}>"

        transforms = {
            "@": resolve_member,
            "@!": resolve_member,
            "#": resolve_channel,
            "@&": resolve_role,
        }

        def repl(match: re.Match) -> str:
            type = match[1]
            id = int(match[2])
            return transforms[type](id)

        result = re.sub(r"<(@[!&]?|#)([0-9]{15,20})>", repl, argument)
        if self.escape_markdown:
            result = nexon.utils.escape_markdown(result)
        elif self.remove_markdown:
            result = nexon.utils.remove_markdown(result)

        # Completely ensure no mentions escape:
        return nexon.utils.escape_mentions(result)


class Greedy(List[T]):
    r"""A special converter that greedily consumes arguments until it can't.
    As a consequence of this behaviour, most input errors are silently discarded,
    since it is used as an indicator of when to stop parsing.

    When a parser error is met the greedy converter stops converting, undoes the
    internal string parsing routine, and continues parsing regularly.

    For example, in the following code:

    .. code-block:: python3

        @commands.command()
        async def test(ctx, numbers: Greedy[int], reason: str):
            await ctx.send("numbers: {}, reason: {}".format(numbers, reason))

    An invocation of ``[p]test 1 2 3 4 5 6 hello`` would pass ``numbers`` with
    ``[1, 2, 3, 4, 5, 6]`` and ``reason`` with ``hello``\.

    For more information, check :ref:`ext_commands_special_converters`.
    """

    __slots__ = ("converter",)

    def __init__(self, *, converter: T) -> None:
        self.converter = converter

    def __repr__(self) -> str:
        converter = getattr(self.converter, "__name__", repr(self.converter))
        return f"Greedy[{converter}]"

    def __class_getitem__(cls, params: Union[Tuple[T], T]) -> Greedy[T]:
        if not isinstance(params, tuple):
            params = (params,)
        if len(params) != 1:
            raise TypeError("Greedy[...] only takes a single argument")
        converter = params[0]

        origin = getattr(converter, "__origin__", None)
        args = getattr(converter, "__args__", ())

        if not (callable(converter) or isinstance(converter, Converter) or origin is not None):
            raise TypeError("Greedy[...] expects a type or a Converter instance.")

        if converter in (str, type(None)) or origin is Greedy:
            raise TypeError(f"Greedy[{type(converter).__name__}] is invalid.")



        if origin is Union and type(None) in args:
            raise TypeError(f"Greedy[{converter!r}] is invalid.")

        # The type variable T is completely lost by this point.
        return cls(converter=converter)  # pyright: ignore


def _convert_to_bool(argument: str) -> bool:
    lowered = argument.lower()
    if lowered in ("yes", "y", "true", "t", "1", "enable", "on"):
        return True
    if lowered in ("no", "n", "false", "f", "0", "disable", "off"):
        return False
    raise BadBoolArgument(lowered)


def get_converter(param: inspect.Parameter) -> Any:
    converter = param.annotation
    if converter is param.empty:
        if param.default is not param.empty:
            converter = str if param.default is None else type(param.default)
        else:
            converter = str
    return converter


def is_generic_type(tp: Any) -> bool:
    return isinstance(tp, type) and issubclass(tp, Generic) or isinstance(tp, GenericAlias)


CONVERTER_MAPPING: Dict[Type[Any], Any] = {
    nexon.Object: ObjectConverter,
    nexon.Member: MemberConverter,
    nexon.User: UserConverter,
    nexon.Message: MessageConverter,
    nexon.PartialMessage: PartialMessageConverter,
    nexon.TextChannel: TextChannelConverter,
    nexon.Invite: InviteConverter,
    nexon.Guild: GuildConverter,
    nexon.Role: RoleConverter,
    nexon.Game: GameConverter,
    nexon.Colour: ColourConverter,
    nexon.VoiceChannel: VoiceChannelConverter,
    nexon.StageChannel: StageChannelConverter,
    nexon.Emoji: EmojiConverter,
    nexon.PartialEmoji: PartialEmojiConverter,
    nexon.CategoryChannel: CategoryChannelConverter,
    nexon.Thread: ThreadConverter,
    nexon.abc.GuildChannel: GuildChannelConverter,
    nexon.GuildSticker: GuildStickerConverter,
    nexon.ScheduledEvent: ScheduledEventConverter,
}


async def _actual_conversion(ctx: Context, converter: Any, argument: str, param: inspect.Parameter):
    if converter is bool:
        return _convert_to_bool(argument)

    try:
        module = converter.__module__
    except AttributeError:
        pass
    else:
        if module is not None and (
            module.startswith("nexon.") and not module.endswith("converter")
        ):
            converter = CONVERTER_MAPPING.get(converter, converter)

    try:
        if inspect.isclass(converter) and issubclass(converter, Converter):
            if inspect.ismethod(converter.convert):
                return await converter.convert(ctx, argument)
            return await converter().convert(ctx, argument)

        if isinstance(converter, Converter):
            return await converter.convert(ctx, argument)
    except CommandError:
        raise
    except Exception as exc:
        raise ConversionError(converter, exc) from exc  # type: ignore

    try:
        # pyright believes this to be Any | type[object], which is fine anyway
        # but claims 0 positional arguments
        return converter(argument)  # pyright: ignore
    except CommandError:
        raise
    except Exception as exc:
        try:
            name = converter.__name__
        except AttributeError:
            name = converter.__class__.__name__

        raise BadArgument(f'Converting to "{name}" failed for parameter "{param.name}".') from exc


async def run_converters(ctx: Context, converter, argument: str, param: inspect.Parameter):
    """|coro|

    Runs converters for a given converter, argument, and parameter.

    This function does the same work that the library does under the hood.

    .. versionadded:: 2.0

    Parameters
    ----------
    ctx: :class:`Context`
        The invocation context to run the converters under.
    converter: Any
        The converter to run, this corresponds to the annotation in the function.
    argument: :class:`str`
        The argument to convert to.
    param: :class:`inspect.Parameter`
        The parameter being converted. This is mainly for error reporting.

    Raises
    ------
    CommandError
        The converter failed to convert.

    Returns
    -------
    Any
        The resulting conversion.
    """
    origin = getattr(converter, "__origin__", None)

    if origin is Union:
        errors = []
        _NoneType = type(None)
        union_args = converter.__args__
        for conv in union_args:
            # if we got to this part in the code, then the previous conversions have failed
            # so we should just undo the view, return the default, and allow parsing to continue
            # with the other parameters
            if conv is _NoneType and param.kind != param.VAR_POSITIONAL:
                ctx.view.undo()
                return None if param.default is param.empty else param.default

            try:
                value = await run_converters(ctx, conv, argument, param)
            except CommandError as exc:
                errors.append(exc)
            else:
                return value

        # if we're here, then we failed all the converters
        raise BadUnionArgument(param, union_args, errors)

    if origin is Literal:
        errors = []
        conversions = {}
        literal_args = converter.__args__
        for literal in literal_args:
            literal_type = type(literal)
            try:
                value = conversions[literal_type]
            except KeyError:
                try:
                    value = await _actual_conversion(ctx, literal_type, argument, param)
                except CommandError as exc:
                    errors.append(exc)
                    conversions[literal_type] = object()
                    continue
                else:
                    conversions[literal_type] = value

            if value == literal:
                return value

        # if we're here, then we failed to match all the literals
        raise BadLiteralArgument(param, literal_args, errors)

    # This must be the last if-clause in the chain of origin checking
    # Nearly every type is a generic type within the typing library
    # So care must be taken to make sure a more specialised origin handle
    # isn't overwritten by the widest if clause
    if origin is not None and is_generic_type(converter):
        converter = origin

    return await _actual_conversion(ctx, converter, argument, param)
