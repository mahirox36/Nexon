# SPDX-License-Identifier: MIT

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
from contextvars import ContextVar
from types import TracebackType
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
    Literal,
    NamedTuple,
    Optional,
    Tuple,
    Type,
    Union,
    overload,
)
from urllib.parse import quote as urlquote
from weakref import WeakValueDictionary

import aiohttp

from .. import utils
from ..asset import Asset
from ..channel import PartialMessageable
from ..enums import WebhookType, try_enum
from ..errors import DiscordServerError, Forbidden, HTTPException, InvalidArgument, NotFound
from ..flags import MessageFlags
from ..http import _USER_AGENT, Route
from ..message import Attachment, Message
from ..mixins import Hashable
from ..user import BaseUser, User

__all__ = (
    "Webhook",
    "WebhookMessage",
    "PartialWebhookChannel",
    "PartialWebhookGuild",
)

_log = logging.getLogger(__name__)

if TYPE_CHECKING:
    import datetime

    from ..abc import Snowflake
    from ..channel import TextChannel
    from ..embeds import Embed
    from ..file import File
    from ..guild import Guild
    from ..http import Response
    from ..mentions import AllowedMentions
    from ..state import ConnectionState
    from ..types.message import Message as MessagePayload
    from ..types.snowflake import Snowflake as SnowflakeAlias
    from ..types.webhook import Webhook as WebhookPayload
    from ..ui.view import View

MISSING = utils.MISSING


class AsyncDeferredLock:
    def __init__(self, lock: asyncio.Lock) -> None:
        self.lock = lock
        self.delta: Optional[float] = None

    async def __aenter__(self):
        await self.lock.acquire()
        return self

    def delay_by(self, delta: float) -> None:
        self.delta = delta

    async def __aexit__(
        self,
        type: Optional[Type[BaseException]],
        value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        if self.delta:
            await asyncio.sleep(self.delta)
        self.lock.release()


class AsyncWebhookAdapter:
    def __init__(self) -> None:
        self._locks: WeakValueDictionary[
            Tuple[Optional[SnowflakeAlias], Optional[str]],
            asyncio.Lock,
        ] = WeakValueDictionary()

    async def request(
        self,
        route: Route,
        session: aiohttp.ClientSession,
        *,
        payload: Optional[Dict[str, Any]] = None,
        multipart: Optional[List[Dict[str, Any]]] = None,
        files: Optional[List[File]] = None,
        reason: Optional[str] = None,
        auth_token: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        # always ensure our user agent is being used
        headers: Dict[str, str] = {"User-Agent": _USER_AGENT}
        files = files or []
        to_send: Optional[Union[str, aiohttp.FormData]] = None
        bucket = (route.webhook_id, route.webhook_token)

        try:
            lock = self._locks[bucket]
        except KeyError:
            self._locks[bucket] = lock = asyncio.Lock()

        if payload is not None:
            headers["Content-Type"] = "application/json"
            to_send = utils.to_json(payload)

        if auth_token is not None:
            headers["Authorization"] = f"Bot {auth_token}"

        if reason is not None:
            headers["X-Audit-Log-Reason"] = urlquote(reason, safe="/ ")

        response: Optional[aiohttp.ClientResponse] = None
        data: Optional[Union[Dict[str, Any], str]] = None
        method = route.method
        url = route.url
        webhook_id = route.webhook_id

        async with AsyncDeferredLock(lock) as lock:
            for attempt in range(5):
                for file in files:
                    file.reset(seek=attempt)

                if multipart:
                    form_data = aiohttp.FormData(quote_fields=False)
                    for p in multipart:
                        form_data.add_field(**p)
                    to_send = form_data

                try:
                    async with session.request(
                        method, url, data=to_send, headers=headers, params=params
                    ) as response:
                        _log.debug(
                            "Webhook ID %s with %s %s has returned status code %s",
                            webhook_id,
                            method,
                            url,
                            response.status,
                        )
                        data = (await response.text(encoding="utf-8")) or None
                        if data and response.headers["Content-Type"] == "application/json":
                            data = json.loads(data)

                        remaining = response.headers.get("X-Ratelimit-Remaining")
                        if remaining == "0" and response.status != 429:
                            delta = utils.parse_ratelimit_header(response)
                            _log.debug(
                                "Webhook ID %s has been pre-emptively rate limited, waiting %.2f seconds",
                                webhook_id,
                                delta,
                            )
                            lock.delay_by(delta)

                        if 300 > response.status >= 200:
                            return data

                        if response.status == 429:
                            if not response.headers.get("Via"):
                                raise HTTPException(response, data)

                            retry_after: float = data["retry_after"]  # type: ignore
                            _log.warning(
                                "Webhook ID %s is rate limited. Retrying in %.2f seconds",
                                webhook_id,
                                retry_after,
                            )
                            await asyncio.sleep(retry_after)
                            continue

                        if response.status >= 500:
                            await asyncio.sleep(1 + attempt * 2)
                            continue

                        if response.status == 403:
                            raise Forbidden(response, data)

                        if response.status == 404:
                            raise NotFound(response, data)

                        raise HTTPException(response, data)

                except OSError as e:
                    if attempt < 4 and e.errno in (54, 10054):
                        await asyncio.sleep(1 + attempt * 2)
                        continue
                    raise

            if response:
                if response.status >= 500:
                    raise DiscordServerError(response, data)
                raise HTTPException(response, data)

            raise RuntimeError("Unreachable code in HTTP handling.")

    def delete_webhook(
        self,
        webhook_id: int,
        *,
        token: Optional[str] = None,
        session: aiohttp.ClientSession,
        reason: Optional[str] = None,
    ) -> Response[None]:
        route = Route("DELETE", "/webhooks/{webhook_id}", webhook_id=webhook_id)
        return self.request(route, session, reason=reason, auth_token=token)

    def delete_webhook_with_token(
        self,
        webhook_id: int,
        token: str,
        *,
        session: aiohttp.ClientSession,
        reason: Optional[str] = None,
    ) -> Response[None]:
        route = Route(
            "DELETE",
            "/webhooks/{webhook_id}/{webhook_token}",
            webhook_id=webhook_id,
            webhook_token=token,
        )
        return self.request(route, session, reason=reason)

    def edit_webhook(
        self,
        webhook_id: int,
        token: str,
        payload: Dict[str, Any],
        *,
        session: aiohttp.ClientSession,
        reason: Optional[str] = None,
    ) -> Response[WebhookPayload]:
        route = Route("PATCH", "/webhooks/{webhook_id}", webhook_id=webhook_id)
        return self.request(route, session, reason=reason, payload=payload, auth_token=token)

    def edit_webhook_with_token(
        self,
        webhook_id: int,
        token: str,
        payload: Dict[str, Any],
        *,
        session: aiohttp.ClientSession,
        reason: Optional[str] = None,
    ) -> Response[WebhookPayload]:
        route = Route(
            "PATCH",
            "/webhooks/{webhook_id}/{webhook_token}",
            webhook_id=webhook_id,
            webhook_token=token,
        )
        return self.request(route, session, reason=reason, payload=payload)

    def execute_webhook(
        self,
        webhook_id: int,
        token: str,
        *,
        session: aiohttp.ClientSession,
        payload: Optional[Dict[str, Any]] = None,
        multipart: Optional[List[Dict[str, Any]]] = None,
        files: Optional[List[File]] = None,
        thread_id: Optional[int] = None,
        wait: bool = False,
    ) -> Response[Optional[MessagePayload]]:
        params = {"wait": int(wait)}
        if thread_id:
            params["thread_id"] = thread_id
        route = Route(
            "POST",
            "/webhooks/{webhook_id}/{webhook_token}",
            webhook_id=webhook_id,
            webhook_token=token,
        )
        return self.request(
            route, session, payload=payload, multipart=multipart, files=files, params=params
        )

    def get_webhook_message(
        self,
        webhook_id: int,
        token: str,
        message_id: int,
        *,
        session: aiohttp.ClientSession,
    ) -> Response[MessagePayload]:
        route = Route(
            "GET",
            "/webhooks/{webhook_id}/{webhook_token}/messages/{message_id}",
            webhook_id=webhook_id,
            webhook_token=token,
            message_id=message_id,
        )
        return self.request(route, session)

    def edit_webhook_message(
        self,
        webhook_id: int,
        token: str,
        message_id: int,
        *,
        session: aiohttp.ClientSession,
        payload: Optional[Dict[str, Any]] = None,
        multipart: Optional[List[Dict[str, Any]]] = None,
        files: Optional[List[File]] = None,
        thread_id: Optional[int] = None,
    ) -> Response[Message]:
        params = {}
        if thread_id:
            params["thread_id"] = thread_id
        route = Route(
            "PATCH",
            "/webhooks/{webhook_id}/{webhook_token}/messages/{message_id}",
            webhook_id=webhook_id,
            webhook_token=token,
            message_id=message_id,
        )
        return self.request(
            route, session, payload=payload, multipart=multipart, files=files, params=params
        )

    def delete_webhook_message(
        self,
        webhook_id: int,
        token: str,
        message_id: int,
        *,
        session: aiohttp.ClientSession,
    ) -> Response[None]:
        route = Route(
            "DELETE",
            "/webhooks/{webhook_id}/{webhook_token}/messages/{message_id}",
            webhook_id=webhook_id,
            webhook_token=token,
            message_id=message_id,
        )
        return self.request(route, session)

    def fetch_webhook(
        self,
        webhook_id: int,
        token: str,
        *,
        session: aiohttp.ClientSession,
    ) -> Response[WebhookPayload]:
        route = Route("GET", "/webhooks/{webhook_id}", webhook_id=webhook_id)
        return self.request(route, session=session, auth_token=token)

    def fetch_webhook_with_token(
        self,
        webhook_id: int,
        token: str,
        *,
        session: aiohttp.ClientSession,
    ) -> Response[WebhookPayload]:
        route = Route(
            "GET",
            "/webhooks/{webhook_id}/{webhook_token}",
            webhook_id=webhook_id,
            webhook_token=token,
        )
        return self.request(route, session=session)

    def create_interaction_response(
        self,
        interaction_id: int,
        token: str,
        *,
        session: aiohttp.ClientSession,
        type: int,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[List[File]] = None,
    ) -> Response[None]:
        payload: Dict[str, Any] | None = {
            "type": type,
        }

        if data is not None:
            payload["data"] = data

        multipart = []

        if files:
            if "data" not in payload:
                payload["data"] = {}
            if "attachments" not in payload["data"]:
                payload["data"]["attachments"] = []
            multipart.append({"name": "payload_json"})
            for index, file in enumerate(files):
                payload["data"]["attachments"].append(
                    {
                        "id": index,
                        "filename": file.filename,
                        "description": file.description,
                    }
                )
                multipart.append(
                    {
                        "name": f"files[{index}]",
                        "value": file.fp,
                        "filename": file.filename,
                        "content_type": "application/octet-stream",
                    }
                )
            multipart[0]["value"] = utils.to_json(payload)
            payload = None

        route = Route(
            "POST",
            "/interactions/{webhook_id}/{webhook_token}/callback",
            webhook_id=interaction_id,
            webhook_token=token,
        )

        return self.request(
            route, session=session, payload=payload, multipart=multipart, files=files
        )

    def get_original_interaction_response(
        self,
        application_id: int,
        token: str,
        *,
        session: aiohttp.ClientSession,
    ) -> Response[MessagePayload]:
        r = Route(
            "GET",
            "/webhooks/{webhook_id}/{webhook_token}/messages/@original",
            webhook_id=application_id,
            webhook_token=token,
        )
        return self.request(r, session=session)

    def edit_original_interaction_response(
        self,
        application_id: int,
        token: str,
        *,
        session: aiohttp.ClientSession,
        payload: Optional[Dict[str, Any]] = None,
        multipart: Optional[List[Dict[str, Any]]] = None,
        files: Optional[List[File]] = None,
    ) -> Response[MessagePayload]:
        r = Route(
            "PATCH",
            "/webhooks/{webhook_id}/{webhook_token}/messages/@original",
            webhook_id=application_id,
            webhook_token=token,
        )
        return self.request(r, session, payload=payload, multipart=multipart, files=files)

    def delete_original_interaction_response(
        self,
        application_id: int,
        token: str,
        *,
        session: aiohttp.ClientSession,
    ) -> Response[None]:
        r = Route(
            "DELETE",
            "/webhooks/{webhook_id}/{wehook_token}/messages/@original",
            webhook_id=application_id,
            wehook_token=token,
        )
        return self.request(r, session=session)


class ExecuteWebhookParameters(NamedTuple):
    payload: Optional[Dict[str, Any]]
    multipart: Optional[List[Dict[str, Any]]]
    files: Optional[List[File]]


def handle_message_parameters(
    content: Optional[str] = MISSING,
    *,
    username: str = MISSING,
    avatar_url: Any = MISSING,
    tts: bool = False,
    file: File = MISSING,
    files: List[File] = MISSING,
    attachments: List[Attachment] = MISSING,
    embed: Optional[Embed] = MISSING,
    embeds: List[Embed] = MISSING,
    view: Optional[View] = MISSING,
    allowed_mentions: Optional[AllowedMentions] = MISSING,
    previous_allowed_mentions: Optional[AllowedMentions] = None,
    ephemeral: Optional[bool] = None,
    flags: Optional[MessageFlags] = None,
    suppress_embeds: Optional[bool] = None,
    thread_name: Optional[str] = None,
) -> ExecuteWebhookParameters:
    if files is not MISSING and file is not MISSING:
        raise InvalidArgument("Cannot mix file and files keyword arguments.")
    if embeds is not MISSING and embed is not MISSING:
        raise InvalidArgument("Cannot mix embed and embeds keyword arguments.")

    payload: Dict[str, Any] | None = {}

    if thread_name:
        payload["thread_name"] = thread_name

    if file is not MISSING or files is not MISSING:
        payload["attachments"] = []

    if attachments is not MISSING:
        payload["attachments"] = [a.to_dict() for a in attachments]

    if embeds is not MISSING:
        payload["embeds"] = [e.to_dict() for e in embeds]

    if embed is not MISSING:
        if embed is None:
            payload["embeds"] = []
        else:
            payload["embeds"] = [embed.to_dict()]

    if content is not MISSING:
        if content is not None:
            payload["content"] = str(content)
        else:
            payload["content"] = None

    if view is not MISSING:
        if view is not None:
            payload["components"] = view.to_components()
        else:
            payload["components"] = []

    payload["tts"] = tts
    if avatar_url:
        payload["avatar_url"] = str(avatar_url)
    if username:
        payload["username"] = username

    if flags is None:
        flags = MessageFlags()
    if suppress_embeds is not None:
        flags.suppress_embeds = suppress_embeds
    if ephemeral is not None:
        flags.ephemeral = ephemeral

    if flags.value != 0:
        payload["flags"] = flags.value

    if allowed_mentions:
        if previous_allowed_mentions is not None:
            payload["allowed_mentions"] = previous_allowed_mentions.merge(
                allowed_mentions
            ).to_dict()
        else:
            payload["allowed_mentions"] = allowed_mentions.to_dict()
    elif previous_allowed_mentions is not None:
        payload["allowed_mentions"] = previous_allowed_mentions.to_dict()

    multipart = []
    if file is not MISSING:
        files = [file]

    if files:
        multipart.append({"name": "payload_json"})
        for index, file in enumerate(files):  # noqa: PLR1704
            payload["attachments"].append(
                {
                    "id": index,
                    "filename": file.filename,
                    "description": file.description,  # type: ignore
                    # ignore complaints about assigning to an Attachment
                }
            )
            multipart.append(
                {
                    "name": f"files[{index}]",
                    "value": file.fp,
                    "filename": file.filename,
                    "content_type": "application/octet-stream",
                }
            )
        multipart[0]["value"] = utils.to_json(payload)
        payload = None

    return ExecuteWebhookParameters(payload=payload, multipart=multipart, files=files)


async_context: ContextVar[AsyncWebhookAdapter] = ContextVar(
    "async_webhook_context", default=AsyncWebhookAdapter()
)


class PartialWebhookChannel(Hashable):
    """Represents a partial channel for webhooks.

    These are typically given for channel follower webhooks.

    .. versionadded:: 2.0

    Attributes
    ----------
    id: :class:`int`
        The partial channel's ID.
    name: :class:`str`
        The partial channel's name.
    """

    __slots__ = ("id", "name")

    def __init__(self, *, data) -> None:
        self.id = int(data["id"])
        self.name = data["name"]

    def __repr__(self) -> str:
        return f"<PartialWebhookChannel name={self.name!r} id={self.id}>"


class PartialWebhookGuild(Hashable):
    """Represents a partial guild for webhooks.

    These are typically given for channel follower webhooks.

    .. versionadded:: 2.0

    Attributes
    ----------
    id: :class:`int`
        The partial guild's ID.
    name: :class:`str`
        The partial guild's name.
    """

    __slots__ = ("id", "name", "_icon", "_state")

    def __init__(self, *, data, state) -> None:
        self._state = state
        self.id = int(data["id"])
        self.name = data["name"]
        self._icon = data["icon"]

    def __repr__(self) -> str:
        return f"<PartialWebhookGuild name={self.name!r} id={self.id}>"

    @property
    def icon(self) -> Optional[Asset]:
        """Optional[:class:`Asset`]: Returns the guild's icon asset, if available."""
        if self._icon is None:
            return None
        return Asset._from_guild_icon(self._state, self.id, self._icon)


class _FriendlyHttpAttributeErrorHelper:
    __slots__ = ()

    def __getattr__(self, attr):
        raise AttributeError("PartialWebhookState does not support http methods.")


class _WebhookState:
    __slots__ = ("_parent", "_webhook")

    def __init__(
        self, webhook: Any, parent: Optional[Union[ConnectionState, _WebhookState]]
    ) -> None:
        self._webhook: Any = webhook

        self._parent: Optional[ConnectionState]
        if isinstance(parent, _WebhookState):
            self._parent = None
        else:
            self._parent = parent

    def _get_guild(self, guild_id):
        if self._parent is not None:
            return self._parent._get_guild(guild_id)
        return None

    def store_user(self, data):
        if self._parent is not None:
            return self._parent.store_user(data)
        # state parameter is artificial
        return BaseUser(state=self, data=data)  # type: ignore

    def create_user(self, data):
        # state parameter is artificial
        return BaseUser(state=self, data=data)  # type: ignore

    @property
    def http(self):
        if self._parent is not None:
            return self._parent.http

        # Some data classes assign state.http and that should be kosher
        # however, using it should result in a late-binding error.
        return _FriendlyHttpAttributeErrorHelper()

    def __getattr__(self, attr):
        if self._parent is not None:
            return getattr(self._parent, attr)

        raise AttributeError(f"PartialWebhookState does not support {attr!r}.")


class WebhookMessage(Message):
    """Represents a message sent from your webhook.

    This allows you to edit or delete a message sent by your
    webhook.

    This inherits from :class:`nexon.Message` with changes to
    :meth:`edit` and :meth:`delete` to work.

    .. versionadded:: 1.6
    """

    _state: _WebhookState

    async def edit(
        self,
        content: Optional[str] = MISSING,
        embeds: List[Embed] = MISSING,
        embed: Optional[Embed] = MISSING,
        file: File = MISSING,
        files: List[File] = MISSING,
        attachments: List[Attachment] = MISSING,
        view: Optional[View] = MISSING,
        allowed_mentions: Optional[AllowedMentions] = None,
        delete_after: Optional[float] = None,
    ) -> WebhookMessage:
        """|coro|

        Edits the message.

        .. versionadded:: 1.6

        .. versionchanged:: 2.0
            The edit is no longer in-place, instead the newly edited message is returned.

        Parameters
        ----------
        content: Optional[:class:`str`]
            The content to edit the message with or ``None`` to clear it.
        embeds: List[:class:`Embed`]
            A list of embeds to edit the message with.
        embed: Optional[:class:`Embed`]
            The embed to edit the message with. ``None`` suppresses the embeds.
            This should not be mixed with the ``embeds`` parameter.
        file: :class:`File`
            The file to upload. This cannot be mixed with ``files`` parameter.

            .. versionadded:: 2.0
        files: List[:class:`File`]
            A list of files to send with the content. This cannot be mixed with the
            ``file`` parameter.

            .. versionadded:: 2.0
        attachments: List[:class:`Attachment`]
            A list of attachments to keep in the message. To keep all existing attachments,
            pass ``message.attachments``.

            .. versionadded:: 2.0
        allowed_mentions: :class:`AllowedMentions`
            Controls the mentions being processed in this message.
            See :meth:`.abc.Messageable.send` for more information.
        view: Optional[:class:`~nexon.ui.View`]
            The updated view to update this message with. If ``None`` is passed then
            the view is removed.

            .. versionadded:: 2.0
        delete_after: Optional[:class:`float`]
            If provided, the number of seconds to wait in the background
            before deleting the message we just edited. If the deletion fails,
            then it is silently ignored.

            .. versionadded:: 2.0

        Raises
        ------
        HTTPException
            Editing the message failed.
        Forbidden
            Edited a message that is not yours.
        InvalidArgument
            You specified both ``embed`` and ``embeds`` or ``file`` and ``files``.
        ValueError
            The length of ``embeds`` was invalid.
        InvalidArgument
            There was no token associated with this webhook.

        Returns
        -------
        :class:`WebhookMessage`
            The newly edited message.
        """
        message = await self._state._webhook.edit_message(
            self.id,
            content=content,
            embeds=embeds,
            embed=embed,
            file=file,
            files=files,
            attachments=attachments,
            view=view,
            allowed_mentions=allowed_mentions,
        )

        if delete_after is not None:
            await self.delete(delay=delete_after)

        return message

    async def delete(self, *, delay: Optional[float] = None) -> None:
        """|coro|

        Deletes the message.

        Parameters
        ----------
        delay: Optional[:class:`float`]
            If provided, the number of seconds to wait before deleting the message.
            The waiting is done in the background and deletion failures are ignored.

        Raises
        ------
        Forbidden
            You do not have proper permissions to delete the message.
        NotFound
            The message was deleted already.
        HTTPException
            Deleting the message failed.
        """

        if delay is not None:

            async def inner_call(delay: float = delay) -> None:
                await asyncio.sleep(delay)
                with contextlib.suppress(HTTPException):
                    await self._state._webhook.delete_message(self.id)

            task = asyncio.create_task(inner_call())
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        else:
            await self._state._webhook.delete_message(self.id)


class BaseWebhook(Hashable):
    __slots__: Tuple[str, ...] = (
        "id",
        "type",
        "guild_id",
        "channel_id",
        "token",
        "auth_token",
        "user",
        "name",
        "_avatar",
        "source_channel",
        "source_guild",
        "_state",
    )

    def __init__(
        self,
        data: WebhookPayload,
        token: Optional[str] = None,
        state: Optional[ConnectionState] = None,
    ) -> None:
        self.auth_token: Optional[str] = token
        self._state: Union[ConnectionState, _WebhookState] = state or _WebhookState(
            self, parent=state
        )
        self._update(data)

    def _update(self, data: WebhookPayload) -> None:
        self.id = int(data["id"])
        self.type = try_enum(WebhookType, int(data["type"]))
        self.channel_id = utils.get_as_snowflake(data, "channel_id")
        self.guild_id = utils.get_as_snowflake(data, "guild_id")
        self.name = data.get("name")
        self._avatar = data.get("avatar")
        self.token = data.get("token")

        user = data.get("user")
        self.user: Optional[Union[BaseUser, User]] = None
        if user is not None:
            # state parameter may be _WebhookState
            self.user = User(state=self._state, data=user)  # type: ignore

        source_channel = data.get("source_channel")
        if source_channel:
            source_channel = PartialWebhookChannel(data=source_channel)

        self.source_channel: Optional[PartialWebhookChannel] = source_channel

        source_guild = data.get("source_guild")
        if source_guild:
            source_guild = PartialWebhookGuild(data=source_guild, state=self._state)

        self.source_guild: Optional[PartialWebhookGuild] = source_guild

    def is_partial(self) -> bool:
        """:class:`bool`: Whether the webhook is a "partial" webhook.

        .. versionadded:: 2.0"""
        return self.channel_id is None

    def is_authenticated(self) -> bool:
        """:class:`bool`: Whether the webhook is authenticated with a bot token.

        .. versionadded:: 2.0
        """
        return self.auth_token is not None

    @property
    def guild(self) -> Optional[Guild]:
        """Optional[:class:`Guild`]: The guild this webhook belongs to.

        If this is a partial webhook, then this will always return ``None``.
        """
        return self._state and self._state._get_guild(self.guild_id)

    @property
    def channel(self) -> Optional[TextChannel]:
        """Optional[:class:`TextChannel`]: The text channel this webhook belongs to.

        If this is a partial webhook, then this will always return ``None``.
        """
        guild = self.guild
        return guild and guild.get_channel(self.channel_id)  # type: ignore

    @property
    def created_at(self) -> datetime.datetime:
        """:class:`datetime.datetime`: Returns the webhook's creation time in UTC."""
        return utils.snowflake_time(self.id)

    @property
    def avatar(self) -> Asset:
        """:class:`Asset`: Returns an :class:`Asset` for the avatar the webhook has.

        If the webhook does not have a traditional avatar, an asset for
        the default avatar is returned instead.
        """
        if self._avatar is None:
            # Default is always blurple apparently
            return Asset._from_default_avatar(self._state, 0)
        return Asset._from_avatar(self._state, self.id, self._avatar)


class Webhook(BaseWebhook):
    """Represents an asynchronous Discord webhook.

    Webhooks are a form to send messages to channels in Discord without a
    bot user or authentication.

    There are two main ways to use Webhooks. The first is through the ones
    received by the library such as :meth:`.Guild.webhooks` and
    :meth:`.TextChannel.webhooks`. The ones received by the library will
    automatically be bound using the library's internal HTTP session.

    The second form involves creating a webhook object manually using the
    :meth:`~.Webhook.from_url` or :meth:`~.Webhook.partial` classmethods.

    For example, creating a webhook from a URL and using :doc:`aiohttp <aio:index>`:

    .. code-block:: python3

        from nexon import Webhook
        import aiohttp

        async def foo():
            async with aiohttp.ClientSession() as session:
                webhook = Webhook.from_url('url-here', session=session)
                await webhook.send('Hello World', username='Foo')

    For a synchronous counterpart, see :class:`SyncWebhook`.

    .. container:: operations

        .. describe:: x == y

            Checks if two webhooks are equal.

        .. describe:: x != y

            Checks if two webhooks are not equal.

        .. describe:: hash(x)

            Returns the webhooks's hash.

    .. versionchanged:: 1.4
        Webhooks are now comparable and hashable.

    Attributes
    ----------
    id: :class:`int`
        The webhook's ID
    type: :class:`WebhookType`
        The type of the webhook.

        .. versionadded:: 1.3

    token: Optional[:class:`str`]
        The authentication token of the webhook. If this is ``None``
        then the webhook cannot be used to make requests.
    guild_id: Optional[:class:`int`]
        The guild ID this webhook is for.
    channel_id: Optional[:class:`int`]
        The channel ID this webhook is for.
    user: Optional[:class:`abc.User`]
        The user this webhook was created by. If the webhook was
        received without authentication then this will be ``None``.
    name: Optional[:class:`str`]
        The default name of the webhook.
    source_guild: Optional[:class:`PartialWebhookGuild`]
        The guild of the channel that this webhook is following.
        Only given if :attr:`type` is :attr:`WebhookType.channel_follower`.

        .. versionadded:: 2.0

    source_channel: Optional[:class:`PartialWebhookChannel`]
        The channel that this webhook is following.
        Only given if :attr:`type` is :attr:`WebhookType.channel_follower`.

        .. versionadded:: 2.0
    """

    __slots__: Tuple[str, ...] = ("session",)

    def __init__(
        self,
        data: WebhookPayload,
        session: aiohttp.ClientSession,
        token: Optional[str] = None,
        state=None,
    ) -> None:
        super().__init__(data, token, state)
        self.session = session

    def __repr__(self) -> str:
        return f"<Webhook id={self.id!r}>"

    @property
    def url(self) -> str:
        """:class:`str` : Returns the webhook's url."""
        return f"https://discord.com/api/webhooks/{self.id}/{self.token}"

    @classmethod
    def partial(
        cls, id: int, token: str, *, session: aiohttp.ClientSession, bot_token: Optional[str] = None
    ) -> Webhook:
        """Creates a partial :class:`Webhook`.

        Parameters
        ----------
        id: :class:`int`
            The ID of the webhook.
        token: :class:`str`
            The authentication token of the webhook.
        session: :class:`aiohttp.ClientSession`
            The session to use to send requests with. Note
            that the library does not manage the session and
            will not close it.

            .. versionadded:: 2.0
        bot_token: Optional[:class:`str`]
            The bot authentication token for authenticated requests
            involving the webhook.

            .. versionadded:: 2.0

        Returns
        -------
        :class:`Webhook`
            A partial :class:`Webhook`.
            A partial webhook is just a webhook object with an ID and a token.
        """
        data: WebhookPayload = {
            "id": id,
            "type": 1,
            "token": token,
        }

        return cls(data, session, token=bot_token)

    @classmethod
    def from_url(
        cls, url: str, *, session: aiohttp.ClientSession, bot_token: Optional[str] = None
    ) -> Webhook:
        """Creates a partial :class:`Webhook` from a webhook URL.

        Parameters
        ----------
        url: :class:`str`
            The URL of the webhook.
        session: :class:`aiohttp.ClientSession`
            The session to use to send requests with. Note
            that the library does not manage the session and
            will not close it.

            .. versionadded:: 2.0
        bot_token: Optional[:class:`str`]
            The bot authentication token for authenticated requests
            involving the webhook.

            .. versionadded:: 2.0

        Raises
        ------
        InvalidArgument
            The URL is invalid.

        Returns
        -------
        :class:`Webhook`
            A partial :class:`Webhook`.
            A partial webhook is just a webhook object with an ID and a token.
        """
        m = re.search(
            r"discord(?:app)?.com/api/webhooks/(?P<id>[0-9]{17,20})/(?P<token>[A-Za-z0-9\.\-\_]{60,68})",
            url,
        )
        if m is None:
            raise InvalidArgument("Invalid webhook URL given.")

        data: Dict[str, Any] = m.groupdict()
        data["type"] = 1
        return cls(data, session, token=bot_token)  # type: ignore

    @classmethod
    def _as_follower(cls, data, *, channel, user) -> Webhook:
        name = f"{channel.guild} #{channel}"
        feed: WebhookPayload = {
            "id": data["webhook_id"],
            "type": 2,
            "name": name,
            "channel_id": channel.id,
            "guild_id": channel.guild.id,
            "user": {
                "username": user.name,
                "global_name": user.global_name,
                "discriminator": user.discriminator,
                "id": user.id,
                "avatar": user._avatar,
            },
        }

        state = channel._state
        session = channel._state.http._HTTPClient__session
        return cls(feed, session=session, state=state, token=state._get_client()._token)

    @classmethod
    def from_state(cls, data, state) -> Webhook:
        session = state.http._HTTPClient__session
        return cls(data, session=session, state=state, token=state._get_client()._token)

    async def fetch(self, *, prefer_auth: bool = True) -> Webhook:
        """|coro|

        Fetches the current webhook.

        This could be used to get a full webhook from a partial webhook.

        .. versionadded:: 2.0

        .. note::

            When fetching with an unauthenticated webhook, i.e.
            :meth:`is_authenticated` returns ``False``, then the
            returned webhook does not contain any user information.

        Parameters
        ----------
        prefer_auth: :class:`bool`
            Whether to use the bot token over the webhook token
            if available. Defaults to ``True``.

        Raises
        ------
        HTTPException
            Could not fetch the webhook
        NotFound
            Could not find the webhook by this ID
        InvalidArgument
            This webhook does not have a token associated with it.

        Returns
        -------
        :class:`Webhook`
            The fetched webhook.
        """
        adapter = async_context.get()

        if prefer_auth and self.auth_token:
            data = await adapter.fetch_webhook(self.id, self.auth_token, session=self.session)
        elif self.token:
            data = await adapter.fetch_webhook_with_token(self.id, self.token, session=self.session)
        else:
            raise InvalidArgument("This webhook does not have a token associated with it")

        return Webhook(data, self.session, token=self.auth_token, state=self._state)

    async def delete(self, *, reason: Optional[str] = None, prefer_auth: bool = True):
        """|coro|

        Deletes this Webhook.

        Parameters
        ----------
        reason: Optional[:class:`str`]
            The reason for deleting this webhook. Shows up on the audit log.

            .. versionadded:: 1.4
        prefer_auth: :class:`bool`
            Whether to use the bot token over the webhook token
            if available. Defaults to ``True``.

            .. versionadded:: 2.0

        Raises
        ------
        HTTPException
            Deleting the webhook failed.
        NotFound
            This webhook does not exist.
        Forbidden
            You do not have permissions to delete this webhook.
        InvalidArgument
            This webhook does not have a token associated with it.
        """
        if self.token is None and self.auth_token is None:
            raise InvalidArgument("This webhook does not have a token associated with it")

        adapter = async_context.get()

        if prefer_auth and self.auth_token:
            await adapter.delete_webhook(
                self.id, token=self.auth_token, session=self.session, reason=reason
            )
        elif self.token:
            await adapter.delete_webhook_with_token(
                self.id, self.token, session=self.session, reason=reason
            )

    async def edit(
        self,
        *,
        reason: Optional[str] = None,
        name: Optional[str] = MISSING,
        avatar: Optional[Union[bytes, Asset, Attachment, File]] = MISSING,
        channel: Optional[Snowflake] = None,
        prefer_auth: bool = True,
    ) -> Webhook:
        """|coro|

        Edits this Webhook.

        .. versionchanged:: 2.1
            The ``avatar`` parameter now accepts :class:`File`, :class:`Attachment`, and :class:`Asset`.

        Parameters
        ----------
        name: Optional[:class:`str`]
            The webhook's new default name.
        avatar: Optional[Union[:class:`bytes`, :class:`Asset`, :class:`Attachment`, :class:`File`]]
            A :term:`py:bytes-like object`, :class:`File`, :class:`Attachment`, or :class:`Asset`
            representing the webhook's new default avatar.
        channel: Optional[:class:`abc.Snowflake`]
            The webhook's new channel. This requires an authenticated webhook.

            .. versionadded:: 2.0
        reason: Optional[:class:`str`]
            The reason for editing this webhook. Shows up on the audit log.

            .. versionadded:: 1.4
        prefer_auth: :class:`bool`
            Whether to use the bot token over the webhook token
            if available. Defaults to ``True``.

            .. versionadded:: 2.0

        Raises
        ------
        HTTPException
            Editing the webhook failed.
        NotFound
            This webhook does not exist.
        InvalidArgument
            This webhook does not have a token associated with it
            or it tried editing a channel without authentication.
        """
        if self.token is None and self.auth_token is None:
            raise InvalidArgument("This webhook does not have a token associated with it")

        payload: Dict[str, Any] = {}
        if name is not MISSING:
            payload["name"] = str(name) if name is not None else None

        if avatar is not MISSING:
            payload["avatar"] = await utils.obj_to_base64_data(avatar)

        adapter = async_context.get()

        data: Optional[WebhookPayload] = None
        # If a channel is given, always use the authenticated endpoint
        if channel is not None:
            if self.auth_token is None:
                raise InvalidArgument("Editing channel requires authenticated webhook")

            payload["channel_id"] = channel.id
            data = await adapter.edit_webhook(
                self.id, self.auth_token, payload=payload, session=self.session, reason=reason
            )

        if prefer_auth and self.auth_token:
            data = await adapter.edit_webhook(
                self.id, self.auth_token, payload=payload, session=self.session, reason=reason
            )
        elif self.token:
            data = await adapter.edit_webhook_with_token(
                self.id, self.token, payload=payload, session=self.session, reason=reason
            )

        if data is None:
            raise RuntimeError("Unreachable code hit: data was not assigned")

        return Webhook(data=data, session=self.session, token=self.auth_token, state=self._state)

    def _create_message(self, data):
        state = _WebhookState(self, parent=self._state)
        # state may be artificial (unlikely at this point...)
        channel = self.channel or PartialMessageable(state=self._state, id=int(data["channel_id"]))  # type: ignore
        # state is artificial
        return WebhookMessage(data=data, state=state, channel=channel)  # type: ignore

    @overload
    async def send(
        self,
        content: str = MISSING,
        *,
        username: str = MISSING,
        avatar_url: Union[Asset, str] = MISSING,
        tts: bool = MISSING,
        file: File = MISSING,
        files: List[File] = MISSING,
        embed: Embed = MISSING,
        embeds: List[Embed] = MISSING,
        allowed_mentions: AllowedMentions = MISSING,
        view: View = MISSING,
        thread: Snowflake = MISSING,
        wait: Literal[True],
        delete_after: Optional[float] = None,
        ephemeral: Optional[bool] = None,
        flags: Optional[MessageFlags] = None,
        suppress_embeds: Optional[bool] = None,
        thread_name: Optional[str] = None,
    ) -> WebhookMessage: ...

    @overload
    async def send(
        self,
        content: str = MISSING,
        *,
        username: str = MISSING,
        avatar_url: Union[Asset, str] = MISSING,
        tts: bool = MISSING,
        file: File = MISSING,
        files: List[File] = MISSING,
        embed: Embed = MISSING,
        embeds: List[Embed] = MISSING,
        allowed_mentions: AllowedMentions = MISSING,
        view: View = MISSING,
        thread: Snowflake = MISSING,
        wait: Literal[False] = ...,
        delete_after: Optional[float] = None,
        ephemeral: Optional[bool] = None,
        flags: Optional[MessageFlags] = None,
        suppress_embeds: Optional[bool] = None,
        thread_name: Optional[str] = None,
    ) -> None: ...

    async def send(
        self,
        content: str = MISSING,
        *,
        username: str = MISSING,
        avatar_url: Union[Asset, str] = MISSING,
        tts: bool = False,
        file: File = MISSING,
        files: List[File] = MISSING,
        embed: Embed = MISSING,
        embeds: List[Embed] = MISSING,
        allowed_mentions: AllowedMentions = MISSING,
        view: View = MISSING,
        thread: Snowflake = MISSING,
        wait: bool = False,
        delete_after: Optional[float] = None,
        ephemeral: Optional[bool] = None,
        flags: Optional[MessageFlags] = None,
        suppress_embeds: Optional[bool] = None,
        thread_name: Optional[str] = None,
    ) -> Optional[WebhookMessage]:
        """|coro|

        Sends a message using the webhook.

        The content must be a type that can convert to a string through ``str(content)``.

        To upload a single file, the ``file`` parameter should be used with a
        single :class:`File` object.

        If the ``embed`` parameter is provided, it must be of type :class:`Embed` and
        it must be a rich embed type. You cannot mix the ``embed`` parameter with the
        ``embeds`` parameter, which must be a :class:`list` of :class:`Embed` objects to send.

        .. versionchanged:: 2.4

            ``ephemeral`` can now accept ``None`` to indicate that
            ``flags`` should be used.

        Parameters
        ----------
        content: :class:`str`
            The content of the message to send.
        wait: :class:`bool`
            Whether the server should wait before sending a response. This essentially
            means that the return type of this function changes from ``None`` to
            a :class:`WebhookMessage` if set to ``True``. If the type of webhook
            is :attr:`WebhookType.application` then this is always set to ``True``.
        username: :class:`str`
            The username to send with this message. If no username is provided
            then the default username for the webhook is used.
        avatar_url: :class:`str`
            The avatar URL to send with this message. If no avatar URL is provided
            then the default avatar for the webhook is used. If this is not a
            string then it is explicitly cast using ``str``.
        tts: :class:`bool`
            Indicates if the message should be sent using text-to-speech.
        ephemeral: :class:`bool`
            Indicates if the message should only be visible to the user.
            This is only available to :attr:`WebhookType.application` webhooks.
            If a view is sent with an ephemeral message and it has no timeout set
            then the timeout is set to 15 minutes.
        delete_after: Optional[:class:`float`]
            If provided, the number of seconds to wait in the background
            before deleting the message we just sent. If the deletion fails,
            then it is silently ignored.

            .. versionadded:: 2.0
        file: :class:`File`
            The file to upload. This cannot be mixed with ``files`` parameter.
        files: List[:class:`File`]
            A list of files to send with the content. This cannot be mixed with the
            ``file`` parameter.
        embed: :class:`Embed`
            The rich embed for the content to send. This cannot be mixed with
            ``embeds`` parameter.
        embeds: List[:class:`Embed`]
            A list of embeds to send with the content. Maximum of 10. This cannot
            be mixed with the ``embed`` parameter.
        allowed_mentions: :class:`AllowedMentions`
            Controls the mentions being processed in this message.

            .. versionadded:: 1.4
        view: :class:`nexon.ui.View`
            The view to send with the message. You can only send a view
            if this webhook is not partial and has state attached. A
            webhook has state attached if the webhook is managed by the
            library.

            .. versionadded:: 2.0
        thread: :class:`~nexon.abc.Snowflake`
            Send a message to the specified thread.
            The thread will automatically be unarchived.

            .. versionadded:: 2.0
        flags: Optional[:class:`~nexon.MessageFlags`]
            The message flags being set for this message.
            Currently only :class:`~nexon.MessageFlags.suppress_embeds` is able to be set.

            .. versionadded:: 2.4
        suppress_embeds: Optional[:class:`bool`]
            Whether to suppress embeds on this message.

            .. versionadded:: 2.4
        thread_name:
            Name of thread to create (requires the webhook channel to be a forum or media channel).

            .. versionadded:: 3.0

        Raises
        ------
        HTTPException
            Sending the message failed.
        NotFound
            This webhook was not found or has expired.
        Forbidden
            The authorization token for the webhook is incorrect.
        InvalidArgument
            You specified both ``embed`` and ``embeds`` or ``file`` and ``files``.
        ValueError
            The length of ``embeds`` was invalid.
        InvalidArgument
            There was no token associated with this webhook or ``ephemeral``
            was passed with the improper webhook type or there was no state
            attached with this webhook when giving it a view.

        Returns
        -------
        Optional[:class:`WebhookMessage`]
            If ``wait`` is ``True`` then the message that was sent, otherwise ``None``.
        """

        if self.token is None:
            raise InvalidArgument("This webhook does not have a token associated with it")

        previous_mentions: Optional[AllowedMentions] = getattr(
            self._state, "allowed_mentions", None
        )

        application_webhook = self.type is WebhookType.application
        if ephemeral and not application_webhook:
            raise InvalidArgument("ephemeral messages can only be sent from application webhooks")

        if application_webhook:
            wait = True

        if view is not MISSING:
            if isinstance(self._state, _WebhookState):
                raise InvalidArgument("Webhook views require an associated state with the webhook")
            if ephemeral is True and view.timeout is None and view.prevent_update:
                view.timeout = 15 * 60.0

        params = handle_message_parameters(
            content=content,
            username=username,
            avatar_url=avatar_url,
            tts=tts,
            file=file,
            files=files,
            embed=embed,
            embeds=embeds,
            ephemeral=ephemeral,
            view=view,
            allowed_mentions=allowed_mentions,
            previous_allowed_mentions=previous_mentions,
            flags=flags,
            suppress_embeds=suppress_embeds,
            thread_name=thread_name,
        )
        adapter = async_context.get()

        data = await adapter.execute_webhook(
            self.id,
            self.token,
            session=self.session,
            payload=params.payload,
            multipart=params.multipart,
            files=params.files,
            thread_id=thread.id if thread else None,
            wait=wait,
        )

        msg = None
        if wait:
            msg = self._create_message(data)

        if view is not MISSING and not view.is_finished() and view.prevent_update:
            message_id = None if msg is None else msg.id
            self._state.store_view(view, message_id)

        if delete_after is not None and msg is not None:
            await msg.delete(delay=delete_after)

        return msg

    async def fetch_message(self, id: int) -> WebhookMessage:
        """|coro|

        Retrieves a single :class:`~nexon.WebhookMessage` owned by this webhook.

        .. versionadded:: 2.0

        Parameters
        ----------
        id: :class:`int`
            The message ID to look for.

        Raises
        ------
        ~nexon.NotFound
            The specified message was not found.
        ~nexon.Forbidden
            You do not have the permissions required to get a message.
        ~nexon.HTTPException
            Retrieving the message failed.
        InvalidArgument
            There was no token associated with this webhook.

        Returns
        -------
        :class:`~nexon.WebhookMessage`
            The message asked for.
        """

        if self.token is None:
            raise InvalidArgument("This webhook does not have a token associated with it")

        adapter = async_context.get()
        data = await adapter.get_webhook_message(
            self.id,
            self.token,
            id,
            session=self.session,
        )
        return self._create_message(data)

    async def edit_message(
        self,
        message_id: int,
        *,
        content: Optional[str] = MISSING,
        embeds: List[Embed] = MISSING,
        embed: Optional[Embed] = MISSING,
        file: File = MISSING,
        files: List[File] = MISSING,
        attachments: List[Attachment] = MISSING,
        view: Optional[View] = MISSING,
        thread: Snowflake = MISSING,
        allowed_mentions: Optional[AllowedMentions] = None,
    ) -> WebhookMessage:
        """|coro|

        Edits a message owned by this webhook.

        This is a lower level interface to :meth:`WebhookMessage.edit` in case
        you only have an ID.

        .. versionadded:: 1.6

        .. versionchanged:: 2.0
            The edit is no longer in-place, instead the newly edited message is returned.

        Parameters
        ----------
        message_id: :class:`int`
            The message ID to edit.
        content: Optional[:class:`str`]
            The content to edit the message with or ``None`` to clear it.
        embeds: List[:class:`Embed`]
            A list of embeds to edit the message with.
        embed: Optional[:class:`Embed`]
            The embed to edit the message with. ``None`` suppresses the embeds.
            This should not be mixed with the ``embeds`` parameter.
        file: :class:`File`
            The file to upload. This cannot be mixed with ``files`` parameter.

            .. versionadded:: 2.0
        files: List[:class:`File`]
            A list of files to send with the content. This cannot be mixed with the
            ``file`` parameter.

            .. versionadded:: 2.0
        attachments: List[:class:`Attachment`]
            A list of attachments to keep in the message.

            .. versionadded:: 2.0
        allowed_mentions: :class:`AllowedMentions`
            Controls the mentions being processed in this message.
            See :meth:`.abc.Messageable.send` for more information.
        view: Optional[:class:`~nexon.ui.View`]
            The updated view to update this message with. If ``None`` is passed then
            the view is removed. The webhook must have state attached, similar to
            :meth:`send`.

            .. versionadded:: 2.0
        thread: :class:`~nexon.abc.Snowflake`
            The thread that the message to be edited is in.

            .. versionadded:: 3.0

        Raises
        ------
        HTTPException
            Editing the message failed.
        Forbidden
            Edited a message that is not yours.
        InvalidArgument
            You specified both ``embed`` and ``embeds`` or ``file`` and ``files``.
        ValueError
            The length of ``embeds`` was invalid.
        InvalidArgument
            There was no token associated with this webhook or the webhook had
            no state.

        Returns
        -------
        :class:`WebhookMessage`
            The newly edited webhook message.
        """

        if self.token is None:
            raise InvalidArgument("This webhook does not have a token associated with it")

        if view is not MISSING:
            if isinstance(self._state, _WebhookState):
                raise InvalidArgument("This webhook does not have state associated with it")

            self._state.prevent_view_updates_for(message_id)

        previous_mentions: Optional[AllowedMentions] = getattr(
            self._state, "allowed_mentions", None
        )
        params = handle_message_parameters(
            content=content,
            file=file,
            files=files,
            attachments=attachments,
            embed=embed,
            embeds=embeds,
            view=view,
            allowed_mentions=allowed_mentions,
            previous_allowed_mentions=previous_mentions,
        )
        adapter = async_context.get()
        thread_id: Optional[int] = None
        if thread is not MISSING:
            thread_id = thread.id

        data = await adapter.edit_webhook_message(
            self.id,
            self.token,
            message_id,
            session=self.session,
            payload=params.payload,
            multipart=params.multipart,
            files=params.files,
            thread_id=thread_id,
        )

        message = self._create_message(data)
        if view and not view.is_finished() and view.prevent_update:
            self._state.store_view(view, message_id)
        return message

    async def delete_message(self, message_id: int, /) -> None:
        """|coro|

        Deletes a message owned by this webhook.

        This is a lower level interface to :meth:`WebhookMessage.delete` in case
        you only have an ID.

        .. versionadded:: 1.6

        Parameters
        ----------
        message_id: :class:`int`
            The message ID to delete.

        Raises
        ------
        HTTPException
            Deleting the message failed.
        Forbidden
            Deleted a message that is not yours.
        """
        if self.token is None:
            raise InvalidArgument("This webhook does not have a token associated with it")

        adapter = async_context.get()
        await adapter.delete_webhook_message(
            self.id,
            self.token,
            message_id,
            session=self.session,
        )
