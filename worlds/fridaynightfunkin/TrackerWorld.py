"""
Tracker World - Specialized FunkinWorld subclass for Universal Tracker re-generation.

This module handles creating a dynamic world class with pre-populated class-level
data from tracker passthrough, bypassing the timing issue where Archipelago resolves
item/location IDs from class dictionaries before instance creation.
"""

from .Items import SongData
# from .__init__ import LocationData


class MockOption:
    """Mock option object that holds a value for tracker re-generation"""
    def __init__(self, value):
        self.value = value


class MockOptions:
    """Mock options object that wraps stored option values"""
    def __init__(self, options_dict):
        for key, value in options_dict.items():
            setattr(self, key, MockOption(value))


def create_tracker_world_class(passthrough_data: dict) -> type:
    """
    Create a dynamic FunkinWorld subclass with all class-level attributes
    pre-populated from tracker re-generation passthrough data.
    
    This ensures Archipelago sees the correct item/location IDs when
    processing the tracker re-generation, since it reads IDs from class-level
    dictionaries before instances are created.
    
    Args:
        passthrough_data: The complete passthrough dict for this game (contains UTSlotData)
    
    Returns:
        The FunkinWorldTracker class type (not an instance)
    """
    # Import here to avoid circular imports
    from . import FunkinWorld, LocationData
    
    ut_slot_data = passthrough_data.get('UTSlotData', {})
    
    if not ut_slot_data:
        raise ValueError("[Tracker] No UTSlotData found in passthrough - cannot create tracker world")
    
    print("[TrackerWorld] Creating dynamic FunkinWorldTracker with pre-populated IDs from passthrough")
    
    # Reconstruct SongData objects from simplified passthrough format
    reconstructed_song_items = {}
    for song_name, item_data in ut_slot_data.get('song_items', {}).items():
        reconstructed_song_items[song_name] = SongData(
            code=item_data.get('code'),
            modded=item_data.get('modded', True),
            songName=item_data.get('songName', song_name),
            playerSongBelongsTo=item_data.get('playerSongBelongsTo', ''),
            playerList=item_data.get('playerList', [])
        )
    
    # Reconstruct custom location items
    reconstructed_custom_locations = {}
    for name, data in ut_slot_data.get('custom_locations', {}).items():
        reconstructed_custom_locations[name] = LocationData(
            code=data.get('id'),
            location_name=name,
            player_owner=data.get('playerOwner', ''),
            player_list=data.get('playerList', []),
            origin_song=data.get('originSong', ''),
            origin_mod=data.get('originMod', '')
        )
    
    # Create the dynamic class with all class-level data pre-populated
    class FunkinWorldTracker(FunkinWorld):
        """Dynamic tracker world with pre-populated class-level data from passthrough"""
        _is_tracker_world = True
        _initialized = True

        
        # ID mappings - CRITICAL for Archipelago
        # These MUST match the passthrough data exactly
        item_name_to_id = ut_slot_data.get('item_name_to_id', {}).copy()
        location_name_to_id = ut_slot_data.get('location_name_to_id', {}).copy()
        
        # Song and audio data
        song_items = reconstructed_song_items.copy()
        song_locations = ut_slot_data.get('song_locations', {}).copy()
        
        # YAML and player data
        all_yamls = ut_slot_data.get('all_yamls', [])
        player_song_additions = {}
        
        # Custom content - handle both old (list) and new (dict) formats
        raw_custom_items = ut_slot_data.get('custom_items', {})
        if isinstance(raw_custom_items, list):
            # Old format: flat list - convert to dict with empty player key
            custom_items_list = {'': raw_custom_items.copy()}
        else:
            # New format: dict with player_name keys
            custom_items_list = raw_custom_items.copy()
        
        raw_custom_traps = ut_slot_data.get('custom_trap_items', {})
        if isinstance(raw_custom_traps, list):
            # Old format: flat list - convert to dict with empty player key
            custom_trap_items_list = {'': raw_custom_traps.copy()}
        else:
            # New format: dict with player_name keys
            custom_trap_items_list = raw_custom_traps.copy()
        
        custom_location_items = reconstructed_custom_locations.copy()
        
        # Custom song modifications - must be dicts with player_name keys to match stuff()'s structure
        raw_song_adds = ut_slot_data.get('custom_song_additions', {})
        if isinstance(raw_song_adds, list):
            # Old format compatibility: convert list to empty dict
            custom_song_additions = {}
        else:
            custom_song_additions = raw_song_adds.copy()
        
        raw_song_excls = ut_slot_data.get('custom_song_exclusions', {})
        if isinstance(raw_song_excls, list):
            # Old format compatibility: convert list to empty dict
            custom_song_exclusions = {}
        else:
            custom_song_exclusions = raw_song_excls.copy()
        
        raw_song_reqs = ut_slot_data.get('custom_song_requirements', {})
        if isinstance(raw_song_reqs, list):
            # Old format compatibility: convert list to empty dict
            custom_song_requirements = {}
        else:
            custom_song_requirements = raw_song_reqs.copy()
        
        # Bundles (Mixtapes)
        song_bundles = ut_slot_data.get('song_bundles', {}).copy()
        bundle_locations = ut_slot_data.get('bundle_locations', {}).copy()
        
        # Sanity items and locations
        sanity_items_list = ut_slot_data.get('sanity_items_list', []).copy()
        sanity_location_ids = ut_slot_data.get('sanity_location_ids', {}).copy()
        
        # Storage for passthrough data - BOTH are needed
        # _passthrough_data contains generation_data at the top level
        # _ut_slot_data contains class-level data (IDs, songs, items, etc.)
        _passthrough_data = passthrough_data.copy()
        _ut_slot_data = ut_slot_data.copy()
        
        def generate_early(self):
            """Generate early phase - restore tracker state from passthrough instead of reprocessing"""
            print(f"[FunkinWorldTracker] Restoring complete generation state from passthrough")
            
            # Verify we have the passthrough data
            if not hasattr(self, '_ut_slot_data') or not self._ut_slot_data:
                print(f"[FunkinWorldTracker WARNING] No _ut_slot_data available")
                super(FunkinWorldTracker, self).generate_early()
                return
            
            # generation_data is stored at passthrough level by fill_slot_data()
            # Try passthrough first, fall back to _ut_slot_data for compatibility
            generation_data = self._passthrough_data.get('generation_data', {})
            if not generation_data:
                generation_data = self._ut_slot_data.get('generation_data', {})
            
            if not generation_data:
                print(f"[FunkinWorldTracker WARNING] No generation_data in passthrough, using defaults")
                generation_data = {}
            
            # === RESTORE OPTIONS FIRST ===
            # This is critical because parent methods depend on self.options having values
            # Replace self.options with a mock that has all the stored values
            stored_options = generation_data.get('options', {})
            if stored_options:
                print(f"[FunkinWorldTracker] Replacing options with mock containing {len(stored_options)} values")
                self.options = MockOptions(stored_options)
            else:
                print(f"[FunkinWorldTracker WARNING] No stored options found in generation_data")
            
            # === CORE GENERATION STATE ===
            # Restore all the dicts that get_item_count() and other methods need
            self.items_in_general = generation_data.get('items_in_general', {
                'Shield': 0,
                'Max HP Up': 0,
                'Max HP Down': 0,
                'Extra Life': 0
            })
            
            self.trap_items_weights = generation_data.get('trap_items_weights', {
                'Blue Balls Curse': 0,
                'Ghost Chat': 0,
                'SvC Effect': 0,
                'Tutorial Trap': 0,
                'Song Switch Trap': 0,
                'Opponent Mode Trap': 0,
                'Both Play Trap': 0,
                'Ultimate Confusion Trap': 0,
                'Fake Transition': 0,
                'Chart Modifier Trap': 0,
                'Resistance Trap': 0,
                'UNO Challenge': 0,
                'Pong Challenge': 0,
            })
            
            self.filter_items_weights = generation_data.get('filter_items_weights', {})
            
            # Ensure filter_items_weights has required filler items
            # These are the two main filter item types used in the game
            if not self.filter_items_weights:
                # Initialize with defaults if empty
                self.filter_items_weights = {
                    'Lonely Friday Night': 1,
                    'PONG Dash Mechanic': 1
                }
            else:
                # Ensure the required items are present
                if 'Lonely Friday Night' not in self.filter_items_weights:
                    self.filter_items_weights['Lonely Friday Night'] = 1
                if 'PONG Dash Mechanic' not in self.filter_items_weights:
                    self.filter_items_weights['PONG Dash Mechanic'] = 1
            
            # === BASIC SETTINGS ===
            self.mods_enabled = generation_data.get('mods_enabled', False)
            self.starting_song = generation_data.get('starting_song', '')
            self.unlock_type = generation_data.get('unlock_type', 'Per Song')
            self.unlock_method = generation_data.get('unlock_method', 'Song Completion')
            self.songLimit = generation_data.get('song_limit', 5)
            
            # === SONG AND VICTORY DATA ===
            self.playable_songs = generation_data.get('playable_songs', [])
            self.victory_song_name = generation_data.get('victory_song_name', '')
            self.victory_song_id = generation_data.get('victory_song_id', 0)
            self.songs_in_bundles = set(generation_data.get('songs_in_bundles', []))
            
            # === RESTORE SONG LISTS FOR LOCATION/REGION GENERATION ===
            # These are used by create_regions() for location setup
            self.original_song_list = generation_data.get('original_song_list', self.playable_songs.copy())
            self.songList = self.playable_songs.copy() if self.playable_songs else []
            
            # Restore starting song if available
            starting_song_name = generation_data.get('starting_song_name')
            if starting_song_name:
                self.starting_song_name = starting_song_name
            
            # === NUMERIC WEIGHTS AND SETTINGS ===
            self.trapAmount = generation_data.get('trap_amount', 0)
            self.ticket_percentage = generation_data.get('ticket_percentage', 0)
            self.ticket_win_percentage = generation_data.get('ticket_win_percentage', 100)
            self.graderequirement = generation_data.get('grade_requirement', 'A')
            self.accrequirement = generation_data.get('accuracy_requirement', '80')
            self.checksPerSong = generation_data.get('checks_per_song', 3)
            
            # === CUSTOM SONG MODIFICATIONS ===
            self._custom_song_exclusions = generation_data.get('song_exclusions', [])
            self._custom_song_additions = generation_data.get('song_additions', [])
            self._custom_song_requirements = generation_data.get('song_requirements', [])
            
            # === SANITY AND CACHING ===
            self._sanity_requirements_cache = generation_data.get('sanity_requirements_cache', {}).copy()
            
            print(f"[FunkinWorldTracker] ✓ Restored generation state:")
            print(f"  - {len(self.playable_songs)} playable songs")
            print(f"  - victory song: {self.victory_song_name} (ID: {self.victory_song_id})")
            print(f"  - original_song_list: {len(self.original_song_list)} songs")
            print(f"  - songList for regions: {len(self.songList)} songs")
            print(f"  - items_in_general: {self.items_in_general}")
            print(f"  - trap_items_weights: {sum(self.trap_items_weights.values())} total weight")
            print(f"  - options object replaced with {len(stored_options)} mock values")
            print(f"  - Starting song: {getattr(self, 'starting_song_name', 'None')}")
            print(f"  - Songs in bundles: {len(self.songs_in_bundles)}")
            import pprint
            pprint.pprint(f"Options: {vars(self.options)}")
        
        def check_filler_trap_weight(self, theFiller: str):
            """Override to ensure we always return a number, never None"""
            if self.filter_items_weights.keys().__contains__(theFiller):
                return self.filter_items_weights[theFiller]
            
            # Custom trap items default to weight 1 if not specified
            # Handle both old (list in dict) and current (multi-player) formats
            for player_traps in self.custom_trap_items_list.values():
                if theFiller in player_traps:
                    return 1
            
            # Default to 0 instead of returning None
            return 0
        
        def create_regions(self):
            """Create regions using parent implementation with tracker data"""
            print(f"[FunkinWorldTracker] Creating regions from passthrough data")
            
            # Call parent implementation - it will use the class-level location_name_to_id
            # which we've pre-populated from passthrough
            super(FunkinWorldTracker, self).create_regions()
            
            print(f"[FunkinWorldTracker] ✓ Regions created with {len(self.multiworld.get_regions(self.player))} regions")
        
        def create_items(self):
            """Create items using parent implementation with tracker data"""
            print(f"[FunkinWorldTracker] Creating items from passthrough data")
            
            # Call parent implementation - it will use the class-level item_name_to_id
            # which we've pre-populated from passthrough
            super(FunkinWorldTracker, self).create_items()
            
            print(f"[FunkinWorldTracker] ✓ Items created: {len(self.multiworld.itempool)} items in pool")
        
        def set_rules(self):
            """Set rules using parent implementation"""
            print(f"[FunkinWorldTracker] Setting access rules from tracker data")
            
            # Call parent implementation
            super(FunkinWorldTracker, self).set_rules()
            
            print(f"[FunkinWorldTracker] ✓ Access rules set")
    
    print(f"[TrackerWorld] ✓ Created FunkinWorldTracker with:")
    print(f"  - {len(FunkinWorldTracker.item_name_to_id)} items in name_to_id")
    print(f"  - {len(FunkinWorldTracker.location_name_to_id)} locations in name_to_id")
    print(f"  - {len(FunkinWorldTracker.song_items)} song items")
    print(f"  - {len(FunkinWorldTracker.song_bundles)} bundles")
    
    return FunkinWorldTracker
