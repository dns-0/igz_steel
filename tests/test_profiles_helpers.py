# SPDX-License-Identifier: GPL-3.0-or-later
import math

import pytest

from igz_steel._profiles import (Loop, circle_loop, polygon_centroid,
                                 reverse_loop, round_corners, signed_area)

SQUARE = [(0, 0), (2, 0), (2, 2), (0, 2)]


def test_signed_area_and_centroid():
    assert signed_area(SQUARE) == pytest.approx(4.0)
    assert signed_area(list(reversed(SQUARE))) == pytest.approx(-4.0)
    assert polygon_centroid(SQUARE) == pytest.approx((1.0, 1.0))


def test_round_corners_without_radius_keeps_points():
    loop = round_corners([(u, v, 0.0) for u, v in SQUARE])
    assert loop.points == [(0, 0), (2, 0), (2, 2), (0, 2)]
    assert loop.arc_edges == set()


def test_round_corners_rounds_a_convex_corner():
    corners = [(0, 0, 0.0), (2, 0, 0.5), (2, 2, 0.0), (0, 2, 0.0)]
    loop = round_corners(corners, segs=4)
    # corner (2,0) replaced by 5 arc points from (1.5,0) to (2,0.5)
    assert len(loop.points) == 3 + 5
    assert loop.points[1] == pytest.approx((1.5, 0.0))
    assert loop.points[5] == pytest.approx((2.0, 0.5))
    centre = (1.5, 0.5)
    for p in loop.points[1:6]:
        assert math.hypot(p[0] - centre[0], p[1] - centre[1]) == pytest.approx(0.5)
    assert loop.arc_edges == {1, 2, 3, 4}
    # area lost by rounding one corner: r^2 (1 - pi/4); a 4-segment arc loses ~0.13 % more
    assert signed_area(loop.points) == pytest.approx(4.0 - 0.25 * (1 - math.pi / 4), rel=2e-3)


def test_round_corners_rounds_a_concave_corner_and_keeps_winding():
    # an L: concave corner at (1,1)
    corners = [(0, 0, 0), (2, 0, 0), (2, 1, 0), (1, 1, 0.25), (1, 2, 0), (0, 2, 0)]
    loop = round_corners(corners, segs=4)
    assert signed_area(loop.points) > 0
    # a concave fillet ADDS material: r^2 (1 - pi/4)
    assert signed_area(loop.points) == pytest.approx(3.0 + 0.0625 * (1 - math.pi / 4), rel=2e-3)
    assert loop.arc_edges == {3, 4, 5, 6}


def test_round_corners_skips_a_fillet_that_does_not_fit():
    corners = [(0, 0, 0), (1, 0, 5.0), (1, 1, 0), (0, 1, 0)]
    loop = round_corners(corners)
    assert loop.points == [(0, 0), (1, 0), (1, 1), (0, 1)]
    assert loop.arc_edges == set()


def test_reverse_loop_remaps_arc_edges():
    loop = Loop([(0, 0), (1, 0), (1, 1), (0, 1)], {1})   # edge (1,0)->(1,1)
    rev = reverse_loop(loop)
    assert rev.points == [(0, 1), (1, 1), (1, 0), (0, 0)]
    assert rev.arc_edges == {1}                         # (1,1)->(1,0), same edge
    assert signed_area(rev.points) < 0


def test_circle_loop():
    loop = circle_loop(1.0, 8)
    assert len(loop.points) == 8 and loop.arc_edges == set(range(8))
    assert signed_area(loop.points) > 0
    assert loop.points[0] == pytest.approx((1.0, 0.0))
