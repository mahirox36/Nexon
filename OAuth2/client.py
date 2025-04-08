from __future__ import annotations

from typing import Any, Dict, List, Optional, TypeVar, Union
from urllib.parse import urlencode

from aiohttp import BaseConnector, BasicAuth
from cachetools import TTLCache

from ..http import HTTPClient, Route
from ..types.oauth2 import Token, Connection, Guild, GuildMember, User
from ..types.snowflake import Snowflake
from .token import OAuth2Token

DISCORD_API_URL = "https://discord.com/api/v10"
OAUTH2_CLIENT_ID = ""
OAUTH2_CLIENT_SECRET = ""
OAUTH2_REDIRECT_URI = ""

class OAuth2Client:
    """Handles OAuth2 authentication flow and API requests
    
    Parameters
    -----------
    client_id: :class:`str`
        The client ID provided by Discord
    client_secret: :class:`str`
        The client secret provided by Discord
    redirect_uri: :class:`str`
        The redirect URI for the OAuth2 flow
    scopes: List[:class:`str`]
        The OAuth2 scopes to request
    connector: Optional[:class:`aiohttp.BaseConnector`]
        The connector to use for the client session.
    max_global_requests: :class:`int`
        Maximum amount of requests per second per authorization.
    time_offset: :class:`float`
        Time offset in seconds for rate limit calculations.
    proxy: Optional[:class:`str`]
        Optional proxy URL to use for requests.
    proxy_auth: Optional[:class:`aiohttp.BasicAuth`]
        Optional proxy authentication.
    assume_unsync_clock: :class:`bool`
        Whether to assume the system clock is unsynced.
    """
    
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scopes: List[str],
        *,
        connector: Optional[BaseConnector] = None,
        max_global_requests: int = 50,
        time_offset: float = 0.0,
        proxy: Optional[str] = None,
        proxy_auth: Optional[BasicAuth] = None,
        assume_unsync_clock: bool = False,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scopes = scopes
        
        # Initialize caches with 1 hour TTL
        self._user_cache = TTLCache(maxsize=100, ttl=3600)
        self._connections_cache = TTLCache(maxsize=100, ttl=3600)
        self._guilds_cache = TTLCache(maxsize=100, ttl=3600)
        self._guild_members_cache = TTLCache(maxsize=1000, ttl=3600)
        
        def dispatch(event: str, *args: Any) -> None:
            pass
            
        self.http = HTTPClient(
            connector=connector,
            max_global_requests=max_global_requests,
            time_offset=time_offset,
            proxy=proxy,
            proxy_auth=proxy_auth,
            assume_unsync_clock=assume_unsync_clock,
            dispatch=dispatch,
        )

    def get_authorize_url(self, state: Optional[str] = None, **kwargs) -> str:
        """Gets the OAuth2 authorization URL
        
        Parameters
        -----------
        state: Optional[:class:`str`]
            The state to include in the auth request
        **kwargs
            Additional query parameters to include
        """
        params = {
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'response_type': 'code',
            'scope': ' '.join(self.scopes)
        }
        
        if state:
            params['state'] = state
            
        params.update(kwargs)
        
        return f"https://discord.com/oauth2/authorize?{urlencode(params)}"

    async def get_access_token(self, code: str) -> OAuth2Token:
        """Gets an access token using an authorization code
        
        Parameters
        -----------
        code: :class:`str`
            The authorization code from OAuth2 redirect
        """
        payload = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': self.redirect_uri
        }
        
        route = Route('POST', '/oauth2/token')
        token_data = await self.http.request(route, data=payload)
        return OAuth2Token(token_data)

    async def refresh_token(self, refresh_token: str) -> OAuth2Token:
        """Refreshes an access token using a refresh token
        
        Parameters
        -----------
        refresh_token: :class:`str`
            The refresh token to use
        """
        payload = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token
        }
        
        route = Route('POST', '/oauth2/token')
        token_data = await self.http.request(route, data=payload)
        return OAuth2Token(token_data)

    async def revoke_token(self, token: str) -> None:
        """Revokes an access token or refresh token
        
        Parameters
        -----------
        token: :class:`str`
            The token to revoke
        """
        payload = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'token': token
        }
        
        route = Route('POST', '/oauth2/token/revoke')
        await self.http.request(route, data=payload)

    async def fetch_user(self, token: OAuth2Token) -> User:
        """Fetches the authenticated user's info
        
        Parameters
        -----------
        token: :class:`OAuth2Token`
            The user's access token
        """
        cache_key = token.access_token
        if cache_key in self._user_cache:
            return self._user_cache[cache_key]
            
        route = Route('GET', '/users/@me')
        data = await self.http.request(route, headers=token.get_auth_header())
        
        self._user_cache[cache_key] = data
        return data

    async def fetch_connections(self, token: OAuth2Token) -> List[Connection]:
        """Fetches the authenticated user's connections
        
        Parameters
        -----------
        token: :class:`OAuth2Token`
            The user's access token
        """
        cache_key = token.access_token
        if cache_key in self._connections_cache:
            return self._connections_cache[cache_key]
            
        route = Route('GET', '/users/@me/connections')
        data = await self.http.request(route, headers=token.get_auth_header())
        
        self._connections_cache[cache_key] = data
        return data

    async def fetch_guilds(self, token: OAuth2Token) -> List[Guild]:
        """Fetches the authenticated user's guilds
        
        Parameters
        -----------
        token: :class:`OAuth2Token`
            The user's access token
        """
        cache_key = token.access_token
        if cache_key in self._guilds_cache:
            return self._guilds_cache[cache_key]
            
        route = Route('GET', '/users/@me/guilds')
        data = await self.http.request(route, headers=token.get_auth_header())
        
        self._guilds_cache[cache_key] = data
        return data

    async def fetch_guild_member(
        self, 
        token: OAuth2Token,
        guild_id: Snowflake
    ) -> GuildMember:
        """Fetches the authenticated user's member info for a guild
        
        Parameters
        -----------
        token: :class:`OAuth2Token`
            The user's access token
        guild_id: :class:`Snowflake`
            The ID of the guild
        """
        cache_key = (token.access_token, guild_id)
        if cache_key in self._guild_members_cache:
            return self._guild_members_cache[cache_key]
            
        route = Route('GET', f'/users/@me/guilds/{guild_id}/member')
        data = await self.http.request(route, headers=token.get_auth_header())
        
        self._guild_members_cache[cache_key] = data
        return data

    async def join_guild(
        self,
        token: OAuth2Token,
        guild_id: Snowflake,
        user_id: Snowflake,
        **fields
    ) -> GuildMember:
        """Adds the user to a guild
        
        Parameters
        -----------
        token: :class:`OAuth2Token`
            The user's access token
        guild_id: :class:`Snowflake` 
            The ID of the guild to join
        user_id: :class:`Snowflake`
            The ID of the user to add
        **fields
            Additional fields to pass to the request
        """
        route = Route('PUT', f'/guilds/{guild_id}/members/{user_id}')
        data = await self.http.request(
            route,
            headers=token.get_auth_header(),
            json={'access_token': token.access_token, **fields}
        )
        return data