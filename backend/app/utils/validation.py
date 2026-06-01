# app/utils/validation.py
"""Utility functions for weight validation and normalization.
These are used by the claim split service to ensure that:
- Each element weight is clamped between 0 and 100.
- The total weight of all elements for a claim sums to exactly 100%.
"""

from typing import List, Dict

def clamp_weight(weight: float) -> float:
    """Clamp a weight value to the 0‑100 range.
    
    Args:
        weight: The raw weight (may be any float).
    Returns:
        A weight bounded between 0 and 100.
    """
    if weight < 0:
        return 0.0
    if weight > 100:
        return 100.0
    return float(weight)

def normalize_weights(elements: List[Dict]) -> List[Dict]:
    """Normalize a list of element dicts so their ``weight`` fields sum to 100.
    
    The function respects the original relative proportions of the
    provided weights and then corrects any rounding errors by adjusting
    the last element.
    
    Args:
        elements: List of dicts, each containing a ``weight`` key (float).
    Returns:
        The same list (modified in‑place) with normalized ``weight`` values.
    """
    if not elements:
        return elements
    # Clamp individual weights first
    for el in elements:
        el["weight"] = clamp_weight(el.get("weight", 0))
    total = sum(el["weight"] for el in elements)
    if total == 0:
        # If everything is zero, distribute equally
        equal = round(100.0 / len(elements), 2)
        for el in elements:
            el["weight"] = equal
        # Adjust last element to hit exactly 100
        elements[-1]["weight"] = round(100.0 - equal * (len(elements) - 1), 2)
        return elements
    # Scale weights proportionally
    factor = 100.0 / total
    for el in elements:
        el["weight"] = round(el["weight"] * factor, 2)
    # Fix any rounding drift so the sum is exactly 100
    corrected_total = sum(el["weight"] for el in elements)
    diff = round(100.0 - corrected_total, 2)
    if diff != 0:
        # Apply the difference to the element with the largest weight
        max_el = max(elements, key=lambda e: e["weight"])
        max_el["weight"] = round(max_el["weight"] + diff, 2)
    return elements
