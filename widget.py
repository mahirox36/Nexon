# SPDX-License-Identifier: MIT

from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Optional, Union

from .activity import BaseActivity, Spotify, create_activity
from .enums import Status, try_enum
from .invite import Invite
from .user import BaseUser
from .utils import get_as_snowflake, resolve_invite, snowflake_time

if TYPE_CHECKING:
    import datetime

    from .state import ConnectionState
    from .types.widget import Widget as WidgetPayload, WidgetMember as WidgetMemberPayload

__all__ = (
    "WidgetChannel",
    "WidgetMember",
    "Widget",
)


class WidgetChannel:
    """Represents a "partial" widget channel.

    .. container:: operations

        .. describe:: x == y

            Checks if two partial channels are the same.

        .. describe:: x != y

            Checks if two partial channels are not the same.

        .. describe:: hash(x)

            Return the partial channel's hash.

        .. describe:: str(x)

            Returns the partial channel's name.

    Attributes
    ----------
    id: :class:`int`
        The channel's ID.
    name: :class:`str`
        The channel's name.
    position: :class:`int`
        The channel's position
    """

    __slots__ = ("id", "name", "position")

    def __init__(self, id: int, name: str, position: int) -> None:
        self.id: int = id
        self.name: str = name
        self.position: int = position

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"<WidgetChannel id={self.id} name={self.name!r} position={self.position!r}>"

    @property
    def mention(self) -> str:
        """:class:`str`: The string that allows you to mention the channel."""
        return f"<#{self.id}>"

    @property
    def created_at(self) -> datetime.datetime:
        """:class:`datetime.datetime`: Returns the channel's creation time in UTC."""
        return snowflake_time(self.id)


class WidgetMember(BaseUser):
    """Represents a "partial" member of the widget's guild.

    .. container:: operations

        .. describe:: x == y

            Checks if two widget members are the same.

        .. describe:: x != y

            Checks if two widget members are not the same.

        .. describe:: hash(x)

            Return the widget member's hash.

        .. describe:: str(x)

            Returns the widget member's ``name#discriminator``.

    Attributes
    ----------
    id: :class:`int`
        The member's ID.
    name: :class:`str`
        The member's username.
    discriminator: :class:`str`
        The member's discriminator.
    bot: :class:`bool`
        Whether the member is a bot.
    status: :class:`Status`
        The member's status.
    nick: Optional[:class:`str`]
        The member's nickname.
    avatar: Optional[:class:`str`]
        The member's avatar hash.
    activity: Optional[Union[:class:`BaseActivity`, :class:`Spotify`]]
        The member's activity.
    deafened: Optional[:class:`bool`]
        Whether the member is currently deafened.
    muted: Optional[:class:`bool`]
        Whether the member is currently muted.
    suppress: Optional[:class:`bool`]
        Whether the member is currently being suppressed.
    connected_channel: Optional[:class:`WidgetChannel`]
        Which channel the member is connected to.
    """

    __slots__ = (
        "status",
        "nick",
        "avatar",
        "activity",
        "deafened",
        "suppress",
        "muted",
        "connected_channel",
    )

    if TYPE_CHECKING:
        activity: Optional[Union[BaseActivity, Spotify]]

    def __init__(
        self,
        *,
        state: ConnectionState,
        data: WidgetMemberPayload,
        connected_channel: Optional[WidgetChannel] = None,
    ) -> None:
        super().__init__(state=state, data=data)
        self.nick: Optional[str] = data.get("nick")
        self.status: Status = try_enum(Status, data.get("status"))
        self.deafened: Optional[bool] = data.get("deaf", False) or data.get("self_deaf", False)
        self.muted: Optional[bool] = data.get("mute", False) or data.get("self_mute", False)
        self.suppress: Optional[bool] = data.get("suppress", False)
        self.activity = create_activity(state, data["game"]) if "game" in data else None

        self.connected_channel: Optional[WidgetChannel] = connected_channel

    def __repr__(self) -> str:
        return (
            f"<WidgetMember name={self.name!r} discriminator={self.discriminator!r}"
            f" bot={self.bot} nick={self.nick!r}>"
        )

    @property
    def display_name(self) -> str:
        """:class:`str`: Returns the user's display name.

        This will return the name using the following hierarchy:

        1. Guild specific nickname
        2. Global Name (also known as 'Display Name' in the Discord UI)
        3. Unique username
        """
        return self.nick or self.global_name or self.name


class Widget:
    """Represents a :class:`Guild` widget.

    .. container:: operations

        .. describe:: x == y

            Checks if two widgets are the same.

        .. describe:: x != y

            Checks if two widgets are not the same.

        .. describe:: str(x)

            Returns the widget's JSON URL.

    Attributes
    ----------
    id: :class:`int`
        The guild's ID.
    name: :class:`str`
        The guild's name.
    channels: List[:class:`WidgetChannel`]
        The accessible voice channels in the guild.
    members: List[:class:`Member`]
        The online members in the server. Offline members
        do not appear in the widget.

        .. note::

            Due to a Discord limitation, if this data is available
            the users will be "anonymized" with linear IDs and discriminator
            information being incorrect. Likewise, the number of members
            retrieved is capped.

    """

    __slots__ = ("_state", "channels", "_invite", "id", "members", "name")

    def __init__(self, *, state: ConnectionState, data: WidgetPayload) -> None:
        self._state = state
        self._invite = data["instant_invite"]
        self.name: str = data["name"]
        self.id: int = int(data["id"])

        self.channels: List[WidgetChannel] = []
        for channel in data.get("channels", []):
            _id = int(channel["id"])
            self.channels.append(
                WidgetChannel(id=_id, name=channel["name"], position=channel["position"])
            )

        self.members: List[WidgetMember] = []
        channels = {channel.id: channel for channel in self.channels}
        for member in data.get("members", []):
            connected_channel = get_as_snowflake(member, "channel_id")
            if connected_channel in channels:
                connected_channel = channels[connected_channel]
            elif connected_channel:
                connected_channel = WidgetChannel(id=connected_channel, name="", position=0)

            self.members.append(WidgetMember(state=self._state, data=member, connected_channel=connected_channel))  # type: ignore

    def __str__(self) -> str:
        return self.json_url

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Widget):
            return self.id == other.id
        return False

    def __repr__(self) -> str:
        return f"<Widget id={self.id} name={self.name!r} invite_url={self.invite_url!r}>"

    @property
    def created_at(self) -> datetime.datetime:
        """:class:`datetime.datetime`: Returns the member's creation time in UTC."""
        return snowflake_time(self.id)

    @property
    def json_url(self) -> str:
        """:class:`str`: The JSON URL of the widget."""
        return f"https://discord.com/api/guilds/{self.id}/widget.json"

    @property
    def invite_url(self) -> str:
        """Optional[:class:`str`]: The invite URL for the guild, if available."""
        return self._invite

    async def fetch_invite(self, *, with_counts: bool = True) -> Invite:
        """|coro|

        Retrieves an :class:`Invite` from the widget's invite URL.
        This is the same as :meth:`Client.fetch_invite`; the invite
        code is abstracted away.

        Parameters
        ----------
        with_counts: :class:`bool`
            Whether to include count information in the invite. This fills the
            :attr:`Invite.approximate_member_count` and :attr:`Invite.approximate_presence_count`
            fields.

        Returns
        -------
        :class:`Invite`
            The invite from the widget's invite URL.
        """
        invite_id = resolve_invite(self._invite)
        data = await self._state.http.get_invite(invite_id, with_counts=with_counts)
        return Invite.from_incomplete(state=self._state, data=data)
