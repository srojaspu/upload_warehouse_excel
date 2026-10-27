import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from upload_warehouse_excel.load_ubicacion import (  # noqa: E402
    _INSERT_CHUNK,
    _TARGET_TABLE,
    _multi_row_insert_sql,
)


def test_target_table_is_ubicacionlote():
    assert _TARGET_TABLE == "dbo.UbicacionLote"


def test_multi_row_placeholders():
    sql = _multi_row_insert_sql(3)
    assert sql.count("(:e") == 3
    for j in range(3):
        for prefix in ("e", "p", "c", "u"):
            assert f":{prefix}{j}" in sql
    assert _TARGET_TABLE in sql
    assert sql.count("VALUES") == 1


def test_chunk_within_param_limit():
    assert _INSERT_CHUNK * 4 < 2100


if __name__ == "__main__":
    test_target_table_is_ubicacionlote()
    test_multi_row_placeholders()
    test_chunk_within_param_limit()
    print("multi-row: 3 tests OK")
