"""
Tests for Lab Batch System in ClashAudit.
"""

import unittest
from core.conflict_detector import ConflictDetector


class TestLabBatchSystem(unittest.TestCase):
    def setUp(self):
        self.faculty = [
            {"name": "Dr. Amit Verma", "department": "CSE", "designation": "Assistant Professor", "max_hours": 18},
            {"name": "Dr. Priya Nair", "department": "CSE", "designation": "Assistant Professor", "max_hours": 18},
            {"name": "Prof. Ananya Iyer", "department": "CSE", "designation": "Associate Professor", "max_hours": 16},
        ]
        self.rooms = [
            {"name": "Lab-1", "room_type": "Lab", "capacity": 30},
            {"name": "Lab-2", "room_type": "Lab", "capacity": 30},
            {"name": "LH-101", "room_type": "Lecture Hall", "capacity": 60},
        ]
        self.sections = [
            {"name": "CSE-A", "department": "CSE", "strength": 60},
        ]
        self.subjects = [
            {"code": "CS305", "name": "Data Structures Lab", "department": "CSE", "is_lab": 1},
            {"code": "CS301", "name": "Operating Systems", "department": "CSE", "is_lab": 0},
        ]

    def test_parallel_distinct_lab_batches_allowed(self):
        """
        When CSE-A is split into Batch B1 (in Lab-1 with Dr. Amit)
        and Batch B2 (in Lab-2 with Dr. Priya) at the SAME time slot,
        it is completely valid and MUST NOT trigger a section clash!
        """
        schedule = [
            {"id": 1, "faculty_name": "Dr. Amit Verma", "department": "CSE",
             "course_code": "CS305", "section": "CSE-A", "batch": "B1",
             "day": "Monday", "time_slot": "09:00 - 10:00", "room": "Lab-1"},
            {"id": 2, "faculty_name": "Dr. Priya Nair", "department": "CSE",
             "course_code": "CS305", "section": "CSE-A", "batch": "B2",
             "day": "Monday", "time_slot": "09:00 - 10:00", "room": "Lab-2"},
        ]
        detector = ConflictDetector(
            faculty_catalog={f["name"]: f for f in self.faculty},
            rooms=self.rooms,
            sections=self.sections,
            subjects=self.subjects
        )
        report = detector.analyze_schedule(schedule)
        self.assertEqual(report["critical_conflicts"], 0, f"Unexpected conflicts: {report['conflicts_list']}")

    def test_same_lab_batch_double_booked_triggers_clash(self):
        """
        If the SAME batch B1 is assigned to two classes simultaneously,
        it MUST trigger a hard Section/Batch clash.
        """
        schedule = [
            {"id": 1, "faculty_name": "Dr. Amit Verma", "department": "CSE",
             "course_code": "CS305", "section": "CSE-A", "batch": "B1",
             "day": "Monday", "time_slot": "09:00 - 10:00", "room": "Lab-1"},
            {"id": 2, "faculty_name": "Dr. Priya Nair", "department": "CSE",
             "course_code": "CS305", "section": "CSE-A", "batch": "B1",
             "day": "Monday", "time_slot": "09:00 - 10:00", "room": "Lab-2"},
        ]
        detector = ConflictDetector(
            faculty_catalog={f["name"]: f for f in self.faculty},
            rooms=self.rooms,
            sections=self.sections,
            subjects=self.subjects
        )
        report = detector.analyze_schedule(schedule)
        types = [c["type"] for c in report["conflicts_list"]]
        self.assertIn("SECTION_CLASH", types)

    def test_entire_section_vs_sub_batch_triggers_clash(self):
        """
        If the entire section ('All') has a lecture while a sub-batch (B1) is in a lab,
        it MUST trigger a hard Section clash because students in B1 cannot be in two places.
        """
        schedule = [
            # Whole section lecture
            {"id": 1, "faculty_name": "Prof. Ananya Iyer", "department": "CSE",
             "course_code": "CS301", "section": "CSE-A", "batch": "All",
             "day": "Monday", "time_slot": "09:00 - 10:00", "room": "LH-101"},
            # Parallel sub-batch lab
            {"id": 2, "faculty_name": "Dr. Amit Verma", "department": "CSE",
             "course_code": "CS305", "section": "CSE-A", "batch": "B1",
             "day": "Monday", "time_slot": "09:00 - 10:00", "room": "Lab-1"},
        ]
        detector = ConflictDetector(
            faculty_catalog={f["name"]: f for f in self.faculty},
            rooms=self.rooms,
            sections=self.sections,
            subjects=self.subjects
        )
        report = detector.analyze_schedule(schedule)
        types = [c["type"] for c in report["conflicts_list"]]
        self.assertIn("SECTION_CLASH", types)


if __name__ == "__main__":
    unittest.main()
