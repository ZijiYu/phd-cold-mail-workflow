import unittest

from dashboard.app import rankings


class RankingTests(unittest.TestCase):
    def test_names_people_write_resolve(self):
        cases = {
            "UC Davis": "University of California--Davis",
            "UIUC": "University of Illinois--Urbana-Champaign",
            "University of Illinois Urbana-Champaign (UIUC)": "University of Illinois--Urbana-Champaign",
            "UT Austin": "University of Texas--Austin",
            "University of Texas at Dallas": "University of Texas--Dallas",
            "Georgia Tech": "Georgia Institute of Technology",
            "Penn State University": "Pennsylvania State University--University Park",
            "Stony Brook University": "Stony Brook University--SUNY",
            "University at Buffalo": "University at Buffalo--SUNY",
            "Rutgers University": "Rutgers University--New Brunswick",
            "Purdue University": "Purdue University--West Lafayette",
        }
        for written, full in cases.items():
            with self.subTest(written=written):
                r = rankings.lookup(written)
                self.assertIsNotNone(r)
                self.assertEqual(r["name"], full)
                self.assertIsInstance(r["rank"], int)

    def test_unknown_school_is_unranked(self):
        self.assertIsNone(rankings.lookup("Lakeview University"))
        self.assertIsNone(rankings.lookup(""))

    def test_similar_names_stay_apart(self):
        self.assertNotEqual(rankings.lookup("University of Rochester")["name"],
                            rankings.lookup("Rochester Institute of Technology")["name"])
        self.assertNotEqual(rankings.lookup("University of Illinois Chicago")["name"], rankings.lookup("UIUC")["name"])

    def test_meta_describes_source(self):
        m = rankings.meta()
        self.assertIn("U.S. News", m["source"])
        self.assertTrue(m["edition"])


if __name__ == "__main__":
    unittest.main()
