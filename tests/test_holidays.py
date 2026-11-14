"""
Tests for Institutional Holidays and Calendar System.
"""
import unittest
from core import database as db


class TestHolidays(unittest.TestCase):
    def setUp(self):
        db.init_db()
        db.execute("DELETE FROM holidays")

    def test_add_and_query_holiday(self):
        """Test adding an institutional holiday and querying it."""
        db.add_holiday(
            holiday_date="2026-10-02",
            name="Gandhi Jayanti",
            holiday_type="National",
            description="National Holiday - Institute closed"
        )
        holidays = db.get_holidays()
        self.assertEqual(len(holidays), 1)
        self.assertEqual(holidays[0]["name"], "Gandhi Jayanti")
        self.assertEqual(holidays[0]["holiday_date"], "2026-10-02")
        self.assertEqual(holidays[0]["holiday_type"], "National")

        # Test get_holiday by date
        h = db.get_holiday("2026-10-02")
        self.assertIsNotNone(h)
        self.assertEqual(h["name"], "Gandhi Jayanti")

    def test_delete_holiday(self):
        """Test deleting a holiday."""
        db.add_holiday(
            holiday_date="2026-12-25",
            name="Christmas",
            holiday_type="Festival",
            description="Winter Break"
        )
        h = db.get_holiday("2026-12-25")
        self.assertIsNotNone(h)
        db.delete_holiday(h["id"])
        self.assertIsNone(db.get_holiday("2026-12-25"))


if __name__ == "__main__":
    unittest.main()
