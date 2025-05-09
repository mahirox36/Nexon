from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Optional

from ..types.oauth2 import Token
from ..utils import MISSING
from .. import utils

class OAuth2Token:
    def __init__(self, token_data: Token) -> None:
        self._token_data: Token = token_data
        self._access_token: str = token_data["access_token"]
        self._token_type: str = token_data.get("token_type", "Bearer")
        self._refresh_token: Optional[str] = token_data.get("refresh_token")
        self._expires_at: Optional[datetime] = None
        
        if "expires_in" in token_data:
            self._expires_at = utils.utcnow() + timedelta(seconds=token_data["expires_in"])

    @property
    def access_token(self) -> str:
        return self._access_token

    @property
    def token_type(self) -> str:
        return self._token_type

    @property 
    def refresh_token(self) -> Optional[str]:
        return self._refresh_token

    @property
    def expired(self) -> bool:
        if self._expires_at is None:
            return False
        return utils.utcnow() >= self._expires_at

    def get_auth_header(self) -> Dict[str, str]:
        return {"Authorization": f"{self.token_type} {self.access_token}"}

    def to_dict(self) -> Token:
        return self._token_data