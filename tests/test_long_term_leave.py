"""
Tests for Long-Term Leave & Maternity Cover Planner.
"""

import unittest
from core import database as db


class TestLongTermLeave(unittest.TestCase):
    def setUp(self):
        db.init_db()
        db.execute("DELETE FROM long_term_leaves")
        db.execute("DELETE FROM long_term_covers")

    def test_create_long_term_maternity_cover_plan(self):
        """Test creating an extended 6-month maternity cover plan."""
        lid = db.add_long_term_leave(
            faculty_name="Prof. Ananya Iyer",
            leave_type="Maternity Leave",
            start_date="2026-12-01",
            end_date="2027-05-31",
            notes="6-month maternity sabbatical"
        )
        self.assertIsNotNone(lid)

        leaves = db.get_long_term_leaves()
        self.assertTrue(any(l["id"] == lid for l in leaves))

        # Assign designated cover faculty
        db.assign_long_term_cover(lid, timetable_id=101, cover_faculty_name="Dr. Priya Nair")
        covers = db.get_long_term_covers()
        self.assertTrue(any(c["cover_faculty_name"] == "Dr. Priya Nair" for c in covers))

        # Delete plan and verify cascade
        db.delete_long_term_leave(lid)
        remaining_covers = db.get_long_term_covers()
        self.assertFalse(any(c["long_term_leave_id"] == lid for c in remaining_covers))


if __name__ == "__main__":
    unittest.main()
