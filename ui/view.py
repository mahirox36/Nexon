# SPDX-License-Identifier: MIT

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
import traceback
from functools import partial
from itertools import groupby
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Dict,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
)

from typing_extensions import Self

from ..components import (
    ActionRow as ActionRowComponent,
    Button as ButtonComponent,
    Component,
    SelectMenu as SelectComponent,
    TextInput as TextComponent,
    _component_factory,
)
from .item import Item, ItemCallbackType

__all__ = ("View",)

if TYPE_CHECKING:
    from ..interactions import ClientT, Interaction
    from ..message import Message
    from ..state import ConnectionState
    from ..types.components import ActionRow as ActionRowPayload, Component as ComponentPayload

_log = logging.getLogger(__name__)


def _walk_all_components(components: List[Component]) -> Iterator[Component]:
    for item in components:
        if isinstance(item, ActionRowComponent):
            yield from item.children
        else:
            yield item


def _component_to_item(component: Component) -> Item:
    if isinstance(component, ButtonComponent):
        from .button import Button

        return Button.from_component(component)
    if isinstance(component, SelectComponent):
        from .select import Select

        return Select.from_component(component)
    if isinstance(component, TextComponent):
        from .text_input import TextInput

        return TextInput.from_component(component)
    return Item.from_component(component)


class _ViewWeights:
    __slots__ = ("weights",)

    def __init__(self, children: List[Item]) -> None:
        self.weights: List[int] = [0, 0, 0, 0, 0]

        key: Callable[[Item[Any]], int] = lambda i: sys.maxsize if i.row is None else i.row
        children = sorted(children, key=key)
        for _, group in groupby(children, key=key):
            for item in group:
                self.add_item(item)

    def find_open_space(self, item: Item) -> int:
        for index, weight in enumerate(self.weights):
            if weight + item.width <= 5:
                return index

        raise ValueError("Could not find open space for item")

    def add_item(self, item: Item) -> None:
        if item.row is not None:
            total = self.weights[item.row] + item.width
            if total > 5:
                raise ValueError(f"item would not fit at row {item.row} ({total} > 5 width)")
            self.weights[item.row] = total
            item._rendered_row = item.row
        else:
            index = self.find_open_space(item)
            self.weights[index] += item.width
            item._rendered_row = index

    def remove_item(self, item: Item) -> None:
        if item._rendered_row is not None:
            self.weights[item._rendered_row] -= item.width
            item._rendered_row = None

    def clear(self) -> None:
        self.weights = [0, 0, 0, 0, 0]


class View:
    """Represents a UI view.

    This object must be inherited to create a UI within Discord.

    .. versionadded:: 2.0

    Parameters
    ----------
    timeout: Optional[:class:`float`]
        Timeout in seconds from last interaction with the UI before no longer accepting input.
        If ``None`` then there is no timeout.
    auto_defer: :class:`bool` = True
        Whether or not to automatically defer the component interaction when the callback
        completes without responding to the interaction. Set this to ``False`` if you want to
        handle view interactions outside of the callback.

    Attributes
    ----------
    timeout: Optional[:class:`float`]
        Timeout from last interaction with the UI before no longer accepting input.
        If ``None`` then there is no timeout.
    children: List[:class:`Item`]
        The list of children attached to this view.
    auto_defer: :class:`bool` = True
        Whether or not to automatically defer the component interaction when the callback
        completes without responding to the interaction. Set this to ``False`` if you want to
        handle view interactions outside of the callback.
    prevent_update: :class:`bool` = True
        This option only affects persistent views.
        Whether or not to store the view separately for each message.
        The stored views are not automatically cleared, and can cause issues if
        you run the bot continously for long periods of time if views are not properly stopped.
        Setting this to False will force the client to find a persistent view added with
        `Bot.add_view` and not store the view separately.
    """

    __discord_ui_view__: ClassVar[bool] = True
    __view_children_items__: ClassVar[List[ItemCallbackType]] = []

    def __init_subclass__(cls) -> None:
        children: List[ItemCallbackType] = []
        for base in reversed(cls.__mro__):
            children.extend(
                member
                for member in base.__dict__.values()
                if hasattr(member, "__discord_ui_model_type__")
            )

        if len(children) > 25:
            raise TypeError("View cannot have more than 25 children")

        cls.__view_children_items__ = children

    def __init__(
        self,
        *,
        timeout: Optional[float] = 180.0,
        auto_defer: bool = True,
        prevent_update: bool = True,
    ) -> None:
        self.timeout = timeout
        self.auto_defer = auto_defer
        self.prevent_update = True if timeout else prevent_update
        self.children: List[Item] = []
        for func in self.__view_children_items__:
            item: Item = func.__discord_ui_model_type__(**func.__discord_ui_model_kwargs__)
            item.callback = partial(func, self, item)  # type: ignore
            item._view = self
            setattr(self, func.__name__, item)
            self.children.append(item)

        self.__weights = _ViewWeights(self.children)
        loop = asyncio.get_running_loop()
        self.id: str = os.urandom(16).hex()
        self.__cancel_callback: Optional[Callable[[View], None]] = None
        self.__timeout_expiry: Optional[float] = None
        self.__timeout_task: Optional[asyncio.Task[None]] = None
        self.__background_tasks: Set[asyncio.Task[None]] = set()
        self.__stopped: asyncio.Future[bool] = loop.create_future()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} timeout={self.timeout} children={len(self.children)}>"

    async def __timeout_task_impl(self) -> None:
        while True:
            # Guard just in case someone changes the value of the timeout at runtime
            if self.timeout is None:
                return None

            if self.__timeout_expiry is None:
                return self._dispatch_timeout()

            # Check if we've elapsed our currently set timeout
            now = time.monotonic()
            if now >= self.__timeout_expiry:
                return self._dispatch_timeout()

            # Wait N seconds to see if timeout data has been refreshed
            await asyncio.sleep(self.__timeout_expiry - now)

    def to_components(self) -> List[ActionRowPayload]:
        def key(item: Item) -> int:
            return item._rendered_row or 0

        children = sorted(self.children, key=key)
        components: List[ActionRowPayload] = []
        for _, group in groupby(children, key=key):
            children = [item.to_component_dict() for item in group]
            if not children:
                continue

            components.append(
                {
                    "type": 1,
                    "components": children,
                }
            )

        return components

    @classmethod
    def from_message(cls, message: Message, /, *, timeout: Optional[float] = 180.0) -> View:
        """Converts a message's components into a :class:`View`.

        The :attr:`.Message.components` of a message are read-only
        and separate types from those in the ``nexon.ui`` namespace.
        In order to modify and edit message components they must be
        converted into a :class:`View` first.

        Parameters
        ----------
        message: :class:`nexon.Message`
            The message with components to convert into a view.
        timeout: Optional[:class:`float`]
            The timeout of the converted view.

        Returns
        -------
        :class:`View`
            The converted view. This always returns a :class:`View` and not
            one of its subclasses.
        """
        view = View(timeout=timeout)
        for component in _walk_all_components(message.components):
            view.add_item(_component_to_item(component))
        return view

    @property
    def _expires_at(self) -> Optional[float]:
        """The monotonic time this view times out at.

        Returns
        -------
        Optional[float]
            When this view times out.

            None if no timeout is set.
        """
        return self.__timeout_expiry

    def add_item(self, item: Item[Self]) -> None:
        """Adds an item to the view.

        Parameters
        ----------
        item: :class:`Item`
            The item to add to the view.

        Raises
        ------
        TypeError
            An :class:`Item` was not passed.
        ValueError
            Maximum number of children has been exceeded (25)
            or the row the item is trying to be added to is full.
        """

        if len(self.children) > 25:
            raise ValueError("Maximum number of children exceeded")

        if not isinstance(item, Item):
            raise TypeError(f"Expected Item not {item.__class__!r}")

        self.__weights.add_item(item)

        item._view = self
        self.children.append(item)

    def remove_item(self, item: Item) -> None:
        """Removes an item from the view.

        Parameters
        ----------
        item: :class:`Item`
            The item to remove from the view.
        """

        try:
            self.children.remove(item)
        except ValueError:
            pass
        else:
            self.__weights.remove_item(item)

    def clear_items(self) -> None:
        """Removes all items from the view."""
        self.children.clear()
        self.__weights.clear()

    async def interaction_check(self, interaction: Interaction) -> bool:
        """|coro|

        A callback that is called when an interaction happens within the view
        that checks whether the view should process item callbacks for the interaction.

        This is useful to override if, for example, you want to ensure that the
        interaction author is a given user.

        The default implementation of this returns ``True``.

        .. note::

            If an exception occurs within the body then the check
            is considered a failure and :meth:`on_error` is called.

        Parameters
        ----------
        interaction: :class:`~nexon.Interaction`
            The interaction that occurred.

        Returns
        -------
        :class:`bool`
            Whether the view children's callbacks should be called.
        """
        return True

    async def on_timeout(self) -> None:
        """|coro|

        A callback that is called when a view's timeout elapses without being explicitly stopped.
        """

    async def on_error(self, error: Exception, item: Item, interaction: Interaction) -> None:
        """|coro|

        A callback that is called when an item's callback or :meth:`interaction_check`
        fails with an error.

        The default implementation prints the traceback to stderr.

        Parameters
        ----------
        error: :class:`Exception`
            The exception that was raised.
        item: :class:`Item`
            The item that failed the dispatch.
        interaction: :class:`~nexon.Interaction`
            The interaction that led to the failure.
        """
        print(f"Ignoring exception in view {self} for item {item}:", file=sys.stderr)  # noqa: T201
        traceback.print_exception(error.__class__, error, error.__traceback__, file=sys.stderr)

    async def _scheduled_task(self, item: Item, interaction: Interaction):
        try:
            if self.timeout:
                self.__timeout_expiry = time.monotonic() + self.timeout

            allow = await self.interaction_check(interaction)
            if not allow:
                return None

            await item.callback(interaction)
            if (
                not interaction.response._responded
                and not interaction.is_expired()
                and self.auto_defer
            ):
                await interaction.response.defer()
        except Exception as e:
            return await self.on_error(e, item, interaction)

    def _start_listening_from_store(self, store: ViewStore) -> None:
        self.__cancel_callback = partial(store.remove_view)
        if self.timeout:
            loop = asyncio.get_running_loop()
            if self.__timeout_task is not None:
                self.__timeout_task.cancel()

            self.__timeout_expiry = time.monotonic() + self.timeout
            self.__timeout_task = loop.create_task(self.__timeout_task_impl())

    def _dispatch_timeout(self) -> None:
        if self.__stopped.done():
            return

        task = asyncio.create_task(self.on_timeout(), name=f"discord-ui-view-timeout-{self.id}")
        self.__background_tasks.add(task)
        task.add_done_callback(self.__background_tasks.discard)
        self.__stopped.set_result(True)

    def _dispatch_item(self, item: Item, interaction: Interaction) -> None:
        if self.__stopped.done():
            return

        task = asyncio.create_task(
            self._scheduled_task(item, interaction), name=f"discord-ui-view-dispatch-{self.id}"
        )
        self.__background_tasks.add(task)
        task.add_done_callback(self.__background_tasks.discard)

    def refresh(self, components: List[Component]) -> None:
        old_state: Dict[str, Item[Any]] = {
            item.custom_id: item for item in self.children if item.is_dispatchable()  # type: ignore
        }

        for component in _walk_all_components(components):
            custom_id = getattr(component, "custom_id", None)
            if custom_id is None:
                continue

            try:
                older = old_state[custom_id]
            except KeyError:
                _log.debug(
                    "View interaction referenced an unknown item custom_id %s. Discarding",
                    custom_id,
                )
                continue
            else:
                older.refresh_component(component)

    def stop(self) -> None:
        """Stops listening to interaction events from this view.

        This operation cannot be undone.
        """
        if not self.__stopped.done():
            self.__stopped.set_result(False)

        self.__timeout_expiry = None
        if self.__timeout_task is not None:
            self.__timeout_task.cancel()
            self.__timeout_task = None

        if self.__cancel_callback:
            self.__cancel_callback(self)
            self.__cancel_callback = None

    def is_finished(self) -> bool:
        """:class:`bool`: Whether the view has finished interacting."""
        return self.__stopped.done()

    def is_dispatching(self) -> bool:
        """:class:`bool`: Whether the view has been added for dispatching purposes."""
        return self.__cancel_callback is not None

    def is_persistent(self) -> bool:
        """:class:`bool`: Whether the view is set up as persistent.

        A persistent view has all their components with a set ``custom_id`` and
        a :attr:`timeout` set to ``None``.
        """
        return self.timeout is None and all(item.is_persistent() for item in self.children)

    async def wait(self) -> bool:
        """Waits until the view has finished interacting.

        A view is considered finished when :meth:`stop` is called
        or it times out.

        Returns
        -------
        :class:`bool`
            If ``True``, then the view timed out. If ``False`` then
            the view finished normally.
        """
        return await self.__stopped


class ViewStore:
    def __init__(self, state: ConnectionState) -> None:
        self._views: Dict[Tuple[int, Optional[int], str], Tuple[View, Item]] = {}
        """(component_type, message_id, custom_id): (View, Item)"""
        self._synced_message_views: Dict[int, View] = {}
        """message_id: View"""
        self._state: ConnectionState = state

    def all_views(self) -> List[View]:
        # Create a unique list of views, as _views stores the same view multiple times,
        # one for each dispatchable item.
        views = {view.id: view for view, _ in self._views.values()}
        return list(views.values())

    def views(self, persistent: bool = True) -> List[View]:
        views = self.all_views()
        return [v for v in views if v.is_persistent() ^ (not persistent)]

    def __verify_integrity(self) -> None:
        to_remove: List[Tuple[int, Optional[int], str]] = []
        for k, (view, _) in self._views.items():
            if view.is_finished():
                to_remove.append(k)

        for k in to_remove:
            del self._views[k]

    def add_view(self, view: View, message_id: Optional[int] = None) -> None:
        self.__verify_integrity()

        view._start_listening_from_store(self)
        for item in view.children:
            if item.is_dispatchable():
                self._views[(item.type.value, message_id, item.custom_id)] = (view, item)  # type: ignore

        if message_id is not None:
            self._synced_message_views[message_id] = view

    def remove_view(self, view: View, message_id: Optional[int] = None) -> None:
        for item in view.children:
            if item.is_dispatchable():
                self._views.pop((item.type.value, message_id, item.custom_id), None)  # type: ignore

        for key, value in self._synced_message_views.items():
            if value.id == view.id:
                del self._synced_message_views[key]
                break

    def dispatch(
        self, component_type: int, custom_id: str, interaction: Interaction[ClientT]
    ) -> None:
        self.__verify_integrity()
        message_id: Optional[int] = interaction.message and interaction.message.id
        key = (component_type, message_id, custom_id)
        # Fallback to None message_id searches in case a persistent view
        # was added without an associated message_id
        value = self._views.get(key) or self._views.get((component_type, None, custom_id))
        if value is None:
            return

        view, item = value
        item.refresh_state(interaction.data, interaction._state, interaction.guild)  # type: ignore
        view._dispatch_item(item, interaction)

    def is_message_tracked(self, message_id: int) -> bool:
        return message_id in self._synced_message_views

    def remove_message_tracking(self, message_id: int) -> Optional[View]:
        return self._synced_message_views.pop(message_id, None)

    def update_from_message(self, message_id: int, components: List[ComponentPayload]) -> None:
        # pre-req: is_message_tracked == true
        view = self._synced_message_views[message_id]
        view.refresh([_component_factory(d) for d in components])
