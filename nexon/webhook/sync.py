# SPDX-License-Identifier: MIT

# If you're wondering why this is essentially copy pasted from the async_.py
# file, then it's due to needing two separate types to make the typing shenanigans
# a bit easier to write. It's an unfortunate design. Originally, these types were
# merged and an adapter was used to differentiate between the async and sync versions.
# However, this proved to be difficult to provide typings for, so here we are.

from __future__ import annotations

import contextlib
import json
import logging
import re
import threading
import time
from types import TracebackType
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Tuple, Type, Union, overload
from urllib.parse import quote as urlquote
from weakref import WeakValueDictionary

from .. import utils
from ..channel import PartialMessageable
from ..errors import DiscordServerError, Forbidden, HTTPException, InvalidArgument, NotFound
from ..http import _USER_AGENT, Route
from ..message import Attachment, Message
from .async_ import BaseWebhook, _WebhookState, handle_message_parameters

__all__ = (
    "SyncWebhook",
    "SyncWebhookMessage",
)

_log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..abc import Snowflake
    from ..embeds import Embed
    from ..file import File
    from ..mentions import AllowedMentions
    from ..types.snowflake import Snowflake as SnowflakeAlias
    from ..types.webhook import Webhook as WebhookPayload

    with contextlib.suppress(ModuleNotFoundError):
        from requests import Response, Session


MISSING = utils.MISSING


class DeferredLock:
    def __init__(self, lock: threading.Lock) -> None:
        self.lock = lock
        self.delta: Optional[float] = None

    def __enter__(self):
        self.lock.acquire()
        return self

    def delay_by(self, delta: float) -> None:
        self.delta = delta

    def __exit__(
        self,
        type: Optional[Type[BaseException]],
        value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        if self.delta:
            time.sleep(self.delta)
        self.lock.release()


class WebhookAdapter:
    def __init__(self) -> None:
        self._locks: WeakValueDictionary[
            Tuple[Optional[SnowflakeAlias], Optional[str]],
            threading.Lock,
        ] = WeakValueDictionary()

    def request(
        self,
        route: Route,
        session: Session,
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
        to_send: Optional[Union[str, Dict[str, Any]]] = None
        bucket = (route.webhook_id, route.webhook_token)

        try:
            lock = self._locks[bucket]
        except KeyError:
            self._locks[bucket] = lock = threading.Lock()

        if payload is not None:
            headers["Content-Type"] = "application/json"
            to_send = utils.to_json(payload)

        if auth_token is not None:
            headers["Authorization"] = f"Bot {auth_token}"

        if reason is not None:
            headers["X-Audit-Log-Reason"] = urlquote(reason, safe="/ ")

        response: Optional[Response] = None
        data: Optional[Union[Dict[str, Any], str]] = None
        file_data: Optional[Dict[str, Any]] = None
        method = route.method
        url = route.url
        webhook_id = route.webhook_id

        with DeferredLock(lock) as lock:
            for attempt in range(5):
                for file in files:
                    file.reset(seek=attempt)

                if multipart:
                    file_data = {}
                    for p in multipart:
                        name = p["name"]
                        if name == "payload_json":
                            to_send = {"payload_json": p["value"]}
                        else:
                            file_data[name] = (p["filename"], p["value"], p["content_type"])

                try:
                    with session.request(
                        method, url, data=to_send, files=file_data, headers=headers, params=params
                    ) as response:
                        _log.debug(
                            "Webhook ID %s with %s %s has returned status code %s",
                            webhook_id,
                            method,
                            url,
                            response.status_code,
                        )
                        response.encoding = "utf-8"
                        # Compatibility with aiohttp
                        response.status = response.status_code  # type: ignore

                        data = response.text or None
                        if data and response.headers["Content-Type"] == "application/json":
                            data = json.loads(data)

                        remaining = response.headers.get("X-Ratelimit-Remaining")
                        if remaining == "0" and response.status_code != 429:
                            delta = utils.parse_ratelimit_header(response)
                            _log.debug(
                                "Webhook ID %s has been pre-emptively rate limited, waiting %.2f seconds",
                                webhook_id,
                                delta,
                            )
                            lock.delay_by(delta)

                        if 300 > response.status_code >= 200:
                            return data

                        if response.status_code == 429:
                            if not response.headers.get("Via"):
                                raise HTTPException(response, data)

                            retry_after: float = data["retry_after"]  # type: ignore
                            _log.warning(
                                "Webhook ID %s is rate limited. Retrying in %.2f seconds",
                                webhook_id,
                                retry_after,
                            )
                            time.sleep(retry_after)
                            continue

                        if response.status_code >= 500:
                            time.sleep(1 + attempt * 2)
                            continue

                        if response.status_code == 403:
                            raise Forbidden(response, data)

                        if response.status_code == 404:
                            raise NotFound(response, data)

                        raise HTTPException(response, data)

                except OSError as e:
                    if attempt < 4 and e.errno in (54, 10054):
                        time.sleep(1 + attempt * 2)
                        continue
                    raise

            if response:
                if response.status_code >= 500:
                    raise DiscordServerError(response, data)
                raise HTTPException(response, data)

            raise RuntimeError("Unreachable code in HTTP handling.")

    def delete_webhook(
        self,
        webhook_id: int,
        *,
        token: Optional[str] = None,
        session: Session,
        reason: Optional[str] = None,
    ):
        route = Route("DELETE", "/webhooks/{webhook_id}", webhook_id=webhook_id)
        return self.request(route, session, reason=reason, auth_token=token)

    def delete_webhook_with_token(
        self,
        webhook_id: int,
        token: str,
        *,
        session: Session,
        reason: Optional[str] = None,
    ):
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
        session: Session,
        reason: Optional[str] = None,
    ):
        route = Route("PATCH", "/webhooks/{webhook_id}", webhook_id=webhook_id)
        return self.request(route, session, reason=reason, payload=payload, auth_token=token)

    def edit_webhook_with_token(
        self,
        webhook_id: int,
        token: str,
        payload: Dict[str, Any],
        *,
        session: Session,
        reason: Optional[str] = None,
    ):
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
        session: Session,
        payload: Optional[Dict[str, Any]] = None,
        multipart: Optional[List[Dict[str, Any]]] = None,
        files: Optional[List[File]] = None,
        thread_id: Optional[int] = None,
        wait: bool = False,
    ):
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
        session: Session,
    ):
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
        session: Session,
        payload: Optional[Dict[str, Any]] = None,
        multipart: Optional[List[Dict[str, Any]]] = None,
        files: Optional[List[File]] = None,
        thread_id: Optional[int] = None,
    ):
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
        session: Session,
    ):
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
        session: Session,
    ):
        route = Route("GET", "/webhooks/{webhook_id}", webhook_id=webhook_id)
        return self.request(route, session=session, auth_token=token)

    def fetch_webhook_with_token(
        self,
        webhook_id: int,
        token: str,
        *,
        session: Session,
    ):
        route = Route(
            "GET",
            "/webhooks/{webhook_id}/{webhook_token}",
            webhook_id=webhook_id,
            webhook_token=token,
        )
        return self.request(route, session=session)


class _WebhookContext(threading.local):
    adapter: Optional[WebhookAdapter] = None


_context = _WebhookContext()


def _get_webhook_adapter() -> WebhookAdapter:
    if _context.adapter is None:
        _context.adapter = WebhookAdapter()
    return _context.adapter


class SyncWebhookMessage(Message):
    """Represents a message sent from your webhook.

    This allows you to edit or delete a message sent by your
    webhook.

    This inherits from :class:`nexon.Message` with changes to
    :meth:`edit` and :meth:`delete` to work.

    .. versionadded:: 2.0
    """

    _state: _WebhookState

    def edit(
        self,
        content: Optional[str] = MISSING,
        embeds: List[Embed] = MISSING,
        embed: Optional[Embed] = MISSING,
        attachments: List[Attachment] = MISSING,
        file: File = MISSING,
        files: List[File] = MISSING,
        allowed_mentions: Optional[AllowedMentions] = None,
    ) -> SyncWebhookMessage:
        """Edits the message.

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
        files: List[:class:`File`]
            A list of files to send with the content. This cannot be mixed with the
            ``file`` parameter.
        attachments: List[:class:`Attachment`]
            A list of attachments to keep in the message. To keep all existing attachments,
            pass ``message.attachments``.
        allowed_mentions: :class:`AllowedMentions`
            Controls the mentions being processed in this message.
            See :meth:`.abc.Messageable.send` for more information.

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
        :class:`SyncWebhookMessage`
            The newly edited message.
        """
        return self._state._webhook.edit_message(
            self.id,
            content=content,
            embeds=embeds,
            embed=embed,
            file=file,
            files=files,
            attachments=attachments,
            allowed_mentions=allowed_mentions,
        )

    def delete(self, *, delay: Optional[float] = None) -> None:
        """Deletes the message.

        Parameters
        ----------
        delay: Optional[:class:`float`]
            If provided, the number of seconds to wait before deleting the message.
            This blocks the thread.

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
            time.sleep(delay)
        self._state._webhook.delete_message(self.id)


class SyncWebhook(BaseWebhook):
    """Represents a synchronous Discord webhook.

    For an asynchronous counterpart, see :class:`Webhook`.

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
        self, data: WebhookPayload, session: Session, token: Optional[str] = None, state=None
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
        cls, id: int, token: str, *, session: Session = MISSING, bot_token: Optional[str] = None
    ) -> SyncWebhook:
        """Creates a partial :class:`Webhook`.

        Parameters
        ----------
        id: :class:`int`
            The ID of the webhook.
        token: :class:`str`
            The authentication token of the webhook.
        session: :class:`requests.Session`
            The session to use to send requests with. Note
            that the library does not manage the session and
            will not close it. If not given, the ``requests``
            auto session creation functions are used instead.
        bot_token: Optional[:class:`str`]
            The bot authentication token for authenticated requests
            involving the webhook.

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
        import requests

        if session is not MISSING:
            if not isinstance(session, requests.Session):
                raise TypeError(f"Expected requests.Session not {session.__class__!r}")
        else:
            session = requests  # type: ignore
        return cls(data, session, token=bot_token)

    @classmethod
    def from_url(
        cls, url: str, *, session: Session = MISSING, bot_token: Optional[str] = None
    ) -> SyncWebhook:
        """Creates a partial :class:`Webhook` from a webhook URL.

        Parameters
        ----------
        url: :class:`str`
            The URL of the webhook.
        session: :class:`requests.Session`
            The session to use to send requests with. Note
            that the library does not manage the session and
            will not close it. If not given, the ``requests``
            auto session creation functions are used instead.
        bot_token: Optional[:class:`str`]
            The bot authentication token for authenticated requests
            involving the webhook.

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
        import requests

        if session is not MISSING:
            if not isinstance(session, requests.Session):
                raise TypeError(f"Expected requests.Session not {session.__class__!r}")
        else:
            session = requests  # type: ignore
        return cls(data, session, token=bot_token)  # type: ignore

    def fetch(self, *, prefer_auth: bool = True) -> SyncWebhook:
        """Fetches the current webhook.

        This could be used to get a full webhook from a partial webhook.

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
        :class:`SyncWebhook`
            The fetched webhook.
        """
        adapter: WebhookAdapter = _get_webhook_adapter()

        if prefer_auth and self.auth_token:
            data = adapter.fetch_webhook(self.id, self.auth_token, session=self.session)
        elif self.token:
            data = adapter.fetch_webhook_with_token(self.id, self.token, session=self.session)
        else:
            raise InvalidArgument("This webhook does not have a token associated with it")

        return SyncWebhook(data, self.session, token=self.auth_token, state=self._state)

    def delete(self, *, reason: Optional[str] = None, prefer_auth: bool = True) -> None:
        """Deletes this Webhook.

        Parameters
        ----------
        reason: Optional[:class:`str`]
            The reason for deleting this webhook. Shows up on the audit log.

            .. versionadded:: 1.4
        prefer_auth: :class:`bool`
            Whether to use the bot token over the webhook token
            if available. Defaults to ``True``.

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

        adapter: WebhookAdapter = _get_webhook_adapter()

        if prefer_auth and self.auth_token:
            adapter.delete_webhook(
                self.id, token=self.auth_token, session=self.session, reason=reason
            )
        elif self.token:
            adapter.delete_webhook_with_token(
                self.id, self.token, session=self.session, reason=reason
            )

    def edit(
        self,
        *,
        reason: Optional[str] = None,
        name: Optional[str] = MISSING,
        avatar: Optional[Union[bytes, File]] = MISSING,
        channel: Optional[Snowflake] = None,
        prefer_auth: bool = True,
    ) -> SyncWebhook:
        """Edits this Webhook.

        .. versionchanged:: 2.1
            The ``avatar`` parameter now accepts :class:`File`.

        Parameters
        ----------
        name: Optional[:class:`str`]
            The webhook's new default name.
        avatar: Optional[Union[:class:`bytes`, :class:`File`]]
            A :term:`py:bytes-like object`, :class:`File` representing the webhook's new default avatar.
        channel: Optional[:class:`abc.Snowflake`]
            The webhook's new channel. This requires an authenticated webhook.
        reason: Optional[:class:`str`]
            The reason for editing this webhook. Shows up on the audit log.

            .. versionadded:: 1.4
        prefer_auth: :class:`bool`
            Whether to use the bot token over the webhook token
            if available. Defaults to ``True``.

        Raises
        ------
        HTTPException
            Editing the webhook failed.
        NotFound
            This webhook does not exist.
        InvalidArgument
            This webhook does not have a token associated with it
            or it tried editing a channel without authentication.

        Returns
        -------
        :class:`SyncWebhook`
            The newly edited webhook.
        """
        if self.token is None and self.auth_token is None:
            raise InvalidArgument("This webhook does not have a token associated with it")

        payload: Dict[str, Any] = {}
        if name is not MISSING:
            payload["name"] = str(name) if name is not None else None

        if avatar is not MISSING:
            if avatar is None:
                payload["avatar"] = avatar
            elif isinstance(avatar, bytes):
                payload["avatar"] = utils._bytes_to_base64_data(avatar)
            else:
                payload["avatar"] = utils._bytes_to_base64_data(avatar.fp.read())

        adapter: WebhookAdapter = _get_webhook_adapter()

        data: Optional[WebhookPayload] = None
        # If a channel is given, always use the authenticated endpoint
        if channel is not None:
            if self.auth_token is None:
                raise InvalidArgument("Editing channel requires authenticated webhook")

            payload["channel_id"] = channel.id
            data = adapter.edit_webhook(
                self.id, self.auth_token, payload=payload, session=self.session, reason=reason
            )

        if prefer_auth and self.auth_token:
            data = adapter.edit_webhook(
                self.id, self.auth_token, payload=payload, session=self.session, reason=reason
            )
        elif self.token:
            data = adapter.edit_webhook_with_token(
                self.id, self.token, payload=payload, session=self.session, reason=reason
            )

        if data is None:
            raise RuntimeError("Unreachable code hit: data was not assigned")

        return SyncWebhook(
            data=data, session=self.session, token=self.auth_token, state=self._state
        )

    def _create_message(self, data):
        state = _WebhookState(self, parent=self._state)
        # state may be artificial (unlikely at this point...)
        channel = self.channel or PartialMessageable(state=self._state, id=int(data["channel_id"]))  # type: ignore
        # state is artificial
        return SyncWebhookMessage(data=data, state=state, channel=channel)  # type: ignore

    @overload
    def send(
        self,
        content: str = MISSING,
        *,
        username: str = MISSING,
        avatar_url: Any = MISSING,
        tts: bool = MISSING,
        file: File = MISSING,
        files: List[File] = MISSING,
        embed: Embed = MISSING,
        embeds: List[Embed] = MISSING,
        allowed_mentions: AllowedMentions = MISSING,
        wait: Literal[True],
        thread_name: Optional[str] = None,
    ) -> SyncWebhookMessage: ...

    @overload
    def send(
        self,
        content: str = MISSING,
        *,
        username: str = MISSING,
        avatar_url: Any = MISSING,
        tts: bool = MISSING,
        file: File = MISSING,
        files: List[File] = MISSING,
        embed: Embed = MISSING,
        embeds: List[Embed] = MISSING,
        allowed_mentions: AllowedMentions = MISSING,
        wait: Literal[False] = ...,
        thread_name: Optional[str] = None,
    ) -> None: ...

    def send(
        self,
        content: str = MISSING,
        *,
        username: str = MISSING,
        avatar_url: Any = MISSING,
        tts: bool = False,
        file: File = MISSING,
        files: List[File] = MISSING,
        embed: Embed = MISSING,
        embeds: List[Embed] = MISSING,
        allowed_mentions: AllowedMentions = MISSING,
        thread: Snowflake = MISSING,
        wait: bool = False,
        thread_name: Optional[str] = None,
    ) -> Optional[SyncWebhookMessage]:
        """Sends a message using the webhook.

        The content must be a type that can convert to a string through ``str(content)``.

        To upload a single file, the ``file`` parameter should be used with a
        single :class:`File` object.

        If the ``embed`` parameter is provided, it must be of type :class:`Embed` and
        it must be a rich embed type. You cannot mix the ``embed`` parameter with the
        ``embeds`` parameter, which must be a :class:`list` of :class:`Embed` objects to send.

        Parameters
        ----------
        content: :class:`str`
            The content of the message to send.
        wait: :class:`bool`
            Whether the server should wait before sending a response. This essentially
            means that the return type of this function changes from ``None`` to
            a :class:`WebhookMessage` if set to ``True``.
        username: :class:`str`
            The username to send with this message. If no username is provided
            then the default username for the webhook is used.
        avatar_url: :class:`str`
            The avatar URL to send with this message. If no avatar URL is provided
            then the default avatar for the webhook is used. If this is not a
            string then it is explicitly cast using ``str``.
        tts: :class:`bool`
            Indicates if the message should be sent using text-to-speech.
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
        thread: :class:`~nexon.abc.Snowflake`
            The thread to send this message to.

            .. versionadded:: 2.0

        thread_name:
            Name of thread to create (requires the webhook channel to be a forum or media channel).

            .. versionadded:: 3.0

        Raises
        ------
        HTTPException
            Sending the message failed.
        NotFound
            This webhook was not found.
        Forbidden
            The authorization token for the webhook is incorrect.
        InvalidArgument
            You specified both ``embed`` and ``embeds`` or ``file`` and ``files``.
        ValueError
            The length of ``embeds`` was invalid.
        InvalidArgument
            There was no token associated with this webhook.

        Returns
        -------
        Optional[:class:`SyncWebhookMessage`]
            If ``wait`` is ``True`` then the message that was sent, otherwise ``None``.
        """

        if self.token is None:
            raise InvalidArgument("This webhook does not have a token associated with it")

        previous_mentions: Optional[AllowedMentions] = getattr(
            self._state, "allowed_mentions", None
        )

        params = handle_message_parameters(
            content=content,
            username=username,
            avatar_url=avatar_url,
            tts=tts,
            file=file,
            files=files,
            embed=embed,
            embeds=embeds,
            allowed_mentions=allowed_mentions,
            previous_allowed_mentions=previous_mentions,
            thread_name=thread_name,
        )
        adapter: WebhookAdapter = _get_webhook_adapter()

        data = adapter.execute_webhook(
            self.id,
            self.token,
            session=self.session,
            payload=params.payload,
            multipart=params.multipart,
            files=params.files,
            thread_id=thread.id if thread else None,
            wait=wait,
        )
        if wait:
            return self._create_message(data)
        return None

    def fetch_message(self, id: int, /) -> SyncWebhookMessage:
        """Retrieves a single :class:`~nexon.SyncWebhookMessage` owned by this webhook.

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
        :class:`~nexon.SyncWebhookMessage`
            The message asked for.
        """

        if self.token is None:
            raise InvalidArgument("This webhook does not have a token associated with it")

        adapter: WebhookAdapter = _get_webhook_adapter()
        data = adapter.get_webhook_message(
            self.id,
            self.token,
            id,
            session=self.session,
        )
        return self._create_message(data)

    def edit_message(
        self,
        message_id: int,
        *,
        content: Optional[str] = MISSING,
        embeds: List[Embed] = MISSING,
        embed: Optional[Embed] = MISSING,
        file: File = MISSING,
        files: List[File] = MISSING,
        attachments: List[Attachment] = MISSING,
        allowed_mentions: Optional[AllowedMentions] = None,
        thread: Snowflake = MISSING,
    ) -> SyncWebhookMessage:
        """Edits a message owned by this webhook.

        This is a lower level interface to :meth:`WebhookMessage.edit` in case
        you only have an ID.

        .. versionadded:: 1.6

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
        files: List[:class:`File`]
            A list of files to send with the content. This cannot be mixed with the
            ``file`` parameter.
        attachments: List[:class:`Attachment`]
            A list of attachments to keep in the message.
        allowed_mentions: :class:`AllowedMentions`
            Controls the mentions being processed in this message.
            See :meth:`.abc.Messageable.send` for more information.
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
            There was no token associated with this webhook.
        """

        if self.token is None:
            raise InvalidArgument("This webhook does not have a token associated with it")

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
            allowed_mentions=allowed_mentions,
            previous_allowed_mentions=previous_mentions,
        )
        adapter: WebhookAdapter = _get_webhook_adapter()
        thread_id: Optional[int] = None
        if thread is not MISSING:
            thread_id = thread.id
        data = adapter.edit_webhook_message(
            self.id,
            self.token,
            message_id,
            session=self.session,
            payload=params.payload,
            multipart=params.multipart,
            files=params.files,
            thread_id=thread_id,
        )
        return self._create_message(data)

    def delete_message(self, message_id: int, /) -> None:
        """Deletes a message owned by this webhook.

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

        adapter: WebhookAdapter = _get_webhook_adapter()
        adapter.delete_webhook_message(
            self.id,
            self.token,
            message_id,
            session=self.session,
        )
