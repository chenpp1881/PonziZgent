
# -*- coding: utf-8 -*-
from typing import Dict, Any, Tuple

class InvariantResult:
    def __init__(self, name: str, satisfied: bool, certificate: Dict[str, Any]):
        self.name = name
        self.satisfied = satisfied
        self.certificate = certificate

    def to_json(self):
        return {
            "name": self.name,
            "satisfied": self.satisfied,
            "certificate": self.certificate
        }

class InvariantRegistry:
    """Extensible registry for invariants like I1, I2, I3; future I4, I5 can be added."""
    def __init__(self):
        self._inv = {}

    def register(self, name: str, fn):
        self._inv[name] = fn

    def run_all(self, mechanism: Dict[str, Any]) -> Dict[str, Any]:
        results = {}
        for k, fn in self._inv.items():
            r = fn(mechanism)
            results[k] = r.to_json()
        return results
