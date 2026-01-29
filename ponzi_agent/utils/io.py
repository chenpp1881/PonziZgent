
# -*- coding: utf-8 -*-
import hashlib
from pathlib import Path

def read_all_sol_files(src_path: Path):
    if src_path.is_file():
        return [src_path] if src_path.suffix.lower()==".sol" else []
    return sorted(list(src_path.rglob("*.sol")))

def build_line_numbered_text(path: Path):
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return [f"{i+1:06d}: {lines[i]}" for i in range(len(lines))]

def sha1_of_line(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()
