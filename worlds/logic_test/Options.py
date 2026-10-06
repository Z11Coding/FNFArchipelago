# Copyright (c) 2024
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

from dataclasses import dataclass
from Options import Toggle, PerGameCommonOptions


class EnableLogicTest(Toggle):
    """
    When enabled, runs a logic analysis after generation to determine if the multiworld
    has no logic requirements or if all items are reachable in Sphere 1.
    After analysis completes, results will be displayed and you'll be asked if you want
    to continue with generation.
    """
    display_name = "Enable Logic Test"
    default = True


@dataclass
class LogicTestOptions(PerGameCommonOptions):
    enable_logic_test: EnableLogicTest
