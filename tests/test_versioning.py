"""
Unit tests for Timetable Versioning, Visual Diff Engine, and Rollback History.
"""

import unittest
from core import database as db
from core.versioning import diff_timetables


class TestTimetableVersioning(unittest.TestCase):
    def setUp(self):
        db.init_db()
        db.execute("DELETE FROM timetable_versions")
        db.clear_timetable()

    def test_save_and_retrieve_version(self):
        """Test saving a named draft snapshot and reading it back."""
        db.add_entry({
            "faculty_name": "Dr. Rajesh Sharma",
            "department": "CSE",
            "course_code": "CS301",
            "course_name": "Operating Systems",
            "section": "CSE-A",
            "batch": "All",
            "day": "Monday",
            "time_slot": "09:00 - 10:00",
            "room": "LH-101"
        })

        vid = db.save_timetable_version(
            version_name="Draft v1 - Pre-Midterm",
            description="Initial baseline schedule",
            created_by="admin"
        )
        self.assertIsNotNone(vid)

        versions = db.get_timetable_versions()
        self.assertEqual(len(versions), 1)
        self.assertEqual(versions[0]["version_name"], "Draft v1 - Pre-Midterm")
        self.assertEqual(versions[0]["slot_count"], 1)

        ver = db.get_timetable_version(vid)
        self.assertIsNotNone(ver)
        self.assertEqual(len(ver["entries"]), 1)
        self.assertEqual(ver["entries"][0]["course_code"], "CS301")

    def test_visual_diff_engine(self):
        """Test detection of added, removed, modified, and unchanged slots."""
        old_slots = [
            # Slot 1: Unchanged
            {"day": "Monday", "time_slot": "09:00 - 10:00", "section": "CSE-A", "batch": "All",
             "course_code": "CS301", "faculty_name": "Dr. Rajesh Sharma", "room": "LH-101"},
            # Slot 2: Modified (Room changed)
            {"day": "Monday", "time_slot": "10:00 - 11:00", "section": "CSE-A", "batch": "All",
             "course_code": "CS302", "faculty_name": "Prof. Ananya Iyer", "room": "LH-101"},
            # Slot 3: Removed in new
            {"day": "Tuesday", "time_slot": "09:00 - 10:00", "section": "CSE-B", "batch": "All",
             "course_code": "CS303", "faculty_name": "Dr. Amit Verma", "room": "LH-102"}
        ]

        new_slots = [
            # Slot 1: Identical
            {"day": "Monday", "time_slot": "09:00 - 10:00", "section": "CSE-A", "batch": "All",
             "course_code": "CS301", "faculty_name": "Dr. Rajesh Sharma", "room": "LH-101"},
            # Slot 2: Room changed to LH-201
            {"day": "Monday", "time_slot": "10:00 - 11:00", "section": "CSE-A", "batch": "All",
             "course_code": "CS302", "faculty_name": "Prof. Ananya Iyer", "room": "LH-201"},
            # Slot 4: Newly added
            {"day": "Wednesday", "time_slot": "11:00 - 12:00", "section": "IT-A", "batch": "All",
             "course_code": "IT301", "faculty_name": "Dr. Suresh Patel", "room": "LH-103"}
        ]

        diff_res = diff_timetables(old_slots, new_slots)
        summary = diff_res["summary"]

        self.assertEqual(summary["unchanged"], 1)
        self.assertEqual(summary["modified"], 1)
        self.assertEqual(summary["removed"], 1)
        self.assertEqual(summary["added"], 1)
        self.assertEqual(summary["total_changes"], 3)

    def test_one_click_rollback(self):
        """Test rolling back the active schedule to a saved draft."""
        # 1. Populate initial schedule and save Draft 1
        db.add_entry({
            "faculty_name": "Dr. Rajesh Sharma",
            "department": "CSE",
            "course_code": "CS301",
            "course_name": "Operating Systems",
            "section": "CSE-A",
            "batch": "All",
            "day": "Monday",
            "time_slot": "09:00 - 10:00",
            "room": "LH-101"
        })
        v1_id = db.save_timetable_version("Draft v1 - Pre-Midterm")

        # 2. Modify active schedule: add second class and delete first
        db.clear_timetable()
        db.add_entry({
            "faculty_name": "Prof. Ananya Iyer",
            "department": "CSE",
            "course_code": "CS302",
            "course_name": "Database Systems",
            "section": "CSE-B",
            "batch": "All",
            "day": "Tuesday",
            "time_slot": "10:00 - 11:00",
            "room": "LH-201"
        })
        self.assertEqual(len(db.get_timetable()), 1)
        self.assertEqual(db.get_timetable()[0]["course_code"], "CS302")

        # 3. Rollback to Draft 1
        success, msg = db.rollback_timetable_version(v1_id)
        self.assertTrue(success)

        # 4. Active schedule should now match Draft 1 (CS301 on Monday)
        current = db.get_timetable()
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0]["course_code"], "CS301")
        self.assertEqual(current[0]["day"], "Monday")

    def test_delete_version(self):
        """Test deleting a saved draft."""
        vid = db.save_timetable_version("Draft To Delete")
        self.assertIsNotNone(db.get_timetable_version(vid))
        db.delete_timetable_version(vid)
        self.assertIsNone(db.get_timetable_version(vid))


if __name__ == "__main__":
    unittest.main()
