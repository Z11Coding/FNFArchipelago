from .bases import EvolveTestBase
from ..evolveData import optionDependReqs

class TestReligionOff(EvolveTestBase):
    options={
        "relig":False,
    }
    run_default_tests=False
    def test_relig_locations_dont_exist(self) -> None:
        locs=optionDependReqs["relig"][1]
        for loc in locs:
            self.assertRaises(KeyError,self.world.get_location,loc)
class TestReligionOn(EvolveTestBase):
    options={
        "relig":True,
    }
    run_default_tests=False
    def test_relig_locations_exist(self) ->None:
        for loc in optionDependReqs["relig"][1]:
            try:
                self.world.get_location(loc)
            except KeyError:
                self.fail(f"Location {loc} should exist as religion is enabled, but it doesn't!")