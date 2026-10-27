import os
from pathlib import Path


def binary_path():
    name = "tailwindcss.exe" if os.name == "nt" else "tailwindcss"
    return Path(__file__).parent / "bin" / name
