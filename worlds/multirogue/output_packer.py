"""
Output Packer for MultiRogue World

Handles creation of .apmrmw compressed multiworld files containing all stages.
Format: Python dict serialized with pickle and compressed with zlib.
"""

import logging
import pickle
import zlib
from typing import Dict, List, Any, Optional
from pathlib import Path

logger = logging.getLogger("MultiRogue")


class StageData:
    """Represents a single stage in the output."""
    
    def __init__(self, stage_num: int):
        self.stage_num = stage_num
        self.difficulty_target = 0.5
        self.games_used: List[str] = []
        self.multidata: Optional[bytes] = None
        self.spoiler: Optional[bytes] = None
        self.scenarios: List[bytes] = []  # List of .apsave files
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage_num": self.stage_num,
            "difficulty_target": self.difficulty_target,
            "games_used": self.games_used,
            "multidata": self.multidata,
            "spoiler": self.spoiler,
            "scenarios": self.scenarios,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StageData":
        stage = cls(data["stage_num"])
        stage.difficulty_target = data.get("difficulty_target", 0.5)
        stage.games_used = data.get("games_used", [])
        stage.multidata = data.get("multidata")
        stage.spoiler = data.get("spoiler")
        stage.scenarios = data.get("scenarios", [])
        return stage


class MultiRogueOutput:
    """Complete output data for a MultiRogue seed."""
    
    def __init__(self, seed: int, archipelago_version: str):
        self.version = 1
        self.seed = seed
        self.archipelago_version = archipelago_version
        self.num_stages = 0
        self.difficulty_curve = "linear"
        self.goal_info: Dict[str, Any] = {
            "goal_stages": 5,
            "is_multiplayer": False,
            "main_world_player": 1,
        }
        self.stage_list: List[StageData] = []
        self.stage_metadata: Dict[str, Any] = {}  # Meta-check mappings
        self.main_multidata: Optional[bytes] = None
        self.main_spoiler: Optional[bytes] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "version": self.version,
            "seed": self.seed,
            "archipelago_version": self.archipelago_version,
            "num_stages": self.num_stages,
            "difficulty_curve": self.difficulty_curve,
            "goal_info": self.goal_info,
            "stage_list": [stage.to_dict() for stage in self.stage_list],
            "stage_metadata": self.stage_metadata,
            "main_multidata": self.main_multidata,
            "main_spoiler": self.main_spoiler,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MultiRogueOutput":
        """Create from dictionary after deserialization."""
        output = cls(data["seed"], data["archipelago_version"])
        output.version = data.get("version", 1)
        output.num_stages = data.get("num_stages", 0)
        output.difficulty_curve = data.get("difficulty_curve", "linear")
        output.goal_info = data.get("goal_info", {})
        output.stage_list = [
            StageData.from_dict(stage_dict)
            for stage_dict in data.get("stage_list", [])
        ]
        output.stage_metadata = data.get("stage_metadata", {})
        output.main_multidata = data.get("main_multidata")
        output.main_spoiler = data.get("main_spoiler")
        return output


def pack_output(output_data: MultiRogueOutput, compression_level: int = 9) -> bytes:
    """
    Compress a MultiRogueOutput into .apmrmw format.
    
    Args:
        output_data: The output to compress
        compression_level: zlib compression level (0-9, default 9)
    
    Returns:
        Compressed bytes ready to write to .apmrmw file
    """
    try:
        # Serialize to pickle
        serialized = pickle.dumps(output_data.to_dict(), protocol=pickle.HIGHEST_PROTOCOL)
        
        # Compress with zlib
        compressed = zlib.compress(serialized, level=compression_level)
        
        logger.info(f"Packed {output_data.num_stages} stages: "
                   f"{len(serialized)} bytes → {len(compressed)} bytes "
                   f"({100*len(compressed)/len(serialized):.1f}% ratio)")
        
        return compressed
    
    except Exception as e:
        logger.error(f"Failed to pack output: {e}")
        raise


def unpack_output(data: bytes) -> MultiRogueOutput:
    """
    Decompress and deserialize a .apmrmw file.
    
    Args:
        data: Compressed bytes from .apmrmw file
    
    Returns:
        Deserialized MultiRogueOutput object
    """
    try:
        # Decompress
        decompressed = zlib.decompress(data)
        
        # Deserialize from pickle
        data_dict = pickle.loads(decompressed)
        
        output = MultiRogueOutput.from_dict(data_dict)
        logger.info(f"Unpacked {output.num_stages} stages from {len(data)} bytes")
        
        return output
    
    except Exception as e:
        logger.error(f"Failed to unpack output: {e}")
        raise


def write_output_file(output_data: MultiRogueOutput, output_path: Path) -> Path:
    """
    Write output to a .apmrmw file.
    
    Args:
        output_data: The output to write
        output_path: Directory to write to
    
    Returns:
        Path to created file
    """
    filename = f"AP_{output_data.seed}_MultiRogue.apmrmw"
    filepath = output_path / filename
    
    try:
        compressed = pack_output(output_data)
        with open(filepath, 'wb') as f:
            f.write(compressed)
        logger.info(f"Wrote output to {filepath}")
        return filepath
    
    except Exception as e:
        logger.error(f"Failed to write output file: {e}")
        raise
