"""
nexon.dataManager
~~~~~~~~~~~~~~~~

A unified data management system for handling JSON data storage.

:copyright: (c) 2024 Mahirox36
:license: MIT, see LICENSE for more details.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from collections import OrderedDict
from time import time
from typing import TYPE_CHECKING, Any, Dict, List, NoReturn, Optional, Union

if TYPE_CHECKING:
    from typing_extensions import Self

__all__ = (
    "DataManager",
)


class DataManager:
    """A unified data management system for handling JSON data storage with enhanced features.

    This class provides persistent storage of structured data with focus on Discord bot-related patterns.

    .. versionadded:: Nexon 0.2.1

    Parameters
    -----------
    name: :class:`str`
        The name of the data store
    server_id: Optional[:class:`int`]
        Server ID for guild-specific data. If provided, data will be stored in the Guilds directory
    file_name: :class:`str`
        Name of the JSON file without extension. Defaults to "data"
    subfolder: Optional[:class:`str`]
        Optional subfolder path within the entity type folder
    default: Union[:class:`dict`, :class:`list`, ``None``]
        Default data structure if no existing data is found
    auto_save: :class:`bool`
        Whether to automatically save on context exit
    entity_type: :class:`str` 
        Type of entity the data belongs to. Defaults to "Features"
    add_name_folder: :class:`bool`
        Whether to include name as a subfolder in the path

    Attributes
    -----------
    path: :class:`pathlib.Path`
        The path to the directory containing the data file
    file: :class:`pathlib.Path`
        The full path to the JSON file
    data: Union[:class:`dict`, :class:`list`, Any]
        The loaded data structure
    auto_save: :class:`bool`
        Whether auto-save is enabled for this instance
    """
    
    _cache: Dict[str, Any] = {}
    _cache_timestamps: Dict[str, float] = {}
    _cache_limit: int = 2000  # Max number of items in cache
    _cache_ttl: int = 2000    # Time-to-live for cache items in seconds

    def __init__(
        self,
        *,
        name: str,
        server_id: Optional[int] = None,
        file_name: str = "data",
        subfolder: Optional[str] = None,
        default: Union[Dict, List, None] = None,
        auto_save: bool = True,
        entity_type: str = "Features",
        add_name_folder: bool = True,
    ) -> None:
        if not name:
            raise ValueError("Name cannot be empty")
        name = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in name)
        base_path = Path("Data")
        entity_type = "Guilds" if server_id is not None else entity_type
        
        path_parts = [entity_type]
        if server_id is not None:
            path_parts.append(str(server_id))
        if add_name_folder:
            path_parts.append(name)
        if subfolder:
            path_parts.append(subfolder)
        
        self.path= base_path.joinpath(*path_parts)
        self.file = self.path / f"{file_name}.json"
        self.default = default if default is not None else {}
        self.data = self.default
        self.auto_save = auto_save
        self._saved = False
        
        self.load()

    def _clean_cache(self) -> None:
        """Clean expired or excess cache entries."""
        current_time = time()
        keys_to_delete = [
            key for key, timestamp in self._cache_timestamps.items()
            if current_time - timestamp > self._cache_ttl
        ]
        for key in keys_to_delete:
            del self._cache[key]
            del self._cache_timestamps[key]

        # Enforce size limit (LRU eviction)
        if len(self._cache) > self._cache_limit:
            # Sort by oldest access time
            sorted_items = sorted(self._cache_timestamps.items(), key=lambda x: x[1])
            keys_to_evict = [item[0] for item in sorted_items[:len(self._cache) - self._cache_limit]]
            for key in keys_to_evict:
                del self._cache[key]
                del self._cache_timestamps[key]
    
    def __repr__(self) -> str:
        return f"<DataManager file_name={self.file!r} auto_save={self.auto_save}>"
    
    def __str__(self) -> str:
        return f"DataManager(path='{self.file}')"
    
    def __getitem__(self, key: str | int) -> Any:
        """Get item using dictionary syntax.
        
        Parameters
        ----------
        key: :class:`str`
            The key to access in the data dictionary.
            
        Returns
        -------
        Any
            The value associated with the key.
            
        Raises
        ------  
        TypeError
            If the underlying data is not a dictionary.
        KeyError
            If the key doesn't exist in the data.
        """
        if isinstance(self.data, dict):
            data = self.get(key, NoReturn)
            if data is NoReturn:
                raise KeyError(key)
            return data
        raise TypeError("Data is not a dictionary")

    def __setitem__(self, key: str, value: Any) -> None:
        """Set item using dictionary syntax.
        
        Parameters
        ----------
        key: :class:`str`
            The key to set in the data dictionary.
        value: Any
            The value to associate with the key.
            
        Raises
        ------
        TypeError
            If the underlying data is not a dictionary.
        """
        if isinstance(self.data, dict):
            self.set(key, value)
        else:
            raise TypeError("Data is not a dictionary")
            
    def __enter__(self) -> Self:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Context manager exit with optional auto-save."""
        if self.auto_save:
            self.save()
        return False
        
    def __len__(self) -> int:
        """Get length of the underlying data structure."""
        return len(self.data)

    def save(self) -> None:
        """Save data to JSON file.
        
        This method ensures the directory exists before writing the file.
        """
        self.path.mkdir(parents=True, exist_ok=True)
        with open(self.file, "w", encoding='utf-8') as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)
        self._saved = True
        
        # Update cache after saving
        cache_key = str(self.file)
        self._cache[cache_key] = self.data
        self._cache_timestamps[cache_key] = time()
        self._clean_cache()

    def load(self) -> Union[Dict, List, Any]:
        """Load data from JSON file.
        
        If the file doesn't exist, it returns the default data structure.
        
        Returns
        -------
        Union[:class:`Dict`, :class:`List`, Any]
            The loaded data or default structure.
        """
        cache_key = str(self.file)
    
        # Check cache first with proper validation
        if cache_key in self._cache:
            self._cache_timestamps[cache_key] = time()  # Update timestamp
            self.data = self._cache[cache_key]  # Make sure to update self.data
            return self.data

        # Load from file if not in cache
        try:
            with open(self.file, "r", encoding='utf-8') as f:
                self.data = json.load(f)
                # Update cache properly
                self._cache[cache_key] = self.data
                self._cache_timestamps[cache_key] = time()
                self._clean_cache()
                return self.data
        except FileNotFoundError:
            self.data = self.default
            return self.default

    def delete(self, key: Optional[str] = None) -> None:
        """Delete data or a specific key.
        
        Parameters
        ----------
        key: Optional[:class:`str`]
            The key to delete from the data. If ``None``, the entire file is deleted.
            
        Raises
        ------
        TypeError
            If the key is provided and the data structure is not compatible.
        """
        # cache_key = str(self.file)
    
        if key is not None:
            if isinstance(self.data, dict):
                if key in self.data:
                    del self.data[key]
                    # self._cache[cache_key] = self.data
                    # self._cache_timestamps[cache_key] = time()
                    # self._clean_cache()
                    self.save()
                else:
                    raise KeyError(f"Key '{key}' not found in data")
            elif isinstance(self.data, list):
                if key in self.data:
                    self.data.remove(key)
                    # self._cache[cache_key] = self.data
                    # self._cache_timestamps[cache_key] = time()
                    # self._clean_cache()
                    self.save()
                else:
                    raise ValueError(f"Item '{key}' not found in list")
            else:
                raise TypeError("Data is neither a dictionary nor a list")
        else:
            if self.file.exists():
                self.file.unlink()
            if not any(self.path.iterdir()):
                shutil.rmtree(self.path)
            
            # Remove from the cache when the file is deleted
            # self._cache.pop(cache_key, None)
            # self._cache_timestamps.pop(cache_key, None)

    def get(self, key: Any, default: Any = None) -> Any:
        """Get value from data with optional default.
        
        Parameters
        ----------
        key: Any
            The key to look up in the data.
        default: Any
            The value to return if the key is not found.
            
        Returns
        -------
        Any
            The value associated with the key or the default.
        """
        if isinstance(self.data, dict):
            return self.data.get(key, default)
        elif isinstance(self.data, (list, tuple)):
            return key if key in self.data else default
        return default

    def set(self, key: str, value: Any) -> None:
        """Set value in the data dictionary.
        
        Parameters
        ----------
        key: :class:`str`
            The key to set in the data.
        value: Any
            The value to associate with the key.
            
        Raises
        ------
        TypeError
            If the underlying data is not a dictionary.
        """
        if isinstance(self.data, dict):
            self.data[key] = value
            # cache_key = str(self.file)
            # self._cache[cache_key] = self.data
            # self._cache_timestamps[cache_key] = time()
            # self._clean_cache()
            if self.auto_save:
                self.save()
        else:
            raise TypeError("Data is not a dictionary")
        
    def update(self, data: Dict) -> None:
        """Update data with dictionary.
        
        Parameters
        ----------
        data: :class:`Dict`
            The dictionary to update the data with.
            
        Raises
        ------
        TypeError
            If the underlying data is not a dictionary.
        """
        if isinstance(self.data, dict):
            self.data.update(data)
            # cache_key = str(self.file)
            # self._cache[cache_key] = self.data
            # self._cache_timestamps[cache_key] = time()
            # self._clean_cache()
            if self.auto_save:
                self.save()
        else:
            raise TypeError("Data is not a dictionary")
            
    def append(self, item: Any) -> None:
        """Append an item to the data list.
        
        Parameters
        ----------
        item: Any
            The item to append to the data list.
            
        Raises
        ------
        TypeError
            If the underlying data is not a list.
        """
        if isinstance(self.data, list):
            self.data.append(item)
            # Update cache
            # cache_key = str(self.file)
            # self._cache[cache_key] = self.data
            # self._cache_timestamps[cache_key] = time()
            self._clean_cache()
        else:
            raise TypeError("Data is not a list")

    def exists(self) -> bool:
        """Check if the data file exists.
        
        Returns
        -------
        :class:`bool`
            True if the file exists, False otherwise.
        """
        return self.file.exists()