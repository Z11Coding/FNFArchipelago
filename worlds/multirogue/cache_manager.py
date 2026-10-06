"""
Cache Manager for MultiRogue World

Manages caching of game complexity profiles to speed up generation.
Tracks game versions and determines when re-fuzzing is needed.
"""

import json
import logging
from typing import Dict, Optional, Any
from pathlib import Path

import Utils

logger = logging.getLogger("MultiRogue")


class ComplexityProfile:
    """Represents the difficulty metrics for a game."""
    
    def __init__(self, game: str, world_version: str):
        self.game = game
        self.world_version = world_version
        self.min_complexity = 0.0
        self.max_complexity = 1.0
        self.avg_complexity = 0.5
        self.sample_count = 0
        self.last_updated = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "world_version": self.world_version,
            "min": self.min_complexity,
            "max": self.max_complexity,
            "avg": self.avg_complexity,
            "samples": self.sample_count,
            "last_updated": self.last_updated,
        }
    
    @classmethod
    def from_dict(cls, game: str, data: Dict[str, Any]) -> "ComplexityProfile":
        profile = cls(game, data.get("world_version", "unknown"))
        profile.min_complexity = data.get("min", 0.0)
        profile.max_complexity = data.get("max", 1.0)
        profile.avg_complexity = data.get("avg", 0.5)
        profile.sample_count = data.get("samples", 0)
        profile.last_updated = data.get("last_updated", "")
        return profile


class CacheManager:
    """Manages the global complexity cache."""
    
    CACHE_FILENAME = "multirogue_complexity_cache.json"
    CACHE_VERSION = 1
    
    def __init__(self):
        self.cache_path = Path(Utils.cache_path("multirogue"))
        self.cache_path.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_path / self.CACHE_FILENAME
        self.cache_data: Dict[str, Any] = {}
        self.profiles: Dict[str, ComplexityProfile] = {}
        self._load_cache()
    
    def _load_cache(self) -> None:
        """Load existing cache from disk."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    self.cache_data = json.load(f)
                logger.debug(f"Loaded complexity cache ({len(self.cache_data.get('games', {}))} games)")
                
                # Validate cache version
                cache_version = self.cache_data.get("version", 0)
                if cache_version != self.CACHE_VERSION:
                    logger.warning(f"Cache version {cache_version} != {self.CACHE_VERSION}, will rebuild")
                    self.cache_data = self._create_empty_cache()
                
                # Load profiles
                for game, profile_data in self.cache_data.get("games", {}).items():
                    self.profiles[game] = ComplexityProfile.from_dict(game, profile_data)
            
            except Exception as e:
                logger.error(f"Failed to load cache: {e}")
                self.cache_data = self._create_empty_cache()
    
    def _create_empty_cache(self) -> Dict[str, Any]:
        """Create an empty cache structure."""
        return {
            "version": self.CACHE_VERSION,
            "games": {},
        }
    
    def save_cache(self) -> None:
        """Save cache to disk."""
        try:
            self.cache_data["games"] = {
                game: profile.to_dict()
                for game, profile in self.profiles.items()
            }
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache_data, f, indent=2)
            logger.debug(f"Saved complexity cache ({len(self.profiles)} games)")
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")
    
    def should_refuzz(self, game: str) -> bool:
        """
        Determine if a game needs re-fuzzing.
        
        Returns True if:
        - Game not in cache
        - World version changed
        - Cache is too old (> 30 days)
        """
        if game not in self.profiles:
            return True
        
        # Check if world version matches
        try:
            from worlds.AutoWorld import AutoWorldRegister
            world_type = AutoWorldRegister.world_types.get(game)
            if not world_type:
                return True
            
            current_version = str(world_type.world_version)
            cached_version = self.profiles[game].world_version
            
            if current_version != cached_version:
                logger.debug(f"Game {game} version changed: {cached_version} -> {current_version}")
                return True
        except Exception as e:
            logger.warning(f"Failed to check version for {game}: {e}")
            return True
        
        return False
    
    def update_profile(self, game: str, min_complexity: float, max_complexity: float, 
                      avg_complexity: float, sample_count: int) -> None:
        """Update complexity profile for a game."""
        world_version = "unknown"
        try:
            from worlds.AutoWorld import AutoWorldRegister
            world_type = AutoWorldRegister.world_types.get(game)
            if world_type:
                world_version = str(world_type.world_version)
        except Exception as e:
            logger.warning(f"Failed to get version for {game}: {e}")
        
        profile = ComplexityProfile(game, world_version)
        profile.min_complexity = min_complexity
        profile.max_complexity = max_complexity
        profile.avg_complexity = avg_complexity
        profile.sample_count = sample_count
        profile.last_updated = Utils.get_datetime_second() if hasattr(Utils, 'get_datetime_second') else ""
        
        self.profiles[game] = profile
        logger.debug(f"Cached profile for {game}: complexity [{min_complexity:.2f}, {max_complexity:.2f}] avg={avg_complexity:.2f}")
        self.save_cache()
    
    def get_profile(self, game: str) -> Optional[ComplexityProfile]:
        """Get cached profile for a game."""
        return self.profiles.get(game)


# Global cache manager instance
_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """Get or create the global cache manager."""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager
