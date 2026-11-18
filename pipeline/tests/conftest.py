import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DATA = RAIZ / "data"  # rutas absolutas: los tests no dependen del cwd
sys.path.insert(0, str(RAIZ))
