"""
Tests for SpoilerDict implementation.

Run with: python -m pytest worlds/spoiler/test_spoiler_dict.py
"""

import pytest
from worlds.spoiler.SpoilerDict import SpoilerDict
from worlds.spoiler import (
    apply_spoiler_protection_to_world,
    extract_spoiler_metadata_for_slotdata,
    patch_slotdata_with_spoiler_data,
)
from worlds.spoiler.SpoilerDictUtils import (
    batch_convert_dicts,
    validate_spoiler_dict,
    compare_spoiler_dicts,
    merge_spoiler_dicts,
    get_spoiler_json_preview,
    create_reverse_label_lookup,
)


class TestSpoilerDict:
    """Tests for SpoilerDict core functionality."""
    
    def test_basic_creation(self):
        """Test creating a SpoilerDict."""
        data = {"key1": "value1", "key2": "value2"}
        labels = {"key1": "Label 1", "key2": "Label 2"}
        
        sd = SpoilerDict(real_data=data, key_labels=labels)
        
        assert sd["key1"] == "value1"
        assert sd["key2"] == "value2"
    
    def test_spoiler_free_iteration(self):
        """Test that iteration shows spoiler-free labels."""
        data = {"real_1": "value1", "real_2": "value2"}
        labels = {"real_1": "??", "real_2": "???_1"}
        
        sd = SpoilerDict(real_data=data, key_labels=labels)
        
        keys_list = list(sd.keys())
        assert "??" in keys_list
        assert "???_1" in keys_list
    
    def test_revealed_keys(self):
        """Test revealed_keys() returns actual keys."""
        data = {"real_1": "value1", "real_2": "value2"}
        labels = {"real_1": "??", "real_2": "???_1"}
        
        sd = SpoilerDict(real_data=data, key_labels=labels)
        
        revealed = sd.revealed_keys()
        assert revealed == {"real_1", "real_2"}
    
    def test_get_method_with_real_keys(self):
        """Test get() method works with real keys."""
        data = {"real_1": "value1"}
        sd = SpoilerDict(real_data=data, key_labels={"real_1": "??"})
        
        assert sd.get("real_1") == "value1"
        assert sd.get("nonexistent", "default") == "default"
    
    def test_equality(self):
        """Test equality compares data, not labels."""
        data1 = {"key1": "value1", "key2": "value2"}
        data2 = {"key1": "value1", "key2": "value2"}
        
        labels1 = {"key1": "Label A", "key2": "Label B"}
        labels2 = {"key1": "Different", "key2": "Labels"}
        
        sd1 = SpoilerDict(real_data=data1, key_labels=labels1)
        sd2 = SpoilerDict(real_data=data2, key_labels=labels2)
        
        # Should be equal despite different labels
        assert sd1 == sd2
    
    def test_equality_with_dict(self):
        """Test equality with regular dict."""
        data = {"key1": "value1"}
        sd = SpoilerDict(real_data=data, key_labels={"key1": "??"})
        regular = {"key1": "value1"}
        
        assert sd == regular
    
    def test_items_iteration(self):
        """Test items() returns spoiler-free labels."""
        data = {"real_1": "value1", "real_2": "value2"}
        labels = {"real_1": "Label A", "real_2": "Label B"}
        
        sd = SpoilerDict(real_data=data, key_labels=labels)
        
        items = dict(sd.items())
        assert items == {"Label A": "value1", "Label B": "value2"}
    
    def test_copy(self):
        """Test copy preserves labels."""
        data = {"key1": "value1"}
        labels = {"key1": "??"}
        
        sd1 = SpoilerDict(real_data=data, key_labels=labels)
        sd2 = sd1.copy()
        
        assert sd1 == sd2
        assert sd1.get_label("key1") == sd2.get_label("key1")
    
    def test_update(self):
        """Test update adds keys and labels."""
        sd = SpoilerDict(real_data={"a": 1}, key_labels={"a": "A"})
        sd.update({"b": 2})
        
        assert sd["b"] == 2
        assert "b" in sd.revealed_keys()
    
    def test_set_label(self):
        """Test setting custom labels."""
        sd = SpoilerDict(real_data={"key1": "value1"}, key_labels={"key1": "Old"})
        sd.set_label("key1", "New")
        
        assert sd.get_label("key1") == "New"
        assert list(sd.keys()) == ["New"]
    
    def test_get_revealed_key_for_label(self):
        """Test reverse lookup from label to key."""
        data = {"real_key": "value"}
        labels = {"real_key": "??"}
        
        sd = SpoilerDict(real_data=data, key_labels=labels)
        
        assert sd.get_revealed_key_for_label("??") == "real_key"
        assert sd.get_revealed_key_for_label("nonexistent") is None
    
    def test_repr(self):
        """Test repr shows spoiler-free version."""
        data = {"secret": "item"}
        labels = {"secret": "???"}
        
        sd = SpoilerDict(real_data=data, key_labels=labels)
        repr_str = repr(sd)
        
        assert "'??': 'item'" in repr_str
        assert "secret" not in repr_str


class TestApplySpoilerProtection:
    """Tests for apply_spoiler_protection_to_world function."""
    
    def test_basic_protection(self):
        """Test basic spoiler protection application."""
        slot_data = {"secret": "item"}
        
        class MockWorld:
            __class__.__name__ = "TestWorld"
            player = 1
        
        result = apply_spoiler_protection_to_world(
            slot_data,
            MockWorld(),
            key_labels={"secret": "??"}
        )
        
        assert isinstance(result, SpoilerDict)
        assert result["secret"] == "item"
        assert list(result.keys()) == ["??"]
    
    def test_metadata_extraction(self):
        """Test that metadata is properly set."""
        slot_data = {"secret": "item"}
        
        class MockWorld:
            __class__.__name__ = "TestWorld"
            player = 1
        
        result = apply_spoiler_protection_to_world(
            slot_data,
            MockWorld(),
            key_labels={"secret": "??"}
        )
        
        assert hasattr(result, '_spoiler_metadata')
        metadata = result._spoiler_metadata
        assert metadata["real_keys"]["??"] == "secret"
        assert metadata["real_items"]["secret"] == "item"


class TestPatchSlotData:
    """Tests for patch_slotdata_with_spoiler_data function."""
    
    def test_patches_spoiler_dicts(self):
        """Test that patch_slotdata_with_spoiler_data adds special_spoiler_data."""
        sd = SpoilerDict(
            real_data={"secret": "item"},
            key_labels={"secret": "??"}
        )
        sd._spoiler_metadata = {
            "real_keys": {"??": "secret"},
            "real_items": {"secret": "item"}
        }
        
        slot_data = {"data": sd, "version": 1}
        result = patch_slotdata_with_spoiler_data(slot_data)
        
        assert "special_spoiler_data" in result
        assert "data" in result["special_spoiler_data"]


class TestSpoilerDictUtils:
    """Tests for utility functions."""
    
    def test_validate_spoiler_dict(self):
        """Test validation of SpoilerDict."""
        data = {"key1": "value1", "key2": "value2"}
        labels = {"key1": "Label A", "key2": "Label B"}
        
        sd = SpoilerDict(real_data=data, key_labels=labels)
        is_valid, issues = validate_spoiler_dict(sd)
        
        assert is_valid
        assert len(issues) == 0
    
    def test_validate_detects_duplicates(self):
        """Test that validation detects duplicate labels."""
        data = {"key1": "value1", "key2": "value2"}
        
        sd = SpoilerDict(real_data=data)
        # Manually set duplicate labels
        sd._key_labels["key1"] = "Same"
        sd._key_labels["key2"] = "Same"
        
        is_valid, issues = validate_spoiler_dict(sd)
        
        assert not is_valid
        assert any("Duplicate" in issue for issue in issues)
    
    def test_compare_spoiler_dicts(self):
        """Test comparison of two SpoilerDicts."""
        data1 = {"key1": "value1"}
        data2 = {"key1": "value1"}
        
        sd1 = SpoilerDict(real_data=data1, key_labels={"key1": "Label A"})
        sd2 = SpoilerDict(real_data=data2, key_labels={"key1": "Label B"})
        
        result = compare_spoiler_dicts(sd1, sd2)
        
        assert result["are_equal"]
        assert len(result["different_labels"]) == 1
    
    def test_merge_spoiler_dicts(self):
        """Test merging multiple SpoilerDicts."""
        sd1 = SpoilerDict(
            real_data={"key1": "value1"},
            key_labels={"key1": "Label 1"}
        )
        sd2 = SpoilerDict(
            real_data={"key2": "value2"},
            key_labels={"key2": "Label 2"}
        )
        
        merged = merge_spoiler_dicts(sd1, sd2)
        
        assert len(merged.revealed_keys()) == 2
        assert merged["key1"] == "value1"
        assert merged["key2"] == "value2"
    
    def test_get_spoiler_json_preview(self):
        """Test JSON preview generation."""
        sd = SpoilerDict(
            real_data={"secret": "item"},
            key_labels={"secret": "??"}
        )
        
        json_str = get_spoiler_json_preview(sd)
        
        assert "'??': 'item'" in json_str
        assert "secret" not in json_str
    
    def test_create_reverse_label_lookup(self):
        """Test reverse lookup creation."""
        sd = SpoilerDict(
            real_data={"key1": "value1", "key2": "value2"},
            key_labels={"key1": "Label A", "key2": "Label B"}
        )
        
        lookup = create_reverse_label_lookup(sd)
        
        assert lookup["Label A"] == "key1"
        assert lookup["Label B"] == "key2"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
