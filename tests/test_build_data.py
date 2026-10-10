import math
import unittest
from datetime import datetime, timedelta, timezone

from scripts.build_data import build_strengths, model_fixture, saved_prediction, select_upcoming_gameweek


def match(number, gameweek, kickoff, home, away, result=None):
    return {
        "match_number": number,
        "round": gameweek,
        "date": kickoff,
        "home": home,
        "away": away,
        "result": result,
    }


class BuildDataTests(unittest.TestCase):
    def test_selects_only_nearest_upcoming_gameweek(self):
        now = datetime(2026, 10, 10, tzinfo=timezone.utc)
        rows = [
            match(1, 5, now - timedelta(days=1), "A", "B"),
            match(2, 6, now + timedelta(hours=1), "C", "D"),
            match(3, 6, now + timedelta(days=1), "E", "F"),
            match(4, 7, now + timedelta(days=7), "G", "H"),
        ]

        gameweek, upcoming = select_upcoming_gameweek(rows, now)

        self.assertEqual(gameweek, 6)
        self.assertEqual([row["match_number"] for row in upcoming], [2, 3])

    def test_completed_current_matches_feed_weighted_model(self):
        now = datetime(2026, 10, 10, tzinfo=timezone.utc)
        prior = [
            match(1, 1, now, "A", "B", (1, 0)),
            match(2, 1, now, "B", "A", (1, 1)),
            match(3, 2, now, "C", "A", (2, 1)),
            match(4, 2, now, "B", "C", (0, 2)),
        ]
        current = [match(5, 1, now, "A", "C", (3, 0))]

        strengths = build_strengths(prior, current)
        prediction = model_fixture(strengths, match(6, 2, now, "A", "B"))

        self.assertEqual(strengths["prior_matches"], 4)
        self.assertEqual(strengths["current_matches"], 1)
        self.assertTrue(math.isfinite(prediction["home_fair_decimal_odds"]))
        self.assertAlmostEqual(
            prediction["home_probability"] + prediction["draw_probability"] + prediction["away_probability"],
            1,
            places=5,
        )

    def test_saved_weekly_odds_override_a_fresh_prediction(self):
        fresh = {
            "home_pints": 1,
            "away_pints": 3,
            "home_probability": 0.7,
            "draw_probability": 0.2,
            "away_probability": 0.1,
            "home_fair_decimal_odds": 1.4,
            "draw_fair_decimal_odds": 5.0,
            "away_fair_decimal_odds": 10.0,
        }
        saved = {
            "homePints": 2,
            "awayPints": 1,
            "homeProbability": 0.3,
            "drawProbability": 0.3,
            "awayProbability": 0.4,
            "homeOdds": 3.33,
            "drawOdds": 3.33,
            "awayOdds": 2.5,
        }

        prediction = saved_prediction(saved, fresh)

        self.assertEqual(prediction["home_pints"], 2)
        self.assertEqual(prediction["away_fair_decimal_odds"], 2.5)


if __name__ == "__main__":
    unittest.main()
