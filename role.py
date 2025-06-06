# SPDX-License-Identifier: MIT

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from .asset import Asset
from .colour import Colour
from .errors import InvalidArgument
from .flags import RoleFlags
from .mixins import Hashable
from .permissions import Permissions
from .utils import MISSING, get_as_snowflake, obj_to_base64_data, snowflake_time

__all__ = (
    "RoleTags",
    "Role",
)

if TYPE_CHECKING:
    import datetime

    from typing_extensions import Self

    from .file import File
    from .guild import Guild
    from .member import Member
    from .message import Attachment
    from .state import ConnectionState
    from .types.guild import RolePositionUpdate
    from .types.role import Role as RolePayload, RoleTags as RoleTagPayload


class RoleTags:
    """Represents tags on a role.

    A role tag is a piece of extra information attached to a managed role
    that gives it context for the reason the role is managed.

    While this can be accessed, a useful interface is also provided in the
    :class:`Role` and :class:`Guild` classes as well.

    .. versionadded:: 1.6

    Attributes
    ----------
    bot_id: Optional[:class:`int`]
        The bot's user ID that manages this role.
    integration_id: Optional[:class:`int`]
        The integration ID that manages the role.
    subscription_listing_id: Optional[:class:`int`]
        The ID of the subscription listing that manages the role.

        .. versionadded:: 2.4
    
    premium_subscriber: :class:`bool`
        Whether the role is the premium subscriber, AKA "boost", role for the guild.
        
        versionadded:: 3.2
    available_for_purchase: :class:`bool`
        Whether the role is available for purchase.
        
        .. versionadded:: 3.2
    guild_connections: :class:`bool`
        Whether the role is a guild's linked role.
        
        .. versionadded:: 3.2
    """

    __slots__ = (
        "bot_id",
        "integration_id",
        "subscription_listing_id",
        "premium_subscriber",
        "available_for_purchase",
        "guild_connections",
    )

    def __init__(self, data: RoleTagPayload) -> None:
        self.bot_id: Optional[int] = get_as_snowflake(data, "bot_id")
        self.integration_id: Optional[int] = get_as_snowflake(data, "integration_id")
        # NOTE: The API returns "null" for this if it's valid, which corresponds to None.
        # This is different from other fields where "null" means "not there".
        # So in this case, a value of None is the same as True.
        # Which means we would need a different sentinel.
        self.subscription_listing_id: Optional[int] = get_as_snowflake(
            data, "subscription_listing_id"
        )
        
        self.guild_connections: bool = "guild_connections" in data
        self.premium_subscriber: bool = "premium_subscriber" in data
        self.available_for_purchase: bool = "available_for_purchase" in data

    def is_bot_managed(self) -> bool:
        """:class:`bool`: Whether the role is associated with a bot."""
        return self.bot_id is not None

    def is_premium_subscriber(self) -> bool:
        """:class:`bool`: Whether the role is the premium subscriber, AKA "boost", role for the guild."""
        return self.premium_subscriber

    def is_integration(self) -> bool:
        """:class:`bool`: Whether the role is managed by an integration."""
        return self.integration_id is not None

    def is_available_for_purchase(self) -> bool:
        """:class:`bool`: Whether the role is available for purchase.

        .. versionadded:: 2.4
        """
        return self.available_for_purchase

    def has_guild_connections(self) -> bool:
        """:class:`bool`: Whether the role is a guild's linked role.

        .. versionadded:: 2.4
        """
        return self.guild_connections

    def __repr__(self) -> str:
        return (
            f"<RoleTags bot_id={self.bot_id} integration_id={self.integration_id} "
            f"premium_subscriber={self.is_premium_subscriber()}>"
            f"subscription_listing_id={self.subscription_listing_id}>"
            f"available_for_purchase={self.is_available_for_purchase()}>"
            f"guild_connections={self.has_guild_connections()}>"
        )


class Role(Hashable):
    """Represents a Discord role in a :class:`Guild`.

    .. container:: operations

        .. describe:: x == y

            Checks if two roles are equal.

        .. describe:: x != y

            Checks if two roles are not equal.

        .. describe:: x > y

            Checks if a role is higher than another in the hierarchy.

        .. describe:: x < y

            Checks if a role is lower than another in the hierarchy.

        .. describe:: x >= y

            Checks if a role is higher or equal to another in the hierarchy.

        .. describe:: x <= y

            Checks if a role is lower or equal to another in the hierarchy.

        .. describe:: hash(x)

            Return the role's hash.

        .. describe:: str(x)

            Returns the role's name.

    Attributes
    ----------
    id: :class:`int`
        The ID for the role.
    name: :class:`str`
        The name of the role.
    guild: :class:`Guild`
        The guild the role belongs to.
    hoist: :class:`bool`
         Indicates if the role will be displayed separately from other members.
    position: :class:`int`
        The position of the role. This number is usually positive. The bottom
        role has a position of 0.

        .. warning::

            Multiple roles can have the same position number. As a consequence
            of this, comparing via role position is prone to subtle bugs if
            checking for role hierarchy. The recommended and correct way to
            compare for roles in the hierarchy is using the comparison
            operators on the role objects themselves.

    managed: :class:`bool`
        Indicates if the role is managed by the guild through some form of
        integrations such as Twitch.
    mentionable: :class:`bool`
        Indicates if the role can be mentioned by users.
    tags: Optional[:class:`RoleTags`]
        The role tags associated with this role.
    """

    __slots__ = (
        "id",
        "name",
        "_permissions",
        "_colour",
        "position",
        "managed",
        "mentionable",
        "hoist",
        "guild",
        "tags",
        "_icon",
        "_state",
        "_flags",
    )

    def __init__(self, *, guild: Guild, state: ConnectionState, data: RolePayload) -> None:
        self.guild: Guild = guild
        self._state: ConnectionState = state
        self.id: int = int(data["id"])
        self._update(data)

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"<Role id={self.id} name={self.name!r}>"

    def __lt__(self, other: Self) -> bool:
        if not isinstance(other, Role) or not isinstance(self, Role):
            return NotImplemented

        if self.guild != other.guild:
            raise RuntimeError("Cannot compare roles from two different guilds.")

        # the @everyone role is always the lowest role in hierarchy
        guild_id = self.guild.id
        if self.id == guild_id:
            # everyone_role < everyone_role -> False
            return other.id != guild_id

        if self.position < other.position:
            return True

        if self.position == other.position:
            return int(self.id) > int(other.id)

        return False

    def __le__(self, other: Self) -> bool:
        r = Role.__lt__(other, self)
        if r is NotImplemented:
            return NotImplemented
        return not r

    def __gt__(self, other: Self) -> bool:
        return Role.__lt__(other, self)

    def __ge__(self, other: Self) -> bool:
        r = Role.__lt__(self, other)
        if r is NotImplemented:
            return NotImplemented
        return not r

    def _update(self, data: RolePayload) -> None:
        self.name: str = data["name"]
        self._permissions: int = int(data.get("permissions", 0))
        self.position: int = data.get("position", 0)
        self._colour: int = data.get("color", 0)
        self.hoist: bool = data.get("hoist", False)
        self.managed: bool = data.get("managed", False)
        self.mentionable: bool = data.get("mentionable", False)
        self._icon: Optional[str] = data.get("icon", None)
        if self._icon is None:
            self._icon: Optional[str] = data.get("unicode_emoji", None)
        self.tags: Optional[RoleTags]
        self.tags = RoleTags(data["tags"]) if "tags" in data else None

        self._flags: int = data.get("flags", 0)

    def is_default(self) -> bool:
        """:class:`bool`: Checks if the role is the default role."""
        return self.guild.id == self.id

    def is_bot_managed(self) -> bool:
        """:class:`bool`: Whether the role is associated with a bot.

        .. versionadded:: 1.6
        """
        return self.tags is not None and self.tags.is_bot_managed()

    def is_premium_subscriber(self) -> bool:
        """:class:`bool`: Whether the role is the premium subscriber, AKA "boost", role for the guild.

        .. versionadded:: 1.6
        """
        return self.tags is not None and self.tags.is_premium_subscriber()

    def is_integration(self) -> bool:
        """:class:`bool`: Whether the role is managed by an integration.

        .. versionadded:: 1.6
        """
        return self.tags is not None and self.tags.is_integration()

    def is_assignable(self) -> bool:
        """:class:`bool`: Whether the role is able to be assigned or removed by the bot.

        .. versionadded:: 2.0
        """
        me = self.guild.me
        return (
            not self.is_default()
            and not self.managed
            and (me.top_role > self or me.id == self.guild.owner_id)
        )

    def is_in_prompt(self) -> bool:
        """:class:`bool`: Whether the role can be selected in an onboarding prompt.

        .. versionadded:: 2.6
        """
        return self.flags.in_prompt

    @property
    def permissions(self) -> Permissions:
        """:class:`Permissions`: Returns the role's permissions."""
        return Permissions(self._permissions)

    @property
    def colour(self) -> Colour:
        """:class:`Colour`: Returns the role colour. An alias exists under ``color``."""
        return Colour(self._colour)

    @property
    def color(self) -> Colour:
        """:class:`Colour`: Returns the role color. An alias exists under ``colour``."""
        return self.colour

    @property
    def created_at(self) -> datetime.datetime:
        """:class:`datetime.datetime`: Returns the role's creation time in UTC."""
        return snowflake_time(self.id)

    @property
    def mention(self) -> str:
        """:class:`str`: Returns a string that allows you to mention a role."""
        if self.id != self.guild.id:
            return f"<@&{self.id}>"
        return "@everyone"

    @property
    def members(self) -> List[Member]:
        """List[:class:`Member`]: Returns all the members with this role."""
        all_members = self.guild.members
        if self.is_default():
            return all_members

        role_id = self.id
        return [member for member in all_members if member._roles.has(role_id)]

    @property
    def icon(self) -> Optional[Union[Asset, str]]:
        """Optional[Union[:class:`Asset`, :class:`str`]]: Returns the role's icon asset or its
        unicode emoji, if available."""
        if self._icon is None:
            return None
        if len(self._icon) == 1:
            return self._icon
        return Asset._from_icon(self._state, self.id, self._icon, "role")

    async def _move(self, position: int, reason: Optional[str]) -> None:
        if position <= 0:
            raise InvalidArgument("Cannot move role to position 0 or below")

        if self.is_default():
            raise InvalidArgument("Cannot move default role")

        if self.position == position:
            return  # Save discord the extra request.

        http = self._state.http

        change_range = range(min(self.position, position), max(self.position, position) + 1)
        roles = [
            r.id for r in self.guild.roles[1:] if r.position in change_range and r.id != self.id
        ]

        if self.position > position:
            roles.insert(0, self.id)
        else:
            roles.append(self.id)

        payload: List[RolePositionUpdate] = [
            {"id": z[0], "position": z[1]} for z in zip(roles, change_range, strict=False)
        ]
        await http.move_role_position(self.guild.id, payload, reason=reason)

    async def edit(
        self,
        *,
        name: str = MISSING,
        permissions: Permissions = MISSING,
        colour: Union[Colour, int] = MISSING,
        color: Union[Colour, int] = MISSING,
        hoist: bool = MISSING,
        mentionable: bool = MISSING,
        position: int = MISSING,
        reason: Optional[str] = MISSING,
        icon: Optional[Union[str, bytes, Asset, Attachment, File]] = MISSING,
    ) -> Optional[Role]:
        """|coro|

        Edits the role.

        You must have the :attr:`~Permissions.manage_roles` permission to
        use this.

        All fields are optional.

        .. versionchanged:: 1.4
            Can now pass ``int`` to ``colour`` keyword-only parameter.

        .. versionchanged:: 2.0
            Edits are no longer in-place, the newly edited role is returned instead.

        .. versionchanged:: 2.1
            The ``icon`` parameter now accepts :class:`Attachment`, and :class:`Asset`.

        Parameters
        ----------
        name: :class:`str`
            The new role name to change to.
        permissions: :class:`Permissions`
            The new permissions to change to.
        colour: Union[:class:`Colour`, :class:`int`]
            The new colour to change to. (aliased to color as well)
        hoist: :class:`bool`
            Indicates if the role should be shown separately in the member list.
        mentionable: :class:`bool`
            Indicates if the role should be mentionable by others.
        position: :class:`int`
            The new role's position. This must be below your top role's
            position or it will fail.
        icon: Optional[Union[:class:`str`, :class:`bytes`, :class:`File`, :class:`Asset`, :class:`Attachment`]]
            The role's icon image
        reason: Optional[:class:`str`]
            The reason for editing this role. Shows up on the audit log.

        Raises
        ------
        Forbidden
            You do not have permissions to change the role.
        HTTPException
            Editing the role failed.
        InvalidArgument
            An invalid position was given or the default
            role was asked to be moved.

        Returns
        -------
        :class:`Role`
            The newly edited role.
        """
        if position is not MISSING:
            await self._move(position, reason=reason)

        payload: Dict[str, Any] = {}
        if color is not MISSING:
            colour = color

        if colour is not MISSING:
            if isinstance(colour, int):
                payload["color"] = colour
            else:
                payload["color"] = colour.value

        if name is not MISSING:
            payload["name"] = name

        if permissions is not MISSING:
            payload["permissions"] = permissions.value

        if hoist is not MISSING:
            payload["hoist"] = hoist

        if mentionable is not MISSING:
            payload["mentionable"] = mentionable

        if icon is not MISSING:
            if isinstance(icon, str):
                payload["unicode_emoji"] = icon
            else:
                payload["icon"] = await obj_to_base64_data(icon)

        data = await self._state.http.edit_role(self.guild.id, self.id, reason=reason, **payload)
        return Role(guild=self.guild, data=data, state=self._state)

    async def delete(self, *, reason: Optional[str] = None) -> None:
        """|coro|

        Deletes the role.

        You must have the :attr:`~Permissions.manage_roles` permission to
        use this.

        Parameters
        ----------
        reason: Optional[:class:`str`]
            The reason for deleting this role. Shows up on the audit log.

        Raises
        ------
        Forbidden
            You do not have permissions to delete the role.
        HTTPException
            Deleting the role failed.
        """

        await self._state.http.delete_role(self.guild.id, self.id, reason=reason)

    @property
    def flags(self) -> RoleFlags:
        """:class:`RoleFlags`: The avaliable flags the role has.

        .. versionadded:: 2.6
        """
        return RoleFlags._from_value(self._flags)
