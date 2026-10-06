from dataclasses import dataclass

from Options import Choice, OptionGroup, PerGameCommonOptions, Range, Toggle, NamedRange, DefaultOnToggle, DeathLink

# In this file, we define the options the player can pick.
# The most common types of options are Toggle, Range and Choice.

# Options will be in the game's template yaml.
# They will be represented by checkboxes, sliders etc. on the game's options page on the website.
# (Note: Options can also be made invisible from either of these places by overriding Option.visibility.
#  Evolve doesn't have an example of this, but this can be used for secret / hidden / advanced options.)

# For further reading on options, you can also read the Options API Document:
# https://github.com/ArchipelagoMW/Archipelago/blob/main/docs/options%20api.md


# The first type of Option we'll discuss is the Toggle.
# A toggle is an option that can either be on or off. This will be represented by a checkbox on the website.
# The default for a toggle is "off".
# If you want a toggle to be on by default, you can use the "DefaultOnToggle" class instead of the "Toggle" class.
# class ExtraStartingChest(Toggle):
#     """
#     Adds an extra chest in the bottom left, making room for an extra Confetti Cannon.
#     """

#     display_name = "Extra Starting Chest"


# class TrapChance(Range):
#     """
#     Percentage chance that any given Confetti Cannon will be replaced by a Math Trap.
#     """

#     display_name = "Trap Chance"

#     range_start = 0
#     range_end = 100
#     default = 0
class GovernorToggle(Toggle):
    """Choose whether Governors will be enabled in game."""
    display_name="Governors Unlocked"

class ReligionUnlocked(DefaultOnToggle):
    """Choose whether Religion is availible in game."""
    display_name="Religion Unlocked"

class Starting2xSpeed(Range):
    """Choose the amount of 2x Speed the game will start with."""
    display_name="Starting 2x Speed (hrs)"
    
    range_start=0
    range_end=8
    default=0
class StartingPlasmids(Range):
    """Choose the amount of Plasmids the game will start with."""
    display_name="Plasmids"

    range_start=0
    range_end=1000
    # special_range_names={
    #     "Hard":0,
    #     "Easy":300,
    #     "Overkill":1000,
    # }

    default=100
class StartingPhage(Range):
    """Choose the amount of Phage the game will start with."""
    display_name="Phage"

    range_start=0
    range_end=500
    # special_range_names={
    #     "0-250_plasmids":0,
    #     "~500_plasmids":250,
    #     "~1000_plasmids":500,
    # }

    default=range_start
class StartingAntip(Range):
    """Choose the amount of Anti-Plasmids the game will start with."""
    display_name="Anti Plasmids"

    range_start=0
    range_end=1000
    # special_range_names={
    #     "hard":0,
    #     "easy":100,
    #     "overkill":1000,
    # }

    default=100
# THIS NOT BE NEEDED BECAUSE THE GENUS WILL CHANGE IT
# class ChooseStartingPlanet(Choice):
#     """Choose the planet the game will be played on."""
#     display_name="Starting Planet"
    
#     option_random_planet=0
#     option_grassland=1
#     option_oceanic=2
#     option_forest=3
#     option_desert=4
#     option_volcanic=5
#     option_tundra=6
#     option_savanna=7
#     option_swamp=8
#     option_ashland=9
#     option_taiga=10

#     default=option_random_planet
class PreviousRace(Choice):
    """Choose the the progrenitor race for the game. This is only for if you choose Fanaticism."""
    display_name="Progenitor Race"

    option_none=0
    option_human=1
    option_elf=2
    option_orc=3
    option_kobold=4
    option_goblin=5
    option_gnome=6
    option_ogre=7
    option_cyclops=8
    option_troll=9
    option_tortoisan=10
    option_gecko=11
    option_sliheryn=12
    option_cacti=13
    option_pinguicula=14
    option_sporgar=15
    option_shroomi=16
    option_moldling=17
    option_mantis=18
    option_scorpid=19
    option_antid=20
    option_sharkin=21
    option_octigoran=22
    option_dryad=23
    option_satyr=24
    option_phoenix=25
    option_salamander=26
    option_yeti=27
    option_wendigo=28
    option_tuskin=29
    option_kamel=30
    option_balrog=31
    option_imp=32
    option_seraph=33
    option_unicorn=34
    option_synth=35
    option_nano=36
    option_ghast=37
    option_shoggoth=38
    option_dwarf=39
    option_lichen=40
    option_wyvern=41
    option_eye_spector=42
    option_djinn=43
    option_narwhalus=44
    option_bombardier=45
    option_nephilim=46
    option_hellspawn=47
    option_cath=48
    option_wolven=49
    option_vulpine=50
    option_centaur=51
    option_rhinotaur=52
    option_capybara=53
    option_araak=54
    option_pterodacti=55
    option_dracnid=56
    option_ent=57
    option_racconar=58
    option_dwarf=59
    option_racconar=60

    default=option_none
class HolidaysActive(Choice):
    """Choose which Holiday event's are active for your game. (this probally won't work!)"""
    display_name="Active Holidays"

    option_none=0
    option_egg_hunt=1
    option_solstice_festival=2
    option_trick_or_treat=3
    option_festive_season=4

    default=option_none
class DeathLinkAmnesty(Range):
    """How many deaths will it take to activate Death Link?
    Please note: Death Link is... dangerous.
    Death Link will set your population to 1 and troops to 0, unless death percent says otherwise.
    """

    display_name="Death Link Amnesty"

    range_start=1
    range_end=10

    default=5
class DeathLinkPercent(Range):
    """What percent of your population will die when Death Link is activated.
    IE: At 100%, no people will live. At 10%, 90% of your population will live.
    A minimum of 1 person will die, unless you have exactly 1 pop.
    """
    display_name="Death Link Percent"

    range_start=10
    range_end=100

    default=range_end

class ChooseGenus(Choice):
    """What Genus will you evolve into: Carnivore, Fungi, Demonic, Synthetic, Eldritch
    All other Genuses are included in Other.
    You can see what the Others option includes on the Setup Page"""
    display_name="Choose Genus"
    #exclude: wendigo,sharkin,dryad
    option_other=0
    option_carnivore=1
    option_avian=2
    option_plant=3
    option_heat=4
    option_angelic=5
    option_fungi=6
    option_demonic=7
    option_synthetic=8
    option_eldritch=9

    default=option_other
class ChooseUniverse(Choice):
    """What universe will you be in?
    IF YOU DO NOT KNOW WHAT EACH UNIVERSE DOES
        DO   NOT    CHANGE    THIS!!!
    """
    display_name="Choose Universe"

    option_standard=0
    option_heavy_gravity=1
    option_antimatter=2
    option_evil=3
    option_micro=4
    option_magic=5

    default=option_standard
# We must now define a dataclass inheriting from PerGameCommonOptions that we put all our options in.
# This is in the format "option_name_in_snake_case: OptionClassName".
@dataclass
class EvolveOptions(PerGameCommonOptions):
    # planet:ChooseStartingPlanet
    speed:Starting2xSpeed
    plasmid:StartingPlasmids
    phage:StartingPhage
    antip:StartingAntip
    govnr:GovernorToggle
    relig:ReligionUnlocked
    prerace:PreviousRace
    deathlink:DeathLink
    deathamn:DeathLinkAmnesty
    deathperc:DeathLinkPercent
    genus:ChooseGenus
    univ:ChooseUniverse
    
    # holiday:HolidaysActive

#progressionBalancing,accessibility,local items, non-local items, start inventory, start hints, start location hints, exclued locations, priority locations



# If we want to group our options by similar type, we can do so as well. This looks nice on the website.
option_groups = [
    OptionGroup(
        "Prestige Options",
        [StartingPlasmids,StartingPhage,StartingAntip]
    ),
    OptionGroup(
        "DeathLink",
        [DeathLink,DeathLinkAmnesty,DeathLinkPercent]
    ),
    OptionGroup(
        "Race Related",
        [ChooseGenus,PreviousRace]
    ),
    OptionGroup(
        "Gameplay Options",
        [Starting2xSpeed,GovernorToggle,ReligionUnlocked,ChooseUniverse]
    ),
]

# Finally, we can define some option presets if we want the player to be able to quickly choose a specific "mode".
option_presets = {
    "normal":{
        # "planet":ChooseStartingPlanet.option_random_planet,
        "speed":4,
        "plasmid":100,
        "phage":0,
        "antip":10,
        "govnr":False,
        "relig":True,
        "prerace":PreviousRace.option_none,
        "holiday":HolidaysActive.option_none,
        "deathlink":False,
        "deathamn":DeathLinkAmnesty.default,
        "deathperc":DeathLinkPercent.default,
        "genus":ChooseGenus.default,
        "univ":ChooseUniverse.default,
    },
}
