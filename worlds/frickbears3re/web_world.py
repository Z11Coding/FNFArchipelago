"""Web configuration for Five Nights at Frickbear's 3 randomizer."""

from .options import Frickbears3ReOptions


class WebWorld:
    """Web UI configuration for Five Nights at Frickbear's 3."""
    
    theme = "dark"
    
    # World display name
    display_name = "Five Nights at Frickbear's 3"
    
    # World description for web display
    description = """
    Five Nights at Frickbear's 3 is a fan-made game inspired by the Five Nights at Freddy's series.
    In this randomizer, you must salvage animatronics across 5 nights from different locations:
    Freddy Fazbear's Pizza, The New & Improved Freddy's, Fazbear's Fright, and William's Woods.
    """
    
    # Links and resources
    links = {
        "Frickbear's 3 on GameJolt": "https://gamejolt.com/games/frickbears3/930477"
    }
