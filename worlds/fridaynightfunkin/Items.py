# Copyright (c) 2022 FelicitusNeko
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

import typing

from BaseClasses import Item, ItemClassification
from typing import List

class FNFBaseList:
    baseSongs: List[str] = [
            "Bopeebo", "Fresh", "Dad Battle",
            "Spookeez", "South", "Monster",
            "Pico", "Philly Nice", "Blammed",
            "Satin Panties", "High", "Milf",
            "Cocoa", "Eggnog", "Winter Horrorland",
            "Senpai", "Roses", "Thorns",
            "Ugh", "Guns", "Stress",
            "Darnell", "Lit Up", "2Hot", "Blazin",
            "Darnell (BF Mix)", ""
        ]
    erectSongs: List[str] = [
            'Bopeebo Erect', 'Fresh Erect', 'Dad Battle Erect',
            'Spookeez Erect', 'South Erect',
            'Pico Erect', 'Philly Nice Erect', 'Blammed Erect',
            'Satin Panties Erect', 'High Erect',
            'Cocoa Erect', 'Eggnog Erect',
            'Senpai Erect', 'Roses Erect', 'Thorns Erect',
            'Ugh Erect'
        ]
    picoSongs: List[str] = [
            'Bopeebo (Pico mix)', 'Fresh (Pico mix)', 'Dad Battle (Pico mix)',
            'Spookeez (Pico mix)', 'South (Pico mix)',
            'Pico (Pico mix)', 'Philly Nice (Pico mix)', 'Blammed (Pico mix)',
            'Eggnog (Pico mix)',
            'Ugh (Pico mix)', 'Guns (Pico mix)'
        ]
    extraSongs: List[str] = [
            'Small Argument',
            'Beat Battle',
            'Beat Battle 2'
        ]

items: List[str] = [
    "Shield", "Max HP Up",
    "Note Checks", "Song Checks",
    "Blue Balls Curse", "Ghost Chat", "SvC Effect", "Tutorial Trap", "Fake Transition"
]


item_groups = {
    "Helpers": ["Shield", "Max HP Up"],
    "Targets": ["Note Checks", "Song Checks"],
    "Traps":   ["Blue Balls Curse", "Ghost Chat", "SvC Effect", "Tutorial Trap", "Fake Transition"]
}

item_table = {
    item: 690000 + x for x, item in enumerate(items)
}


class FunkinItem(Item):
    game = "Friday Night Funkin"
    type: str

    def __init__(self, name, classification, code, player):
        super(FunkinItem, self).__init__(
            name, classification, code, player)

        if code is None:
            self.type = "Event"
        elif name in item_groups["Traps"]:
            self.type = "Trap"
            self.classification = ItemClassification.trap
        elif name in item_groups["Targets"]:
            self.type = "Target"
            self.classification = ItemClassification.progression
        elif name in item_groups["Helpers"]:
            self.type = "Helper"
            self.classification = ItemClassification.useful
        else:
            self.type = "Other"