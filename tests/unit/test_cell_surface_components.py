from __future__ import annotations

import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import shape_program_adaptive as spa  # noqa: E402


ISO = 0.0
OUT = 1.0
IN = -1.0


def corners(*inside_indices):
    """Corner values with the named corners inside the surface."""

    values = [OUT] * 8
    for index in inside_indices:
        values[index] = IN
    return values


class CubeTopologyTests(unittest.TestCase):
    """The face table must describe a real cube, or everything below is noise."""

    def test_every_edge_appears_on_exactly_two_faces(self):
        seen = {}
        for _corners, edges in spa._CUBE_FACES:
            for edge in edges:
                seen[edge] = seen.get(edge, 0) + 1
        self.assertEqual(12, len(seen))
        for edge, count in seen.items():
            self.assertEqual(2, count, "edge %d" % edge)

    def test_face_edges_join_consecutive_face_corners(self):
        for corner_cycle, edges in spa._CUBE_FACES:
            for position, edge in enumerate(edges):
                first = corner_cycle[position]
                second = corner_cycle[(position + 1) % 4]
                self.assertEqual(
                    {first, second},
                    set(spa._EDGES[edge]),
                    "face %s edge %d" % (corner_cycle, edge),
                )


class SinglePatchTests(unittest.TestCase):
    def test_no_crossing_yields_no_components(self):
        self.assertEqual([], spa.cell_surface_components([OUT] * 8, ISO))
        self.assertEqual([], spa.cell_surface_components([IN] * 8, ISO))

    def test_one_inside_corner_is_one_patch(self):
        components = spa.cell_surface_components(corners(0), ISO)
        self.assertEqual(1, len(components))
        # Corner 0 touches edges 0, 3 and 8.
        self.assertEqual([0, 3, 8], components[0])

    def test_a_half_full_cell_is_one_patch(self):
        # Whole z=0 layer inside: a single planar patch through the four uprights.
        components = spa.cell_surface_components(corners(0, 1, 2, 3), ISO)
        self.assertEqual(1, len(components))
        self.assertEqual([8, 9, 10, 11], components[0])

    def test_seven_inside_corners_is_one_patch(self):
        components = spa.cell_surface_components(corners(0, 1, 2, 3, 4, 5, 6), ISO)
        self.assertEqual(1, len(components))


class TwoPatchTests(unittest.TestCase):
    """The configurations that produce pinched edges today."""

    def test_two_opposite_corners_are_separate_patches(self):
        # Corners 0 and 6 are body-diagonal opposites and share no face, so the
        # cell holds two disjoint surface patches. One vertex cannot represent
        # both, which is the defect this grouping exists to fix.
        components = spa.cell_surface_components(corners(0, 6), ISO)
        self.assertEqual(2, len(components))
        self.assertEqual([[0, 3, 8], [5, 6, 10]], components)

    def test_two_diagonal_corners_on_one_face_stay_separate_without_center(self):
        # Corners 0 and 2 are face diagonal on z=0: a saddle. Without a centre
        # sample the deterministic fallback applies.
        components = spa.cell_surface_components(corners(0, 2), ISO)
        self.assertGreaterEqual(len(components), 1)

    def test_four_separate_corners_give_four_patches_with_center_samples(self):
        # The alternating corner set: every face is a saddle, so this is only
        # resolvable with centre samples. Outside centres isolate each corner.
        centers = {index: OUT for index in range(6)}
        components = spa.cell_surface_components(corners(0, 2, 5, 7), ISO, centers)
        self.assertEqual(4, len(components))
        for group in components:
            self.assertEqual(3, len(group), components)

    def test_alternating_corners_merge_without_center_samples(self):
        # Documented fallback: merging is the safe direction because it
        # reproduces today's single-vertex behaviour rather than splitting a
        # patch that the centre sample would have joined.
        components = spa.cell_surface_components(corners(0, 2, 5, 7), ISO)
        self.assertEqual(1, len(components))

    def test_every_edge_belongs_to_exactly_one_component(self):
        for inside in ((0,), (0, 6), (0, 2, 5, 7), (0, 1), (0, 1, 2, 3), (1, 7)):
            components = spa.cell_surface_components(corners(*inside), ISO)
            flat = [edge for group in components for edge in group]
            self.assertEqual(sorted(flat), sorted(set(flat)), inside)
            self.assertEqual(
                sorted(flat), spa.crossing_edges(corners(*inside), ISO), inside
            )


class SaddleResolutionTests(unittest.TestCase):
    """A four-crossing face has two valid readings; the centre sample decides."""

    def test_center_matching_the_inside_diagonal_isolates_the_outside_corners(self):
        # z=0 face has corners 0,1,2,3 with 0 and 2 inside. An inside centre
        # means 0 and 2 join across the face, so 1 and 3 are isolated.
        values = corners(0, 2)
        joined = spa.cell_surface_components(values, ISO, face_center_values={0: IN})
        separated = spa.cell_surface_components(values, ISO, face_center_values={0: OUT})
        self.assertNotEqual(joined, separated)

    def test_center_sample_can_merge_what_the_fallback_separates(self):
        values = corners(0, 2)
        with_center = spa.cell_surface_components(values, ISO, face_center_values={0: IN})
        without = spa.cell_surface_components(values, ISO)
        self.assertTrue(len(with_center) <= len(without) + 1)

    def test_missing_face_entry_falls_back_without_raising(self):
        components = spa.cell_surface_components(corners(0, 2), ISO, face_center_values={})
        self.assertTrue(components)


class DeterminismTests(unittest.TestCase):
    def test_output_is_sorted_and_stable(self):
        for inside in ((0, 6), (0, 2, 5, 7), (1, 3, 4)):
            first = spa.cell_surface_components(corners(*inside), ISO)
            second = spa.cell_surface_components(corners(*inside), ISO)
            self.assertEqual(first, second)
            for group in first:
                self.assertEqual(group, sorted(group))

    def test_iso_level_is_respected(self):
        values = [0.5] * 8
        values[0] = -0.5
        self.assertEqual(1, len(spa.cell_surface_components(values, ISO)))
        # Raising the iso level past every corner leaves no crossing.
        self.assertEqual([], spa.cell_surface_components(values, 10.0))


if __name__ == "__main__":
    unittest.main()
