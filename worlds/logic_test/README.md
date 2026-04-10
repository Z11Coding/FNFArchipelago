# Logic Test World

A specialized Archipelago world for analyzing multiworld logic without generating traditional gameplay.

## Overview

The Logic Test world is designed to debug and verify multiworld seeds by analyzing whether items and locations have proper logic requirements. It checks if:

1. **No Logic**: All items are accessible without collecting any progression items
2. **Sphere 1 Only**: All items are accessible with just the starting items
3. **Logic Required**: Items require progression through multiple spheres

## Usage

Include the Logic Test world in your multiworld with other worlds you want to test. When generation completes:

1. The world analyzes accessibility of all non-filler items across all worlds
2. Results are displayed showing:
   - Total items analyzed
   - Items accessible in Sphere 0 (no items needed)
   - Items accessible in Sphere 1 (starting items only)
   - Items requiring progression
3. You're prompted to confirm whether to continue with the seed

## Options

- **Enable Logic Test**: When enabled (default), runs the logic analysis after generation

## How It Works

The Logic Test world:
- Creates no items or locations of its own
- Analyzes the entire multiworld after item placement
- Uses accessibility rules to determine which items can be reached at each sphere
- Displays detailed results including the maximum sphere depth needed

## Example Output

```
============================================================
LOGIC TEST RESULTS
============================================================

Total Non-Filler Items: 150
Items in Sphere 0 (No Logic): 0
Items in Sphere 1 (Starting Items): 145
Items in Other Spheres: 5
Max Sphere Depth: 3

------------------------------------------------------------
✓ Result: SPHERE 1 ONLY
  All items are accessible with just starting items.
------------------------------------------------------------

Do you want to continue with this seed? (yes/no): 
```
