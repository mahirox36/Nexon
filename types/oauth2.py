from __future__ import annotations

from typing import TypedDict, List, Optional
from typing_extensions import NotRequired

from .snowflake import Snowflake

class Token(TypedDict):
    access_token: str
    token_type: str
    expires_in: NotRequired[int]
    refresh_token: NotRequired[str]

class Connection(TypedDict):
    id: str
    name: str
    type: str
    revoked: bool
    verified: bool
    friend_sync: bool
    show_activity: bool
    visibility: int

class User(TypedDict):
    id: Snowflake
    username: str
    discriminator: str
    avatar: Optional[str]
    bot: NotRequired[bool]
    system: NotRequired[bool]
    mfa_enabled: NotRequired[bool]
    locale: NotRequired[str]
    verified: NotRequired[bool]
    email: NotRequired[str]
    flags: NotRequired[int]
    premium_type: NotRequired[int]
    public_flags: NotRequired[int]

class Guild(TypedDict):
    id: Snowflake
    name: str
    icon: Optional[str]
    owner: bool
    permissions: str
    features: List[str]

class GuildMember(TypedDict):
    roles: List[Snowflake]
    joined_at: str
    deaf: bool
    mute: bool
    flags: int
    pending: NotRequired[bool]
    nick: NotRequired[str]

# OAuth2 Scopes
class OAuth2Scope:
    """OAuth2 scopes that can be requested"""
    ACTIVITIES_READ = "activities.read"
    ACTIVITIES_WRITE = "activities.write"
    APPLICATIONS_BUILDS_READ = "applications.builds.read"
    APPLICATIONS_BUILDS_UPLOAD = "applications.builds.upload"
    APPLICATIONS_COMMANDS = "applications.commands"
    APPLICATIONS_COMMANDS_UPDATE = "applications.commands.update"
    APPLICATIONS_COMMANDS_PERMISSIONS_UPDATE = "applications.commands.permissions.update"
    APPLICATIONS_ENTITLEMENTS = "applications.entitlements"
    APPLICATIONS_STORE_UPDATE = "applications.store.update"
    BOT = "bot"
    CONNECTIONS = "connections"
    DM_CHANNELS_READ = "dm_channels.read"
    EMAIL = "email"
    GDM_JOIN = "gdm.join"
    GUILDS = "guilds"
    GUILDS_JOIN = "guilds.join"
    GUILDS_MEMBERS_READ = "guilds.members.read"
    IDENTIFY = "identify"
    MESSAGES_READ = "messages.read"
    RELATIONSHIPS_READ = "relationships.read"
    ROLE_CONNECTIONS_WRITE = "role_connections.write"
    RPC = "rpc"
    RPC_ACTIVITIES_WRITE = "rpc.activities.write"
    RPC_NOTIFICATIONS_READ = "rpc.notifications.read"
    RPC_VOICE_READ = "rpc.voice.read"
    RPC_VOICE_WRITE = "rpc.voice.write"
    VOICE = "voice"
    WEBHOOK_INCOMING = "webhook.incoming"