import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from upload_warehouse_excel.normalize import (  # noqa: E402
    SIN_UBICAR,
    build_pallet,
    norm_import,
    norm_pallet_raw,
    norm_text,
    ubicacion_key,
)


def test_norm_text():
    assert norm_text(None) is None
    assert norm_text("  P1   fragancia  ") == "P1 FRAGANCIA"
    assert norm_text("") is None


def test_norm_import():
    assert norm_import("IMPO 118-26 NORTHCASTLE") == "118-26 NORTHCASTLE"
    assert norm_import("impo  099-25   max factor ") == "099-25 MAX FACTOR"
    assert norm_import(None) is None


def test_build_pallet():
    assert build_pallet(3, "MAQUILLAJE") == "P3 MAQUILLAJE"
    assert build_pallet(3.0, "maquillaje ") == "P3 MAQUILLAJE"
    assert build_pallet("P1 MAQUILLAJE ", None) == "P1 MAQUILLAJE"
    assert build_pallet(None, None) is None


def test_ubicacion_key_null():
    assert ubicacion_key(None) == SIN_UBICAR
    assert ubicacion_key("  ") == SIN_UBICAR
    assert ubicacion_key("r01-12-05") == "R01-12-05"


def test_pallet_trailing_space():
    assert norm_pallet_raw("P26 FRAGANCIA ") == "P26 FRAGANCIA"


if __name__ == "__main__":
    test_norm_text()
    test_norm_import()
    test_build_pallet()
    test_ubicacion_key_null()
    test_pallet_trailing_space()
    print("normalize: 5 tests OK")
