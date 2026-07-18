"""Canonical formation slot maps.

Coordinates are percentages of the pitch:
  x: 0 = left touchline, 100 = right
  y: 0 = own goal line, 100 = opposition goal line
"""

from __future__ import annotations

from typing import TypedDict


class SlotDef(TypedDict):
    key: str
    label: str
    x: float
    y: float


FORMATIONS: dict[str, list[SlotDef]] = {
    "4-3-3": [
        {"key": "GK", "label": "GK", "x": 50, "y": 8},
        {"key": "LB", "label": "LB", "x": 14, "y": 28},
        {"key": "LCB", "label": "LCB", "x": 36, "y": 24},
        {"key": "RCB", "label": "RCB", "x": 64, "y": 24},
        {"key": "RB", "label": "RB", "x": 86, "y": 28},
        {"key": "LCM", "label": "LCM", "x": 28, "y": 50},
        {"key": "CM", "label": "CM", "x": 50, "y": 46},
        {"key": "RCM", "label": "RCM", "x": 72, "y": 50},
        {"key": "LW", "label": "LW", "x": 18, "y": 76},
        {"key": "ST", "label": "ST", "x": 50, "y": 84},
        {"key": "RW", "label": "RW", "x": 82, "y": 76},
    ],
    "4-4-2": [
        {"key": "GK", "label": "GK", "x": 50, "y": 8},
        {"key": "LB", "label": "LB", "x": 14, "y": 28},
        {"key": "LCB", "label": "LCB", "x": 36, "y": 24},
        {"key": "RCB", "label": "RCB", "x": 64, "y": 24},
        {"key": "RB", "label": "RB", "x": 86, "y": 28},
        {"key": "LM", "label": "LM", "x": 16, "y": 52},
        {"key": "LCM", "label": "LCM", "x": 38, "y": 48},
        {"key": "RCM", "label": "RCM", "x": 62, "y": 48},
        {"key": "RM", "label": "RM", "x": 84, "y": 52},
        {"key": "LST", "label": "ST", "x": 38, "y": 82},
        {"key": "RST", "label": "ST", "x": 62, "y": 82},
    ],
    "3-5-2": [
        {"key": "GK", "label": "GK", "x": 50, "y": 8},
        {"key": "LCB", "label": "LCB", "x": 28, "y": 24},
        {"key": "CB", "label": "CB", "x": 50, "y": 22},
        {"key": "RCB", "label": "RCB", "x": 72, "y": 24},
        {"key": "LWB", "label": "LWB", "x": 12, "y": 48},
        {"key": "LCM", "label": "LCM", "x": 34, "y": 50},
        {"key": "CDM", "label": "CDM", "x": 50, "y": 42},
        {"key": "RCM", "label": "RCM", "x": 66, "y": 50},
        {"key": "RWB", "label": "RWB", "x": 88, "y": 48},
        {"key": "LST", "label": "ST", "x": 38, "y": 82},
        {"key": "RST", "label": "ST", "x": 62, "y": 82},
    ],
    "4-2-3-1": [
        {"key": "GK", "label": "GK", "x": 50, "y": 8},
        {"key": "LB", "label": "LB", "x": 14, "y": 28},
        {"key": "LCB", "label": "LCB", "x": 36, "y": 24},
        {"key": "RCB", "label": "RCB", "x": 64, "y": 24},
        {"key": "RB", "label": "RB", "x": 86, "y": 28},
        {"key": "LCDM", "label": "CDM", "x": 38, "y": 44},
        {"key": "RCDM", "label": "CDM", "x": 62, "y": 44},
        {"key": "LAM", "label": "LAM", "x": 20, "y": 66},
        {"key": "CAM", "label": "CAM", "x": 50, "y": 64},
        {"key": "RAM", "label": "RAM", "x": 80, "y": 66},
        {"key": "ST", "label": "ST", "x": 50, "y": 86},
    ],
    "3-4-3": [
        {"key": "GK", "label": "GK", "x": 50, "y": 8},
        {"key": "LCB", "label": "LCB", "x": 28, "y": 24},
        {"key": "CB", "label": "CB", "x": 50, "y": 22},
        {"key": "RCB", "label": "RCB", "x": 72, "y": 24},
        {"key": "LM", "label": "LM", "x": 16, "y": 50},
        {"key": "LCM", "label": "LCM", "x": 38, "y": 48},
        {"key": "RCM", "label": "RCM", "x": 62, "y": 48},
        {"key": "RM", "label": "RM", "x": 84, "y": 50},
        {"key": "LW", "label": "LW", "x": 20, "y": 78},
        {"key": "ST", "label": "ST", "x": 50, "y": 86},
        {"key": "RW", "label": "RW", "x": 80, "y": 78},
    ],
    "5-3-2": [
        {"key": "GK", "label": "GK", "x": 50, "y": 8},
        {"key": "LWB", "label": "LWB", "x": 10, "y": 32},
        {"key": "LCB", "label": "LCB", "x": 30, "y": 24},
        {"key": "CB", "label": "CB", "x": 50, "y": 22},
        {"key": "RCB", "label": "RCB", "x": 70, "y": 24},
        {"key": "RWB", "label": "RWB", "x": 90, "y": 32},
        {"key": "LCM", "label": "LCM", "x": 30, "y": 52},
        {"key": "CM", "label": "CM", "x": 50, "y": 48},
        {"key": "RCM", "label": "RCM", "x": 70, "y": 52},
        {"key": "LST", "label": "ST", "x": 38, "y": 82},
        {"key": "RST", "label": "ST", "x": 62, "y": 82},
    ],
    "4-1-4-1": [
        {"key": "GK", "label": "GK", "x": 50, "y": 8},
        {"key": "LB", "label": "LB", "x": 14, "y": 28},
        {"key": "LCB", "label": "LCB", "x": 36, "y": 24},
        {"key": "RCB", "label": "RCB", "x": 64, "y": 24},
        {"key": "RB", "label": "RB", "x": 86, "y": 28},
        {"key": "CDM", "label": "CDM", "x": 50, "y": 42},
        {"key": "LM", "label": "LM", "x": 16, "y": 62},
        {"key": "LCM", "label": "LCM", "x": 38, "y": 58},
        {"key": "RCM", "label": "RCM", "x": 62, "y": 58},
        {"key": "RM", "label": "RM", "x": 84, "y": 62},
        {"key": "ST", "label": "ST", "x": 50, "y": 86},
    ],
}

FORMATION_KEYS = list(FORMATIONS.keys())


def get_slots(formation: str) -> list[SlotDef]:
    slots = FORMATIONS.get(formation)
    if not slots:
        raise ValueError(f"Unknown formation: {formation}")
    return slots


def slot_keys(formation: str) -> set[str]:
    return {s["key"] for s in get_slots(formation)}
