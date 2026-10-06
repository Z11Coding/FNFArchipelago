from .bases import EvolveTestBase
from ..evolveData import genusSpecies

#exclude: wendigo


# "republic":is_race("terrifying"),
# "socialist":is_race("terrifying"),
# "magocracy":is_universe("magic"),
# "governor":is_option("govnr"),
# "wagon":AND(is_race("soul_eater"),isnt_species("wendigo")),
# "agriculture":OR(is_race("herbivore"),AND(isnt_race("carnivore"),isnt_race("detritivore"),isnt_race("soul_eater"))),
# "wind_plant":OR(is_race("carnivore"),is_race("detritivore"),is_race("artificial"),is_race("soul_eater"),is_race("unfathomable"),is_race("forager")),
# "reclaimer":shovels,
# "shovel":shovels,
# "iron_shovel":shovels,
# "steel_shovel":shovels,
# "titanium_shovel":shovels,
# "alloy_shovel":shovels,
# "theology":is_option("relig"),
# "theocracy":is_option("relig"),

# speciesGenus={}
# genusSpecies={
#     "organism": [
#         "protoplasm"
#     ],
#     "humanoid": [
#         "human",
#         "elven",
#         "orc",
#         "junker",
#         "sludge",
#         "ultra_sludge"
#     ],
#     "carnivore": [
#         "cath",
#         "wolven",
#         "vulpine"
#     ],
#     "herbivore": [
#         "centaur",
#         "rhinotaur",
#         "capybara"
#     ],
#     "small": [
#         "kobold",
#         "goblin",
#         "gnome"
#     ],
#     "giant": [
#         "ogre",
#         "cyclops",
#         "troll"
#     ],
#     "reptilian": [
#         "tortoisan",
#         "gecko",
#         "slitheryn"
#     ],
#     "avian": [
#         "arraak",
#         "pterodacti",
#         "dracnid"
#     ],
#     "plant": [
#         "entish",
#         "cacti",
#         "pinguicula"
#     ],
#     "fungi": [
#         "sporgar",
#         "shroomi",
#         "moldling"
#     ],
#     "insectoid": [
#         "mantis",
#         "scorpid",
#         "antid"
#     ],
#     "aquatic": [
#         "sharkin",
#         "octigoran"
#     ],
#     "fey": [
#         "dryad",
#         "satyr"
#     ],
#     "heat": [
#         "phoenix",
#         "salamander"
#     ],
#     "polar": [
#         "yeti",
#         "wendigo"
#     ],
#     "sand": [
#         "tuskin",
#         "kamel"
#     ],
#     "demonic": [
#         "balorg",
#         "imp",
#         "hellspawn"
#     ],
#     "angelic": [
#         "seraph",
#         "unicorn"
#     ],
#     "synthetic": [
#         "synth",
#         "nano"
#     ],
#     "eldritch": [
#         "ghast",
#         "shoggoth"
#     ],
#     "hybrid": [
#         "dwarf",
#         "raccoon",
#         "lichen",
#         "wyvern",
#         "beholder",
#         "djinn",
#         "narwhal",
#         "bombardier",
#         "nephilim"
#     ]
# }


# for genus in genusSpecies:
#     for species in genusSpecies[genus]:
#         if species in speciesGenus:
#             speciesGenus[species].append(genus)
#         else:
#             speciesGenus[species]=[genus]
# print(speciesGenus)
agricSet=["agriculture","farm_house","irrigation","copper_hoe","iron_hoe","steel_hoe","titanium_hoe","silo","mill","windmill","windturbine"]
agricSetBuild=["farm","mill","windmill","silo"]
class TestCarnivore(EvolveTestBase):
    options={
        "genus":"carnivore"
    }
    # locs=[]
    run_default_tests=False
    def test_locations_exist(self) -> None:
        for i in ["wind_plant","smokehouse"]:
            try:
                self.world.get_location(f"loc-tech:{i}")
            except KeyError:
                self.fail(f"Location 'loc-tech:{i}' should exist as the genus (carnivore) is correct, but it doesn't!")
        for i in ["smokehouse"]:
            try:
                self.world.get_location(f"loc-build:{i}")
            except KeyError:
                self.fail(f"Location 'loc-build:{i}' should exist as the genus (carnivore) is correct, but it doesn't!")
    def test_locations_not_exist(self)->None:
        for i in agricSet:
            self.assertRaises(KeyError,self.world.get_location,"loc-tech:"+i)
        for i in agricSetBuild:
            self.assertRaises(KeyError,self.world.get_location,"loc-build:"+i)
class TestFungi(EvolveTestBase):
    options={
        "genus":"fungi"
    }
    # locs=[]
    run_default_tests=False
    def test_locations_exist(self) -> None:
        for i in ["wind_plant","alt_lodge","compost","hot_compost","mulching","adv_mulching"]:
            try:
                self.world.get_location(f"loc-tech:{i}")
            except KeyError:
                self.fail(f"Location 'loc-tech:{i}' should exist as the genus (fungi) is correct, but it doesn't!")
                # break
        for i in ["compost","lodge"]:
            try:
                self.world.get_location(f"loc-build:{i}")
            except KeyError:
                self.fail(f"Location 'loc-build:{i}' should exist as the genus (fungi) is correct, but it doesn't!")
    def test_locations_not_exist(self)->None:
        for i in agricSet:
            self.assertRaises(KeyError,self.world.get_location,"loc-tech:"+i)
        
class TestDemonic(EvolveTestBase):
    options={
        "genus":"demonic"
    }
    # locs=[]
    run_default_tests=False
    def test_locations_exist(self) -> None:
        for i in ["wind_plant",]:
            try:
                self.world.get_location(f"loc-tech:{i}")
            except KeyError:
                self.fail(f"Location 'loc-tech:{i}' should exist as the genus (demonic) is correct, but it doesn't!")
        for i in ["soul_well"]:
            try:
                self.world.get_location(f"loc-build:{i}")
            except KeyError:
                self.fail(f"Location 'loc-build:{i}' should exist as the genus (demonic) is correct, but it doesn't!")
    def test_locations_not_exist(self)->None:
        for i in agricSet+["stone_axe", "copper_axes", "iron_saw", "iron_axes", "carpentry", "steel_saw", "steel_axes", "master_craftsman", "titanium_axes", "brickworks", "machinery"]:
            self.assertRaises(KeyError,self.world.get_location,"loc-tech:"+i)
        for i in agricSetBuild+["lumber_yard","sawmill"]:
            self.assertRaises(KeyError,self.world.get_location,"loc-build:"+i)
class TestEldritch(EvolveTestBase):
    options={
        "genus":"eldritch"
    }
    # locs=[]
    run_default_tests=False
    def test_locations_exist(self) -> None:
        for i in ["wind_plant","alt_lodge","captive_housing","torture","thrall_quarters","psychic_energy","psychic_attack","psychic_finance","mind_break","psychic_stun"]:
            try:
                self.world.get_location(f"loc-tech:{i}")
            except KeyError:
                self.fail(f"Location 'loc-tech:{i}' should exist as the genus (eldritch) is correct, but it doesn't!")
        for i in ["captive_housing","lodge"]:
            try:
                self.world.get_location(f"loc-build:{i}")
            except KeyError:
                self.fail(f"Location 'loc-build:{i}' should exist as the genus (eldritch) is correct, but it doesn't!")
    def test_locations_not_exist(self)->None:
        for i in agricSet:
            self.assertRaises(KeyError,self.world.get_location,"loc-tech:"+i)
        for i in agricSetBuild:
            self.assertRaises(KeyError,self.world.get_location,"loc-build:"+i)
class TestSynthetic(EvolveTestBase):
    options={
        "genus":"synthetic"
    }
    # locs=[]
    run_default_tests=False
    def test_locations_exist(self) -> None:
        for i in ["alt_lodge"]:
            try:
                self.world.get_location(f"loc-tech:{i}")
            except KeyError:
                self.fail(f"Location 'loc-tech:{i}' should exist as the genus (synthetic) is correct, but it doesn't!")
        for i in ["lodge"]:
            try:
                self.world.get_location(f"loc-build:{i}")
            except KeyError:
                self.fail(f"Location 'loc-build:{i}' should exist as the genus (synthetic) is correct, but it doesn't!")
    def test_locations_not_exist(self)->None:
        for i in agricSet+["aphrodisiac","hospital"]:
            self.assertRaises(KeyError,self.world.get_location,i)
        for i in agricSetBuild+["hospital"]:
            self.assertRaises(KeyError,self.world.get_location,"loc-build:"+i)
class TestAvian(EvolveTestBase):
    options={
        "genus":"avian"
    }
    # locs=[]
    run_default_tests=False
    def test_locations_not_exist(self)->None:
        for i in ["cement","rebar","steel_rebar","portland_cement","screw_conveyor"]:
            self.assertRaises(KeyError,self.world.get_location,i)
        for i in ["cement_plant"]:
            self.assertRaises(KeyError,self.world.get_location,"loc-build:"+i)
class TestPlant(EvolveTestBase):
    options={
        "genus":"plant"
    }
    # locs=[]
    run_default_tests=False
    def test_locations_not_exist(self)->None:
        for i in ["copper_sledgehammer","iron_sledgehammer","steel_sledgehammer","titanium_sledgehammer"]:
            self.assertRaises(KeyError,self.world.get_location,i)
class TestHeat(EvolveTestBase):
    options={
        "genus":"heat"
    }
    # locs=[]
    run_default_tests=False
    def test_locations_not_exist(self)->None:
        for i in ["stone_axe", "copper_axes", "iron_saw", "iron_axes", "carpentry", "steel_saw", "steel_axes", "master_craftsman", "titanium_axes", "brickworks", "machinery"]:
            self.assertRaises(KeyError,self.world.get_location,i)
        for i in ["lumber_yard","sawmill"]:
            self.assertRaises(KeyError,self.world.get_location,"loc-build:"+i)
# class TestCarnivore(EvolveTestBase):
#     options={
#         "genus":"carnivore"
#     }
#     # locs=[]
#     run_default_tests=False
#     def test_locations_exist(self) -> None:
#         for i in []:
#             try:
#                 self.world.get_location(f"loc-tech:{i}")
#             except KeyError:
#                 self.fail(f"Location 'loc-tech:{i}' should exist as the genus () is correct, but it doesn't!")
#     def test_locations_not_exist(self)->None:
#         for i in []:
#             self.assertRaises(KeyError,self.world.get_location,i)