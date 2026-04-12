# Copyright (c) 2024
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

from typing import Dict, Set, List, Tuple
from argparse import Namespace
from BaseClasses import Region, Location, Item, ItemClassification, CollectionState, MultiWorld
from .Items import *
from .Locations import *
from .Options import LogicTestOptions
from ..AutoWorld import World, call_all
from worlds.generic.Rules import exclusion_rules

class CancelGeneration(Exception):
    """Custom exception to signal generation cancellation due to a player deciding to cancel it."""
    pass
class LogicTestWorld(World):
    """
    Logic Test World - A debugging world that analyzes multiworld logic.
    
    This world checks if the multiworld has:
    - No logic (all items accessible without any items)
    - Sphere 1 only (all items accessible with just starting items)
    
    After generation, results are displayed and user confirmation is requested.
    """
    
    game = "Logic Test"
    options_dataclass = LogicTestOptions
    options: LogicTestOptions
    item_name_to_id = {}
    location_name_to_id = {}
    
    def create_items(self) -> None:
        """Logic Test world doesn't create items - it analyzes existing ones."""
        pass
    
    def create_regions(self) -> None:
        """Logic Test world doesn't create regions - it analyzes existing ones."""
        pass
    
    def fill_hook(self, progitempool: List[Item], nonprogresspool: List[Item],
                   locations: List[Location], forced_good_item_locations: List[Location]) -> None:
        """
        After all items are placed, analyze the multiworld logic to determine accessibility patterns.
        Checks if items are all accessible without logic, in sphere 1 only, or require progression.
        """
        if not self.options.enable_logic_test:
            return
        
        # Error on multiple Logic Test worlds
        other_logic_worlds = [pid for pid in self.multiworld.player_ids 
                             if pid != self.player and self.multiworld.game[pid] == "Logic Test" and isinstance(self.multiworld.worlds.get(pid), LogicTestWorld)]
        if other_logic_worlds:
            raise Exception(f"Multiple Logic Test worlds detected: {[self.player] + other_logic_worlds}. "
                          "Only one Logic Test world is allowed per multiworld.")
        
        # Check if a No Logic world exists (which would invalidate logic testing)
        try:
            from ..noLogic import NoLogicWorld
            no_logic_worlds = [pid for pid in self.multiworld.player_ids 
                              if self.multiworld.game[pid] == "No Logic" and isinstance(self.multiworld.worlds.get(pid), NoLogicWorld)]
            
            if no_logic_worlds:
                # Check if any No Logic world would invalidate the test
                # The test is only invalidated if No Logic is set to mode 1 (enabled/no-logic mode)
                # Mode 0 = disabled, Mode 1 = enabled (removes logic), Mode 2 = logical mode (keeps logic)
                should_abort = False
                for pid in no_logic_worlds:
                    world: NoLogicWorld = self.multiworld.worlds[pid]
                    
                    # Check the no_progression_maze option value
                    # Value 0 = disabled (Still no logic)
                    # Value 1 = enabled mode (removes all logic)
                    # Value 2 = logical mode (preserves logic)
                    if hasattr(world.options, 'no_progression_maze'):
                        maze_mode = world.options.no_progression_maze.value
                        if maze_mode != 2:  # Only abort if not in logical mode
                            should_abort = True
                            break
                
                if should_abort:
                    print("\n" + "="*70)
                    print("ERROR: No Logic world in no-logic mode detected!")
                    print("="*70)
                    print("Logic Test world cannot be used with No Logic!")
                    print(f"No Logic worlds: {no_logic_worlds}")
                    print("Reason: No Logic world inherently removes all logic,")
                    print("        which breaks Logic Test's analysis and makes results invalid.")
                    print("        (Logical mode (no_progression_maze=2) would be acceptable)")
                    print("="*70 + "\n")
                    raise Exception("Logic Test world is incompatible with No Logic world in no-logic mode. "
                                  "Use No Logic in Logical mode (no_progression_maze=2) instead. If you for some reason have" \
                                  "more than one No Logic world, you're definitely doing something wrong.")
        except ImportError:
            # No Logic world not available, continue normally
            pass
        
        try:
            results = self.analyze_sphere_logic()
            self.display_results(results)
        except Exception as e:
            import time
            import traceback
            if isinstance(e, CancelGeneration):
                print("\nGeneration cancelled by user.")
                import sys
                # Show the breakdown and then close.
                print("\n" + "="*70)
                print("LOGIC TEST CANCELLED BY USER")
                print("="*70)
                print("The logic test results were:")
                print(f"  No Logic: {results['is_no_logic']}")
                print(f"  Sphere 1 Only: {results['is_sphere_1_only']}")
                print(f"  Max Sphere Required: {results['max_sphere']}")
                print(f"  Other Sphere Items: {results['other_sphere_items']}")
                print("="*70 + "\n")
                # PER GAME.
                print("Per-player logic analysis:")
                for player_id, analysis in results['per_player'].items():
                    player_name = self.multiworld.player_name[player_id]
                    print(f"  Player {player_id} ({player_name}):")
                    print(f"    Total Items: {analysis['total']}")
                    print(f"    Sphere 1 Items: {analysis['sphere_1']}")
                    
                    if analysis['no_logic']:
                        print(f"    ✗ NO LOGIC - All items accessible without progression")
                    elif analysis['sphere_1_only']:
                        print(f"    ✗ SPHERE 1 ONLY - All items accessible with starting items")
                    else:
                        unreachable = analysis['total'] - analysis['sphere_1']
                        print(f"    ✓ LOGIC REQUIRED - {unreachable} items need progression")
                print("="*70 + "\n")
                sys.exit(0)
            
            try:
                # Display generation info and error details
                self.display_error_info(e, traceback)
            except Exception as display_error:
                # If display fails, just print basic error info
                print(f"\nError during logic test:")
                print(f"  Error Type: {type(e).__name__}")
                print(f"  Error Message: {str(e)}")
                print("\nTraceback:")
                traceback.print_exc()
            
            # Check if No Logic exists - cannot continue if it does
            try:
                from ..noLogic import NoLogicWorld
                no_logic_worlds = [pid for pid in self.multiworld.player_ids 
                                  if self.multiworld.game[pid] == "No Logic" and isinstance(self.multiworld.worlds.get(pid), NoLogicWorld)]
                
                if no_logic_worlds:
                    print("\n" + "="*70)
                    print("ERROR: No Logic world detected!")
                    print("="*70)
                    print("Generation cannot continue because No Logic world exists.")
                    print("No Logic breaks if using player-specific items.")
                    print("="*70 + "\n")
                    import sys
                    sys.exit(1)
            except ImportError:
                pass
            
            # Wait before showing input prompt
            time.sleep(3)
            
            # Ask user what to do
            response = input("\nDo you want to continue with this seed anyway? (yes/no): ").strip().lower()
            if response not in ['yes', 'y']:
                import sys
                print("Exiting generation due to logic test error.")
                sys.exit(1)

    def create_test_multiworld(self) -> MultiWorld:
        """
        Create a test multiworld by properly replicating the generation pipeline.
        
        This follows the exact pattern from Main.py and test utilities:
        1. Create fresh MultiWorld
        2. Set seed
        3. Build options Namespace with remapped player IDs
        4. Call set_options() to create fresh world instances
        5. Initialize CollectionState
        6. Run generation pipeline
        """
        print("\n[Logic Test] Creating test multiworld...")
        source = self.multiworld
        logic_test_player = self.player
        
        # Identify non-logic-test players
        non_logic_players = [pid for pid in source.player_ids if pid != logic_test_player]
        print(f"[Logic Test] Non-logic players: {non_logic_players}")
        
        if not non_logic_players:
            raise Exception("No players to test - only Logic Test world exists")
        
        # Create player ID mapping (old -> new)
        player_map = {}
        for new_id, old_id in enumerate(sorted(non_logic_players), 1):
            player_map[old_id] = new_id
        print(f"[Logic Test] Player ID mapping: {player_map}")
        
        # Step 1: Create fresh multiworld with filtered player count
        print(f"[Logic Test] Step 1: Creating fresh MultiWorld with {len(non_logic_players)} players...")
        test_mw = MultiWorld(len(non_logic_players))
        
        # Step 2: Set seed (this initializes the random number generator properly)
        print(f"[Logic Test] Step 2: Setting seed...")
        test_mw.set_seed(source.seed)
        test_mw.seed_name = source.seed_name
        test_mw.algorithm = source.algorithm
        test_mw.is_race = source.is_race if hasattr(source, 'is_race') else False
        test_mw.testing_logic = True  # Flag to indicate this is a logic test multiworld
        print(f"[Logic Test]   Seed: {test_mw.seed_name}, Algorithm: {test_mw.algorithm}")
        
        # Step 3: Build options Namespace (required by set_options)
        print(f"[Logic Test] Step 3: Building options Namespace...")
        options_dict = {}
        
        # Map game and player names
        options_dict['game'] = {player_map[old_id]: source.game[old_id] for old_id in non_logic_players}
        options_dict['name'] = {player_map[old_id]: source.player_name[old_id] for old_id in non_logic_players}
        print(f"[Logic Test]   Games: {options_dict['game']}")
        print(f"[Logic Test]   Player names: {options_dict['name']}")
        
        # Initialize multiworld game and player_name before set_options
        test_mw.game = options_dict['game']
        test_mw.player_name = options_dict['name']
        
        # Copy per-world options directly from source worlds (Option instances)
        print(f"[Logic Test] Step 3b: Copying per-world options...")
        from worlds import AutoWorldRegister
        
        for old_id in non_logic_players:
            if old_id in source.worlds:
                new_id = player_map[old_id]
                old_world = source.worlds[old_id]
                game_name = source.game[old_id]
                
                # Get the world type and its option classes
                try:
                    world_type = AutoWorldRegister.world_types[game_name]
                    option_classes = world_type.options_dataclass.type_hints
                    print(f"[Logic Test]   {game_name} Player {new_id}: {len(option_classes)} options")
                    
                    # For each option, copy the Option instance directly from source
                    for option_name, option_class in option_classes.items():
                        if hasattr(old_world.options, option_name):
                            source_option = getattr(old_world.options, option_name)
                            
                            # Copy the Option instance directly (it's already the right type)
                            if option_name not in options_dict:
                                options_dict[option_name] = {}
                            options_dict[option_name][new_id] = source_option
                except KeyError:
                    print(f"[Logic Test]   WARNING: Unknown game type '{game_name}', skipping options")
        
        # Copy global options directly from source multiworld (Option instances)
        print(f"[Logic Test] Step 3c: Copying global options...")
        from Options import CommonOptions
        
        # Get all common option classes
        common_option_classes = CommonOptions.type_hints
        
        for option_name, option_class in common_option_classes.items():
            # Initialize dict for this option
            options_dict[option_name] = {}
            
            # Copy from source multiworld or use defaults
            if hasattr(source, option_name):
                source_dict = getattr(source, option_name, {})
                if isinstance(source_dict, dict):
                    for old_id, source_option in source_dict.items():
                        if old_id in player_map:
                            new_id = player_map[old_id]
                            # Copy the Option instance directly
                            options_dict[option_name][new_id] = source_option
            
            # Fill in any missing players with defaults
            for new_id in test_mw.player_ids:
                if new_id not in options_dict[option_name]:
                    if hasattr(option_class, 'from_any'):
                        options_dict[option_name][new_id] = option_class.from_any(option_class.default)
                    else:
                        options_dict[option_name][new_id] = option_class(option_class.default)
        
        print(f"[Logic Test]   Copied {len(common_option_classes)} common options")
        
        # Create Namespace for set_options
        options_ns = Namespace(**options_dict)
        
        # Step 4: Call set_options() which creates fresh world instances
        print(f"[Logic Test] Step 4: Calling set_options() to create fresh world instances...")
        test_mw.set_options(options_ns)
        print(f"[Logic Test]   Fresh worlds created: {list(test_mw.worlds.keys())}")
        
        # Verify worlds have their options set
        for player_id, world in test_mw.worlds.items():
            print(f"[Logic Test]   Player {player_id} ({world.__class__.__name__}) has options: {hasattr(world, 'options')}")
            if hasattr(world, 'options'):
                print(f"[Logic Test]     Options type: {type(world.options).__name__}")
        
        # Step 5: Copy precollected items and remap player IDs
        print(f"[Logic Test] Step 5: Copying precollected items with remapped player IDs...")
        for old_id in non_logic_players:
            if old_id in source.precollected_items:
                new_id = player_map[old_id]
                items = source.precollected_items[old_id]
                # Remap player IDs in items
                for item in items:
                    if item.player == old_id:
                        item.player = new_id
                test_mw.precollected_items[new_id] = items
                print(f"[Logic Test]   Player {new_id} (remapped from {old_id}): {len(items)} precollected items")
        
        # Step 6: Copy plando item blocks with remapped player IDs
        print(f"[Logic Test] Step 6: Copying plando item blocks with remapped player IDs...")
        if hasattr(source, 'plando_item_blocks'):
            for old_id in non_logic_players:
                if old_id in source.plando_item_blocks:
                    new_id = player_map[old_id]
                    blocks = source.plando_item_blocks[old_id]
                    # Remap player IDs in plando blocks
                    for block in blocks:
                        if hasattr(block, 'player') and block.player == old_id:
                            block.player = new_id
                    test_mw.plando_item_blocks[new_id] = blocks
                    print(f"[Logic Test]   Player {new_id} (remapped from {old_id}): {len(blocks)} plando blocks")
        
        # Step 7: Initialize CollectionState
        print(f"[Logic Test] Step 7: Initializing CollectionState...")
        test_mw.state = CollectionState(test_mw)
        
        # Step 8: Run the generation pipeline (explicitly call on each world)
        print(f"\n[Logic Test] ========== RUNNING GENERATION PIPELINE ==========")
        gen_steps = [
            ("generate_early", "Early generation hooks"),
            ("create_regions", "Creating regions"),
            ("create_items", "Creating items"),
            ("set_rules", "Setting access rules"),
            ("connect_entrances", "Connecting entrances"),
            ("generate_basic", "Final generation"),
        ]
        
        for step_name, step_desc in gen_steps:
            print(f"\n[Logic Test] Step: {step_name} - {step_desc}")
            
            # Special handling for generate_early - this is critical
            if step_name == "generate_early":
                print(f"[Logic Test]   *** CRITICAL STEP: {step_name} populates dynamic data structures ***")
                print(f"[Logic Test]   Testing world access to multiworld attributes...")
                for player_id, world in test_mw.worlds.items():
                    print(f"[Logic Test]     Player {player_id}: ", end="")
                    print(f"has options={hasattr(world, 'options')}, ", end="")
                    print(f"multiworld={hasattr(world, 'multiworld')}, ", end="")
                    print(f"player={hasattr(world, 'player')}")
            
            # Debug: show which worlds exist
            print(f"[Logic Test]   Worlds in test_mw: {list(test_mw.worlds.keys())}")
            for player_id, world in test_mw.worlds.items():
                print(f"[Logic Test]     Player {player_id}: {world.__class__.__name__}")
                if hasattr(world, step_name):
                    print(f"[Logic Test]       → Has {step_name} method")
                else:
                    print(f"[Logic Test]       → MISSING {step_name} method")
            
            # Call the generation step using call_all
            try:
                print(f"[Logic Test]   Calling call_all(test_mw, '{step_name}')...")
                call_all(test_mw, step_name)
                print(f"[Logic Test]   ✓ {step_name} completed via call_all")
                
                # After generate_early, check what was populated
                if step_name == "generate_early":
                    print(f"[Logic Test]   generate_early done. Checking multiworld state...")

            except AttributeError as e:
                print(f"[Logic Test]   ✗ call_all failed with AttributeError: {e}")
                print(f"[Logic Test]   Trying direct world calls...")
                # Fallback: call directly on each world
                for player_id, world in test_mw.worlds.items():
                    if hasattr(world, step_name):
                        try:
                            method = getattr(world, step_name)
                            print(f"[Logic Test]     Calling {step_name} on Player {player_id}...")
                            method()
                            print(f"[Logic Test]     ✓ {step_name} called on Player {player_id}")
                        except Exception as method_error:
                            print(f"[Logic Test]     ✗ {step_name} failed on Player {player_id}: {type(method_error).__name__}: {method_error}")
                            import traceback
                            traceback.print_exc()
                    else:
                        print(f"[Logic Test]     - Player {player_id} does not have {step_name}")
            except Exception as e:
                print(f"[Logic Test]   ✗ {step_name} failed: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
                raise
            
            # Show what was created/modified
            if step_name == "create_regions":
                print(f"[Logic Test]   → Regions created: {len(test_mw.regions)}")
                if test_mw.regions:
                    regions_by_player = {}
                    for region in test_mw.regions:
                        if region.player not in regions_by_player:
                            regions_by_player[region.player] = []
                        regions_by_player[region.player].append(region.name)
                    for player_id in sorted(regions_by_player.keys()):
                        print(f"[Logic Test]     Player {player_id}: {len(regions_by_player[player_id])} regions")
            
            elif step_name == "create_items":
                print(f"[Logic Test]   → Items created: {len(test_mw.itempool)}")
                # Group by player
                items_by_player = {}
                for item in test_mw.itempool:
                    if item.player not in items_by_player:
                        items_by_player[item.player] = []
                    items_by_player[item.player].append(item)
                for player_id in sorted(items_by_player.keys()):
                    print(f"[Logic Test]     Player {player_id}: {len(items_by_player[player_id])} items")
            
            elif step_name == "set_rules":
                print(f"[Logic Test]   → Access rules set on all regions")
            
            elif step_name == "connect_entrances":
                print(f"[Logic Test]   → Entrances connected")
            
            elif step_name == "generate_basic":
                print(f"[Logic Test]   → Generation complete")
        
        print(f"\n[Logic Test] ========== PIPELINE COMPLETE ==========")
        print(f"[Logic Test] Final state:")
        print(f"[Logic Test]   Total regions: {len(test_mw.regions)}")
        print(f"[Logic Test]   Total itempool: {len(test_mw.itempool)} items")
        locations = list(test_mw.get_locations())
        print(f"[Logic Test]   Total locations: {len(locations)}")
        
        print(f"\n[Logic Test] Initializing final CollectionState for logic testing...")
        test_mw.state = CollectionState(test_mw)
        
        return test_mw

    def display_error_info(self, error: Exception, traceback_module) -> None:
        """
        Display comprehensive generation info when an error occurs.
        
        Shows seed, per-world item/location counts, and error details.
        """
        print("\n" + "="*70)
        print("LOGIC TEST ERROR - GENERATION INFORMATION")
        print("="*70)
        
        # Generation metadata
        multiworld = self.multiworld
        print(f"\nGeneration Seed: {multiworld.seed}")
        print(f"Multiworld ID: {multiworld.seed_name if hasattr(multiworld, 'seed_name') else 'N/A'}")
        num_players = (len(multiworld.players) if isinstance(multiworld.players, dict) else multiworld.players) - 1
        print(f"Total Players: {num_players}")
        
        # Count items and locations per world
        items_per_world = {}
        locations_per_world = {}
        
        for location in multiworld.get_locations():
            world_name = f"{self.multiworld.worlds[location.player].__class__.__name__} (Player {location.player})" if hasattr(self.multiworld, 'worlds') else f"World {location.player}"
            game = self.multiworld.worlds[location.player].game if hasattr(self.multiworld, 'worlds') else "Unknown Game"
            
            if world_name not in locations_per_world:
                locations_per_world[world_name] = {"count": 0, "game": game}
            locations_per_world[world_name]["count"] += 1
            
            if location.item:
                if world_name not in items_per_world:
                    items_per_world[world_name] = {"progression": 0, "useful": 0, "filler": 0}
                
                if location.item.classification == ItemClassification.progression:
                    items_per_world[world_name]["progression"] += 1
                elif location.item.classification == ItemClassification.useful:
                    items_per_world[world_name]["useful"] += 1
                else:
                    items_per_world[world_name]["filler"] += 1
        
        # Display per-world summary
        print("\n" + "-"*70)
        print("PER-WORLD BREAKDOWN:")
        print("-"*70)
        
        total_locations = 0
        total_prog_items = 0
        total_useful_items = 0
        total_filler_items = 0
        
        for world_name in sorted(items_per_world.keys()):
            items = items_per_world[world_name]
            locs = locations_per_world.get(world_name, {}).get("count", 0)
            game = locations_per_world.get(world_name, {}).get("game", "Unknown")
            
            prog = items["progression"]
            useful = items["useful"]
            filler = items["filler"]
            total = prog + useful + filler
            
            print(f"\n  {world_name}")
            print(f"    Game: {game}")
            print(f"    Locations: {locs}")
            print(f"    Items: {total} (Progression: {prog}, Useful: {useful}, Filler: {filler})")
            
            total_locations += locs
            total_prog_items += prog
            total_useful_items += useful
            total_filler_items += filler
        
        # Overall totals
        print("\n" + "-"*70)
        print("TOTALS:")
        print("-"*70)
        print(f"  Total Locations: {total_locations}")
        print(f"  Total Items: {total_prog_items + total_useful_items + total_filler_items}")
        print(f"    - Progression: {total_prog_items}")
        print(f"    - Useful: {total_useful_items}")
        print(f"    - Filler: {total_filler_items}")
        
        # Error details
        print("\n" + "-"*70)
        print("ERROR DETAILS:")
        print("-"*70)
        print(f"  Error Type: {type(error).__name__}")
        print(f"  Error Message: {str(error)}")
        print("\n  Traceback:")
        traceback_module.print_exc()
        
        print("\n" + "="*70)
    
    def analyze_sphere_logic(self) -> Dict:
        """
        Analyze the multiworld to determine sphere information.
        
        Returns a dict with:
        - total_items: Total items in the multiworld (excluding filler)
        - sphere_0_items: Items accessible without any progression
        - sphere_1_items: Items accessible with starting items only
        - other_sphere_items: Items needing additional progression
        - is_no_logic: Whether it appears to be no logic
        - is_sphere_1_only: Whether all items are in sphere 1
        - per_game_analysis: Dict of analysis for each game
        """
        from BaseClasses import ItemClassification
        
        print(f"\n[Logic Test] ========== STARTING LOGIC ANALYSIS ==========")
        print(f"[Logic Test] Creating fresh multiworld for testing...")
        
        # Create a fresh test multiworld that replicates the original's generation
        multiworld = self.create_test_multiworld()
        logic_test_player = self.player  # Still the logic test player number from original
        
        # Get all non-filler items across all worlds, organized by game
        # Note: Fresh multiworld doesn't have Logic Test player, so no filtering needed
        print(f"[Logic Test] Gathering items from all worlds...")
        all_items = {}
        game_items = {}  # Items organized by game/world
        
        for location in multiworld.get_locations():
            if location.item and location.item.classification != ItemClassification.filler:
                world_name = multiworld.player_name.get(location.item.player, f"Player {location.item.player}")
                game_name = multiworld.game.get(location.item.player, "Unknown")
                
                if world_name not in all_items:
                    all_items[world_name] = []
                all_items[world_name].append(location.item)
                
                if game_name not in game_items:
                    game_items[game_name] = []
                game_items[game_name].append(location.item)
        
        total_items = sum(len(items) for items in all_items.values())
        print(f"[Logic Test] Total non-filler items: {total_items}")
        for game_name, items in game_items.items():
            print(f"[Logic Test]   {game_name}: {len(items)} items")
        
        # Analyze per-game accessibility
        print(f"\n[Logic Test] Analyzing per-game logic...")
        per_game_analysis = {}
        for game_name, items in game_items.items():
            print(f"[Logic Test]   Analyzing {game_name}...")
            # Fresh multiworld has no logic test player, so pass -1 or 0 to skip filtering
            game_analysis = self.analyze_game_logic(multiworld, game_name, items, -1)
            per_game_analysis[game_name] = game_analysis
        
        # Test sphere accessibility for all items
        print(f"\n[Logic Test] Testing item accessibility by sphere...")
        collection_state = CollectionState(multiworld)
        
        # Use proper sphere collection logic similar to multiworld.get_spheres()
        print(f"\n[Logic Test] Using proper sphere collection logic...")
        
        sphere_0_items = 0
        sphere_1_items = 0
        sphere_index = 0  # 0-indexed: sphere 0, sphere 1, etc.
        
        # Create fresh state for sphere analysis
        collection_state = CollectionState(multiworld)
        filled_locations = set(multiworld.get_filled_locations())
        
        # Process each sphere properly
        while filled_locations:
            sphere: Set[Location] = set()
            
            # Find all currently reachable locations
            for location in filled_locations:
                try:
                    if location.can_reach(collection_state):
                        sphere.add(location)
                except Exception as e:
                    # Log problematic locations but don't crash
                    error_msg = str(e)
                    if not any(x in error_msg for x in ["access_rule", "Tricks", "Items", "Enemies"]):
                        print(f"[Logic Test] Warning: {location.name} (Player {location.player}) - {type(e).__name__}: {error_msg[:80]}")
            
            if not sphere:
                # No more reachable locations
                if filled_locations:
                    print(f"[Logic Test] Found {len(filled_locations)} unreachable locations")
                break
            
            # Count items in this sphere
            sphere_item_count = 0
            for location in sphere:
                if location.item and location.item.classification != ItemClassification.filler:
                    sphere_item_count += 1
            
            print(f"[Logic Test] Sphere {sphere_index}: {sphere_item_count} items ({len(sphere)} total locations)")
            
            # Record sphere 0 and 1 specifically
            if sphere_index == 0:
                sphere_0_items = sphere_item_count
            elif sphere_index == 1:
                sphere_1_items = sphere_item_count
            
            # Collect all items from current sphere
            for location in sphere:
                if location.item:
                    collection_state.collect(location.item, True, location)
            
            # Remove processed locations and move to next sphere
            filled_locations -= sphere
            sphere_index += 1
        
        # Count total accessible items (should be all items by this point)
        final_items = 0
        for location in multiworld.get_filled_locations():
            if location.item and location.item.classification != ItemClassification.filler:
                try:
                    if location.can_reach(collection_state):
                        final_items += 1
                except Exception:
                    pass
        
        other_sphere_items = final_items - sphere_1_items
        
        is_no_logic = sphere_0_items >= total_items * 0.95  # 95% threshold for no logic
        is_sphere_1_only = sphere_1_items >= total_items * 0.95 and not is_no_logic
        
        # Check if multiworld can be beaten immediately with just starting items
        print(f"\n[Logic Test] Checking if multiworld can be beaten immediately...")
        starting_only_state = CollectionState(multiworld)
        can_beat_immediately = multiworld.can_beat_game(starting_only_state)
        print(f"[Logic Test] Multiworld beatable immediately: {can_beat_immediately}")
        
        # Check per-game if games can be beaten immediately
        print(f"\n[Logic Test] Checking per-game immediate completion...")
        per_game_beatable = {}
        for game_name in game_items.keys():
            # Get all players for this game
            game_players = [pid for pid in multiworld.player_ids if multiworld.game[pid] == game_name]
            
            # Check if they can beat the game with starting items
            state = CollectionState(multiworld)
            can_beat = all(multiworld.has_beaten_game(state, pid) for pid in game_players)
            per_game_beatable[game_name] = can_beat
            print(f"[Logic Test]   {game_name}: {can_beat}")
        
        print(f"\n[Logic Test] Analysis complete!")
        print(f"[Logic Test] Results: {total_items} total, {sphere_0_items} in sphere 0, {sphere_1_items} in sphere 1, {other_sphere_items} beyond")
        
        return {
            "total_items": total_items,
            "sphere_0_items": sphere_0_items,
            "sphere_1_items": sphere_1_items,
            "other_sphere_items": other_sphere_items,
            "is_no_logic": is_no_logic,
            "is_sphere_1_only": is_sphere_1_only,
            "max_sphere": sphere_index,
            "can_beat_immediately": can_beat_immediately,
            "per_game_beatable": per_game_beatable,
            "per_game_analysis": per_game_analysis,
        }
    
    def analyze_game_logic(self, multiworld: MultiWorld, game_name: str, items: List[Item], logic_test_player: int = -1) -> Dict:
        """
        Analyze logic for a specific game's items using proper can_reach() method.
        
        Returns dict with sphere 0 and 1 accessibility, and whether items are no-logic or sphere-1-only.
        """
        if not items:
            return {"total": 0, "no_logic": False, "sphere_1_only": False}
        
        collection_state = CollectionState(multiworld)
        total_game_items = len(items)
        
        # Count items accessible in sphere 0 using proper can_reach() method
        accessible_sphere_0 = 0
        for item in items:
            try:
                for loc in multiworld.get_locations():
                    if loc.item == item and loc.can_reach(collection_state):
                        accessible_sphere_0 += 1
                        break  # Found this item is reachable
            except Exception:
                # Skip items that cause errors
                pass
        
        # Simulate sphere 1 by collecting all reachable items
        try:
            filled_locations = set(multiworld.get_filled_locations())
            while filled_locations:
                sphere: Set[Location] = set()
                # Find reachable items in current state
                for location in filled_locations:
                    try:
                        if location.can_reach(collection_state):
                            sphere.add(location)
                    except Exception:
                        pass
                
                if not sphere:
                    break
                
                # Collect items from this sphere
                for location in sphere:
                    if location.item:
                        collection_state.collect(location.item, True, location)
                
                filled_locations -= sphere
        except Exception:
            pass
        
        # Count items accessible after collecting sphere 0
        accessible_sphere_1 = 0
        for item in items:
            try:
                for loc in multiworld.get_locations():
                    if loc.item == item and loc.can_reach(collection_state):
                        accessible_sphere_1 += 1
                        break
            except Exception:
                pass
        
        is_no_logic = accessible_sphere_0 >= total_game_items * 0.95
        is_sphere_1_only = accessible_sphere_1 >= total_game_items * 0.95 and not is_no_logic
        
        return {
            "total": total_game_items,
            "sphere_0": accessible_sphere_0,
            "sphere_1": accessible_sphere_1,
            "no_logic": is_no_logic,
            "sphere_1_only": is_sphere_1_only,
        }
    
    def count_accessible_items(self, collection_state: CollectionState, multiworld: MultiWorld,
                               all_items: Dict[str, List[Item]], logic_test_player: int = -1) -> int:
        """
        Count how many non-filler items are currently accessible using proper can_reach() method.
        
        Gracefully handles access rule failures from custom lambdas or missing dynamic data.
        """
        count = 0
        for location in multiworld.get_filled_locations():
            # Skip logic test player's locations if a valid player ID is provided (-1 means no filtering)
            if logic_test_player >= 0 and location.player == logic_test_player:
                continue
            
            if location.item and location.item.classification != ItemClassification.filler:
                try:
                    if location.can_reach(collection_state):
                        count += 1
                except Exception:
                    # Skip locations whose access rules fail to evaluate
                    pass
        return count
    
    def display_results(self, results: Dict) -> None:
        """Display logic analysis results."""
        print("\n" + "="*60)
        print("LOGIC TEST RESULTS")
        print("="*60)
        
        print(f"\nTotal Non-Filler Items: {results['total_items']}")
        print(f"Items in Sphere 0 (Starting Items): {results['sphere_0_items']}")
        print(f"Items in Sphere 1 (First Accessible Items): {results['sphere_1_items']}")
        print(f"Items in Other Spheres: {results['other_sphere_items']}")
        print(f"Max Sphere Depth: {results['max_sphere']}")
        
        print("\n" + "-"*60)
        if results['is_no_logic']:
            print("✗ Result: NO LOGIC DETECTED")
            print("  All items are accessible without any progression items.")
        elif results['is_sphere_1_only']:
            print("✗ Result: SPHERE 1 ONLY")
            print("  All items are accessible with just starting items.")
        else:
            print("✓ Result: LOGIC REQUIRED")
            print(f"  Items require progression through sphere {results['max_sphere']}.")
            print(f"  {results['other_sphere_items']} items beyond Sphere 1.")
        print("-"*60)
        
        # Check if multiworld can be beaten immediately
        print("\nBEATABILITY CHECK:")
        print("-"*60)
        if results['can_beat_immediately']:
            print("✗ Multiworld can be beaten immediately with starting items only!")
        else:
            print("✓ Multiworld requires progression items to beat")
        
        # Display per-game analysis with beatable status
        if results['per_game_analysis']:
            print("\nPER-GAME ANALYSIS:")
            print("-"*60)
            for game_name, analysis in results['per_game_analysis'].items():
                if analysis['total'] > 0:
                    print(f"\n{game_name}:")
                    print(f"  Total Items: {analysis['total']}")
                    print(f"  Sphere 0: {analysis['sphere_0']}")
                    print(f"  Sphere 1: {analysis['sphere_1']}")
                    
                    if analysis['no_logic']:
                        print(f"  ✗ NO LOGIC - All items accessible without progression")
                    elif analysis['sphere_1_only']:
                        print(f"  ✗ SPHERE 1 ONLY - All items accessible with starting items")
                    else:
                        unreachable = analysis['total'] - analysis['sphere_1']
                        print(f"  ✓ LOGIC REQUIRED - {unreachable} items need progression")
                    
                    # Show if this game can be beaten immediately
                    can_beat = results['per_game_beatable'].get(game_name, False)
                    if can_beat:
                        print(f"  ✗ Can be beaten immediately with starting items!")
                    else:
                        print(f"  ✓ Requires progression to beat")
            print("-"*60 + "\n")
        
        # Check if No Logic exists - cannot continue if it does
        try:
            from ..noLogic import NoLogicWorld
            no_logic_worlds = [pid for pid in self.multiworld.player_ids 
                              if self.multiworld.game[pid] == "No Logic" and isinstance(self.multiworld.worlds.get(pid), NoLogicWorld)]
            
            if no_logic_worlds:
                print("\n" + "="*70)
                print("ERROR: No Logic world detected!")
                print("="*70)
                print("Generation cannot continue because No Logic world exists.")
                print("No Logic breaks if using player-specific items.")
                print("="*70 + "\n")
                import sys
                sys.exit(1)
        except ImportError:
            pass
        
        # Ask for confirmation
        response = input("Do you want to continue with this seed? (yes/no): ").strip().lower()
        if response not in ['yes', 'y']:
            raise CancelGeneration("Logic test cancelled by user.")
        
        print("Continuing with generation...\n")
        # Give Final Results a moment to sink in before proceeding
        import time
        time.sleep(2)
        print("\n" + "="*60 + "\n")
        print(f"Proceeding with normal generation, filling the multiworld with {len(self.multiworld.itempool)} items.")
