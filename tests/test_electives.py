"""
Tests for Open Electives Cross-Department Conflict Resolution and Interactive Editor.
"""

import unittest
from core.conflict_detector import ConflictDetector


class TestElectivesAndEditor(unittest.TestCase):
    def setUp(self):
        self.faculty = [
            {"name": "Dr. Rajesh Sharma", "department": "CSE", "designation": "Professor", "max_hours": 14},
            {"name": "Prof. Sneha Deshmukh", "department": "IT", "designation": "Assistant Professor", "max_hours": 18},
            {"name": "Dr. Vikram Gupta", "department": "AI-DS", "designation": "Professor", "max_hours": 14},
        ]
        self.rooms = [
            {"name": "LH-101", "room_type": "Lecture Hall", "capacity": 100},
            {"name": "LH-102", "room_type": "Lecture Hall", "capacity": 60},
            {"name": "LH-201", "room_type": "Lecture Hall", "capacity": 60},
        ]
        self.sections = [
            {"name": "CSE-A", "department": "CSE", "strength": 50},
            {"name": "IT-A", "department": "IT", "strength": 40},
            {"name": "MECH-A", "department": "MECH", "strength": 45},
        ]
        self.subjects = [
            {"code": "OE301", "name": "Intro to AI & ML", "department": "AI-DS", "is_lab": 0},
            {"code": "CS301", "name": "Operating Systems", "department": "CSE", "is_lab": 0},
            {"code": "IT301", "name": "Web Tech", "department": "IT", "is_lab": 0},
        ]
        self.elective_baskets = [
            {
                "basket_name": "Open Elective I",
                "course_code": "OE301",
                "course_name": "Intro to AI & ML",
                "sections": "CSE-A, IT-A, MECH-A",
                "capacity": 80
            }
        ]

    def test_cross_department_elective_clash_detected(self):
        """
        Students from CSE-A and IT-A are enrolled in OE301 on Monday 10:00 - 11:00.
        If CSE-A also has CS301 scheduled in their own department at the same time,
        ConflictDetector MUST flag a cross-department elective collision.
        """
        schedule = [
            # Open elective scheduled for mixed cohort
            {"id": 1, "faculty_name": "Dr. Vikram Gupta", "department": "AI-DS",
             "course_code": "OE301", "section": "Open-Cohort", "day": "Monday",
             "time_slot": "10:00 - 11:00", "room": "LH-101"},
            # Conflicting parallel class in CSE department for CSE-A
            {"id": 2, "faculty_name": "Dr. Rajesh Sharma", "department": "CSE",
             "course_code": "CS301", "section": "CSE-A", "day": "Monday",
             "time_slot": "10:00 - 11:00", "room": "LH-102"},
            # Non-conflicting class for IT-A at a different time
            {"id": 3, "faculty_name": "Prof. Sneha Deshmukh", "department": "IT",
             "course_code": "IT301", "section": "IT-A", "day": "Monday",
             "time_slot": "11:00 - 12:00", "room": "LH-201"},
        ]

        detector = ConflictDetector(
            faculty_catalog={f["name"]: f for f in self.faculty},
            rooms=self.rooms,
            sections=self.sections,
            subjects=self.subjects,
            elective_baskets=self.elective_baskets
        )
        report = detector.analyze_schedule(schedule)

        conflict_types = [c["type"] for c in report["conflicts_list"]]
        self.assertIn("ELECTIVE_SECTION_CLASH", conflict_types)

        # Check description mentions the enrolled section
        elective_conflicts = [c for c in report["conflicts_list"] if c["type"] == "ELECTIVE_SECTION_CLASH"]
        self.assertTrue(any("CSE-A" in c["description"] for c in elective_conflicts))

    def test_clean_cross_department_elective_schedule(self):
        """When elective is scheduled during an open slot with no parallel classes, zero clash is reported."""
        schedule = [
            {"id": 1, "faculty_name": "Dr. Vikram Gupta", "department": "AI-DS",
             "course_code": "OE301", "section": "Open-Cohort", "day": "Monday",
             "time_slot": "10:00 - 11:00", "room": "LH-101"},
            # CSE-A and IT-A have classes only at other times
            {"id": 2, "faculty_name": "Dr. Rajesh Sharma", "department": "CSE",
             "course_code": "CS301", "section": "CSE-A", "day": "Monday",
             "time_slot": "11:00 - 12:00", "room": "LH-102"},
            {"id": 3, "faculty_name": "Prof. Sneha Deshmukh", "department": "IT",
             "course_code": "IT301", "section": "IT-A", "day": "Monday",
             "time_slot": "12:00 - 01:00", "room": "LH-201"},
        ]
        detector = ConflictDetector(
            faculty_catalog={f["name"]: f for f in self.faculty},
            rooms=self.rooms,
            sections=self.sections,
            subjects=self.subjects,
            elective_baskets=self.elective_baskets
        )
        report = detector.analyze_schedule(schedule)
        self.assertEqual(report["critical_conflicts"], 0)


if __name__ == "__main__":
    unittest.main()
