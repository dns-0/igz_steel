# SPDX-License-Identifier: GPL-3.0-or-later
import zipfile


def test_zip_contains_package_and_no_caches(tmp_path):
    from devtools.package import build_zip
    out = build_zip(tmp_path / "igz_steel.zip")
    names = zipfile.ZipFile(out).namelist()
    assert "igz_steel/__init__.py" in names
    assert "igz_steel/data/aisc_v16.json" in names
    assert "igz_steel/icons/tb_place.svg" in names
    assert "igz_steel/icons/tb_grid.svg" in names
    assert "igz_steel/LICENSE" in names and "igz_steel/README.md" in names
    assert not any("__pycache__" in n or n.endswith(".pyc") for n in names)
    assert not any(n.endswith(".xlsx") for n in names)
