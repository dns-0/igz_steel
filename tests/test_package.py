# SPDX-License-Identifier: GPL-3.0-or-later
def test_package_key():
    import igz_steel
    assert igz_steel.KEY == "igz_steel"
    assert igz_steel.EXT_VERSION == 1
