"""
Tests for Automated Timetable Generator (CSP) and Continuous Lab Block Support.
"""

import unittest
from core.generator import TimetableGenerator
from core.conflict_detector import ConflictDetector


class TestGeneratorAndLabs(unittest.TestCase):
    def setUp(self):
        self.faculty = [
            {"name": "Dr. Rajesh Sharma", "department": "CSE", "designation": "Professor", "max_hours": 14},
            {"name": "Prof. Ananya Iyer", "department": "CSE", "designation": "Associate Professor", "max_hours": 16},
            {"name": "Dr. Amit Verma", "department": "CSE", "designation": "Assistant Professor", "max_hours": 18},
            {"name": "Dr. Suresh Patel", "department": "IT", "designation": "Associate Professor", "max_hours": 16},
        ]
        self.rooms = [
            {"name": "LH-101", "room_type": "Lecture Hall", "capacity": 60},
            {"name": "LH-102", "room_type": "Lecture Hall", "capacity": 60},
            {"name": "Lab-1", "room_type": "Lab", "capacity": 60},
            {"name": "Lab-2", "room_type": "Lab", "capacity": 60},
        ]
        self.sections = [
            {"name": "CSE-A", "department": "CSE", "strength": 50},
            {"name": "CSE-B", "department": "CSE", "strength": 50},
            {"name": "IT-A", "department": "IT", "strength": 40},
        ]
        self.subjects = [
            {"code": "CS301", "name": "Operating Systems", "department": "CSE", "is_lab": 0},
            {"code": "CS302", "name": "Database Systems", "department": "CSE", "is_lab": 0},
            {"code": "CS305", "name": "OS & DB Lab", "department": "CSE", "is_lab": 1},
            {"code": "IT301", "name": "Web Technologies", "department": "IT", "is_lab": 0},
            {"code": "IT305", "name": "Web Tech Lab", "department": "IT", "is_lab": 1},
        ]
        self.settings = {
            "working_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
            "time_slots": [
                "09:00 - 10:00", "10:00 - 11:00", "11:00 - 12:00", "12:00 - 01:00",
                "02:00 - 03:00", "03:00 - 04:00"
            ],
            "lunch_after": "12:00 - 01:00",
            "max_daily_hours": 5,
            "max_consecutive_hours": 3,
            "underload_percent": 65,
        }

    def test_generator_solves_zero_clash_schedule(self):
        """Test that generator produces a 100% collision-free timetable."""
        reqs = [
            {"section": "CSE-A", "course_code": "CS301", "hours_per_week": 3, "duration": 1},
            {"section": "CSE-A", "course_code": "CS302", "hours_per_week": 3, "duration": 1},
            {"section": "CSE-A", "course_code": "CS305", "hours_per_week": 2, "duration": 2},
            {"section": "CSE-B", "course_code": "CS301", "hours_per_week": 3, "duration": 1},
            {"section": "CSE-B", "course_code": "CS302", "hours_per_week": 3, "duration": 1},
            {"section": "CSE-B", "course_code": "CS305", "hours_per_week": 2, "duration": 2},
            {"section": "IT-A", "course_code": "IT301", "hours_per_week": 3, "duration": 1},
            {"section": "IT-A", "course_code": "IT305", "hours_per_week": 2, "duration": 2},
        ]
        gen = TimetableGenerator(self.faculty, self.rooms, self.sections, self.subjects, settings=self.settings)
        success, schedule, stats = gen.generate(reqs)

        self.assertTrue(success, f"Generator failed. Stats: {stats}")
        self.assertEqual(len(schedule), 21)

        # Validate with ConflictDetector
        detector = ConflictDetector(
            faculty_catalog={f["name"]: f for f in self.faculty},
            rooms=self.rooms,
            sections=self.sections,
            subjects=self.subjects,
            settings=self.settings
        )
        report = detector.analyze_schedule(schedule)
        self.assertEqual(report["critical_conflicts"], 0, f"Critical conflicts found: {report['conflicts_list']}")

    def test_multi_hour_lab_block_continuity(self):
        """Test that 2-hour lab blocks are strictly consecutive on the same day in the same room."""
        reqs = [
            {"section": "CSE-A", "course_code": "CS305", "hours_per_week": 2, "duration": 2},
            {"section": "IT-A", "course_code": "IT305", "hours_per_week": 2, "duration": 2},
        ]
        gen = TimetableGenerator(self.faculty, self.rooms, self.sections, self.subjects, settings=self.settings)
        success, schedule, _ = gen.generate(reqs)
        self.assertTrue(success)

        for sec, code in [("CSE-A", "CS305"), ("IT-A", "IT305")]:
            lab_entries = [e for e in schedule if e["section"] == sec and e["course_code"] == code]
            self.assertEqual(len(lab_entries), 2)
            self.assertEqual(lab_entries[0]["day"], lab_entries[1]["day"])
            self.assertEqual(lab_entries[0]["room"], lab_entries[1]["room"])
            self.assertEqual(lab_entries[0]["faculty_name"], lab_entries[1]["faculty_name"])

            # Verify consecutive time slots
            idx0 = self.settings["time_slots"].index(lab_entries[0]["time_slot"])
            idx1 = self.settings["time_slots"].index(lab_entries[1]["time_slot"])
            self.assertEqual(idx1 - idx0, 1)
            # Must not cross lunch
            self.assertNotEqual(lab_entries[0]["time_slot"], self.settings["lunch_after"])

    def test_conflict_detector_catches_split_or_fragmented_labs(self):
        """Test that ConflictDetector warns on non-contiguous or split-room labs."""
        detector = ConflictDetector(
            faculty_catalog={f["name"]: f for f in self.faculty},
            rooms=self.rooms,
            sections=self.sections,
            subjects=self.subjects,
            settings=self.settings
        )

        # 1. Fragmented lab (has 1 hour gap between 9-10 and 11-12)
        frag_schedule = [
            {"id": 1, "faculty_name": "Dr. Amit Verma", "department": "CSE", "course_code": "CS305",
             "section": "CSE-A", "day": "Monday", "time_slot": "09:00 - 10:00", "room": "Lab-1"},
            {"id": 2, "faculty_name": "Dr. Amit Verma", "department": "CSE", "course_code": "CS305",
             "section": "CSE-A", "day": "Monday", "time_slot": "11:00 - 12:00", "room": "Lab-1"},
        ]
        rep_frag = detector.analyze_schedule(frag_schedule)
        frag_types = [c["type"] for c in rep_frag["conflicts_list"]]
        self.assertIn("LAB_FRAGMENTED", frag_types)

        # 2. Split room lab
        split_schedule = [
            {"id": 1, "faculty_name": "Dr. Amit Verma", "department": "CSE", "course_code": "CS305",
             "section": "CSE-A", "day": "Monday", "time_slot": "09:00 - 10:00", "room": "Lab-1"},
            {"id": 2, "faculty_name": "Dr. Amit Verma", "department": "CSE", "course_code": "CS305",
             "section": "CSE-A", "day": "Monday", "time_slot": "10:00 - 11:00", "room": "Lab-2"},
        ]
        rep_split = detector.analyze_schedule(split_schedule)
        split_types = [c["type"] for c in rep_split["conflicts_list"]]
        self.assertIn("LAB_ROOM_SPLIT", split_types)


if __name__ == "__main__":
    unittest.main()
