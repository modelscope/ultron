# Copyright (c) ModelScope Contributors. All rights reserved.
import unittest

from ultron.services.skill.taxonomy import (
    CATEGORY_DEFINITIONS,
    CATEGORY_TREE,
    KEYWORD_MAP,
    SOURCE_ONLY_SLUGS,
)


class TestTaxonomy(unittest.TestCase):
    def test_source_only_subset_of_definitions(self):
        for s in SOURCE_ONLY_SLUGS:
            self.assertIn(s, CATEGORY_DEFINITIONS)

    def test_category_tree_covers_definitions_keys(self):
        all_slugs = set(CATEGORY_DEFINITIONS)
        tree_slugs = set()
        for _dim, slugs in CATEGORY_TREE.items():
            tree_slugs.update(slugs)
        missing = all_slugs - tree_slugs
        self.assertEqual(missing, set(), msg=f"definitions not in tree: {missing}")

    def test_keyword_map_general_has_entries(self):
        self.assertIn("python", KEYWORD_MAP["general"])


if __name__ == "__main__":
    unittest.main()
