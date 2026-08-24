"""Formation slot maps used by lineup UI."""

import pytest

from app.core.formations import FORMATIONS, FORMATION_KEYS, get_slots, slot_keys


def test_all_formations_have_eleven_unique_slots():
    assert len(FORMATION_KEYS) >= 5
    for name in FORMATION_KEYS:
        slots = get_slots(name)
        assert len(slots) == 11, f"{name} should have 11 slots"
        keys = [s["key"] for s in slots]
        assert len(keys) == len(set(keys)), f"{name} has duplicate keys"
        assert "GK" in keys


def test_slot_keys_matches_formation():
    keys = slot_keys("4-3-3")
    assert keys == {s["key"] for s in FORMATIONS["4-3-3"]}


def test_unknown_formation_raises():
    with pytest.raises(ValueError, match="Unknown formation"):
        get_slots("9-9-9")


def test_coordinates_within_pitch():
    for name, slots in FORMATIONS.items():
        for slot in slots:
            assert 0 <= slot["x"] <= 100, f"{name}/{slot['key']} x out of range"
            assert 0 <= slot["y"] <= 100, f"{name}/{slot['key']} y out of range"
