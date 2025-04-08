from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, Optional, Dict

from cachetools import TTLCache

from .token import OAuth2Token
from .client import OAuth2Client

class OAuth2Session:
    """Manages OAuth2 tokens and session state
    
    Parameters
    -----------
    client: :class:`OAuth2Client`
        The OAuth2 client to use
    token: Optional[:class:`OAuth2Token`]
        Initial access token to use
    """
    
    def __init__(
        self,
        client: OAuth2Client,
        token: Optional[OAuth2Token] = None,
        auto_refresh: bool = True
    ) -> None:
        self.client = client
        self.token = token
        self.auto_refresh = auto_refresh
        
        # Cache for token refreshing to prevent multiple simultaneous refreshes
        self._refresh_lock = asyncio.Lock()
        self._refresh_cache: Dict[str, asyncio.Event] = {}

    async def _ensure_token(self) -> OAuth2Token:
        """Ensures we have a valid token, refreshing if needed"""
        if not self.token:
            raise RuntimeError("No token available")
            
        if not self.auto_refresh:
            return self.token
            
        # Check if token needs refresh
        if self.token.expired:
            async with self._refresh_lock:
                # Check if refresh is already in progress
                refresh_event = self._refresh_cache.get(self.token.access_token)
                if refresh_event:
                    # Wait for refresh to complete
                    await refresh_event.wait()
                    return self.token
                    
                # Start new refresh
                refresh_event = asyncio.Event()
                self._refresh_cache[self.token.access_token] = refresh_event
                
                try:
                    if not self.token.refresh_token:
                        raise RuntimeError("No refresh token available")
                        
                    self.token = await self.client.refresh_token(self.token.refresh_token)
                finally:
                    refresh_event.set()
                    self._refresh_cache.pop(self.token.access_token, None)
                    
        return self.token

    async def fetch_user(self):
        """Fetches the authenticated user's info"""
        token = await self._ensure_token()
        return await self.client.fetch_user(token)
        
    async def fetch_connections(self):
        """Fetches the authenticated user's connections"""
        token = await self._ensure_token()
        return await self.client.fetch_connections(token)
        
    async def fetch_guilds(self):
        """Fetches the authenticated user's guilds"""
        token = await self._ensure_token()
        return await self.client.fetch_guilds(token)
        
    async def fetch_guild_member(self, guild_id):
        """Fetches the authenticated user's member info for a guild"""
        token = await self._ensure_token()
        return await self.client.fetch_guild_member(token, guild_id)
        
    async def join_guild(self, guild_id, user_id, **fields):
        """Adds the user to a guild"""
        token = await self._ensure_token()
        return await self.client.join_guild(token, guild_id, user_id, **fields)
        
    async def revoke(self):
        """Revokes the current access token"""
        if self.token:
            await self.client.revoke_token(self.token.access_token)
            self.token = None