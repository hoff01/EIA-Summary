from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def inside_root(path: Path) -> Path:
    resolved = path.resolve()
    root = ROOT.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"refusing path outside dashboard folder: {resolved}")
    return resolved


def ensure_dirs() -> None:
    for name in ["archive", "output", "config", "reference", "logs"]:
        inside_root(ROOT / name).mkdir(parents=True, exist_ok=True)
