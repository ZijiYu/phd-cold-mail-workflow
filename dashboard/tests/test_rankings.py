import unittest

from dashboard.app import rankings


class RankingTests(unittest.TestCase):
    def test_names_people_write_resolve(self):
        cases = {
            "UC Davis": "Univ. of California - Davis",
            "UIUC": "Univ. of Illinois at Urbana-Champaign",
            "University of Illinois Urbana-Champaign (UIUC)": "Univ. of Illinois at Urbana-Champaign",
            "UT Austin": "University of Texas at Austin",
            "Georgia Tech": "Georgia Institute of Technology",
            "Penn State University": "Pennsylvania State University",
            "Rochester Institute of Technology": "Rochester Inst. of Technology",
            "Stony Brook University": "Stony Brook University",
        }
        for written, full in cases.items():
            with self.subTest(written=written):
                r = rankings.lookup(written)
                self.assertIsNotNone(r)
                self.assertEqual(r["name"], full)
                self.assertIsInstance(r["cs"], int)

    def test_unknown_school_is_unranked(self):
        self.assertIsNone(rankings.lookup("Lakeview University"))
        self.assertIsNone(rankings.lookup(""))

    def test_similar_names_stay_apart(self):
        self.assertNotEqual(rankings.lookup("University of Rochester")["name"],
                            rankings.lookup("Rochester Institute of Technology")["name"])
        self.assertNotEqual(rankings.lookup("Boston University")["name"], rankings.lookup("Boston College")["name"])

    def test_meta_describes_source(self):
        m = rankings.meta()
        self.assertIn("CSRankings", m["source"])
        self.assertRegex(m["years"], r"^\d{4}-\d{4}$")


if __name__ == "__main__":
    unittest.main()
