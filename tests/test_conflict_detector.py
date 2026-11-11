"""Tests for core/conflict_detector.py (no database needed)."""
import os
import tempfile

# Use a temporary database so the tests never touch your real data in data/
os.environ.setdefault("CLASHAUDIT_DB", os.path.join(tempfile.mkdtemp(prefix="clashaudit_test_"), "test.db"))
os.environ.setdefault("CLASHAUDIT_SECRET", "test-secret")

import unittest

from core.conflict_detector import ConflictDetector
from core.scenarios import SCENARIOS

CATALOG = {
    "Dr. A": {"designation": "Professor", "department": "CSE", "max_hours": 14},
    "Dr. B": {"designation": "Assistant Professor", "department": "CSE", "max_hours": 18},
    "Dr. C": {"designation": "Assistant Professor", "department": "CSE", "max_hours": 3},
}
ROOMS = [
    {"name": "LH-1", "room_type": "Lecture Hall", "capacity": 60},
    {"name": "LH-2", "room_type": "Lecture Hall", "capacity": 30},
    {"name": "LAB-1", "room_type": "Lab", "capacity": 60},
]
SECTIONS = [{"name": "CSE-A", "department": "CSE", "strength": 60},
            {"name": "CSE-B", "department": "CSE", "strength": 60}]
SUBJECTS = [{"code": "CS1", "name": "Maths", "department": "CSE", "is_lab": 0},
            {"code": "CS2", "name": "Physics", "department": "CSE", "is_lab": 0},
            {"code": "CS9", "name": "Python Lab", "department": "CSE", "is_lab": 1}]


def cls(i, faculty, section, day, slot, room, code="CS1"):
    return {"id": i, "faculty_name": faculty, "department": "CSE", "course_code": code,
            "course_name": "", "section": section, "day": day, "time_slot": slot, "room": room}


def make_detector(faculty_subjects=None):
    return ConflictDetector(CATALOG, ROOMS, SECTIONS, SUBJECTS, faculty_subjects or {})


def types_of(report):
    return [c["type"] for c in report["conflicts_list"]]


class TestHardConflicts(unittest.TestCase):
    def test_clean_timetable_has_no_conflicts(self):
        schedule = [cls(1, "Dr. A", "CSE-A", "Monday", "09:00 - 10:00", "LH-1"),
                    cls(2, "Dr. B", "CSE-B", "Monday", "09:00 - 10:00", "LAB-1")]
        report = make_detector().analyze_schedule(schedule)
        self.assertEqual(report["total_conflicts"], 0)

    def test_faculty_double_booking(self):
        schedule = [cls(1, "Dr. A", "CSE-A", "Monday", "09:00 - 10:00", "LH-1"),
                    cls(2, "Dr. A", "CSE-B", "Monday", "09:00 - 10:00", "LAB-1")]
        report = make_detector().analyze_schedule(schedule)
        self.assertIn("FACULTY_TIME_CLASH", types_of(report))
        self.assertEqual(report["critical_conflicts"], 1)

    def test_room_double_booking(self):
        schedule = [cls(1, "Dr. A", "CSE-A", "Monday", "09:00 - 10:00", "LH-1"),
                    cls(2, "Dr. B", "CSE-B", "Monday", "09:00 - 10:00", "LH-1")]
        self.assertIn("ROOM_DOUBLE_BOOKING", types_of(make_detector().analyze_schedule(schedule)))

    def test_section_clash(self):
        schedule = [cls(1, "Dr. A", "CSE-A", "Monday", "09:00 - 10:00", "LH-1"),
                    cls(2, "Dr. B", "CSE-A", "Monday", "09:00 - 10:00", "LAB-1")]
        self.assertIn("SECTION_CLASH", types_of(make_detector().analyze_schedule(schedule)))


class TestWarnings(unittest.TestCase):
    def test_four_classes_in_a_row_is_fatigue(self):
        slots = ["09:00 - 10:00", "10:00 - 11:00", "11:00 - 12:00", "12:00 - 01:00"]
        schedule = [cls(i, "Dr. B", "CSE-A", "Monday", s, "LH-1") for i, s in enumerate(slots)]
        self.assertIn("CONSECUTIVE_FATIGUE", types_of(make_detector().analyze_schedule(schedule)))

    def test_lunch_break_resets_the_streak(self):
        # 11-12, 12-1, (lunch), 2-3, 3-4  -> longest run is only 2, so no warning
        slots = ["11:00 - 12:00", "12:00 - 01:00", "02:00 - 03:00", "03:00 - 04:00"]
        schedule = [cls(i, "Dr. B", "CSE-A", "Monday", s, "LH-1") for i, s in enumerate(slots)]
        self.assertNotIn("CONSECUTIVE_FATIGUE", types_of(make_detector().analyze_schedule(schedule)))

    def test_weekly_overload(self):
        days = ["Monday", "Tuesday", "Wednesday", "Thursday"]
        schedule = [cls(i, "Dr. C", "CSE-A", d, "09:00 - 10:00", "LH-1") for i, d in enumerate(days)]
        report = make_detector().analyze_schedule(schedule)
        self.assertIn("WEEKLY_OVERLOAD", types_of(report))
        status = {w["faculty_name"]: w["status"] for w in report["workload_distribution"]}
        self.assertEqual(status["Dr. C"], "Overloaded")

    def test_lab_in_lecture_hall(self):
        schedule = [cls(1, "Dr. B", "CSE-A", "Monday", "09:00 - 10:00", "LH-1", code="CS9")]
        self.assertIn("LAB_ROOM_MISMATCH", types_of(make_detector().analyze_schedule(schedule)))

    def test_room_too_small(self):
        schedule = [cls(1, "Dr. B", "CSE-A", "Monday", "09:00 - 10:00", "LH-2")]  # 60 students, 30 seats
        self.assertIn("ROOM_TOO_SMALL", types_of(make_detector().analyze_schedule(schedule)))

    def test_not_qualified(self):
        schedule = [cls(1, "Dr. B", "CSE-A", "Monday", "09:00 - 10:00", "LH-1")]
        report = make_detector({"CS1": ["Dr. A"]}).analyze_schedule(schedule)
        self.assertIn("NOT_QUALIFIED", types_of(report))

    def test_unknown_faculty_and_bad_slot(self):
        schedule = [cls(1, "Dr. Nobody", "CSE-A", "Monday", "7am", "LH-1")]
        found = types_of(make_detector().analyze_schedule(schedule))
        self.assertIn("UNKNOWN_FACULTY", found)
        self.assertIn("INVALID_SLOT", found)


class TestSuggestions(unittest.TestCase):
    def test_substitute_is_free_and_qualified(self):
        schedule = [cls(1, "Dr. A", "CSE-A", "Monday", "09:00 - 10:00", "LH-1"),
                    cls(2, "Dr. A", "CSE-B", "Monday", "09:00 - 10:00", "LAB-1")]
        report = make_detector({"CS1": ["Dr. A", "Dr. C"]}).analyze_schedule(schedule)
        fix = report["suggestions"][0]
        self.assertEqual(fix["action"], "REASSIGN_FACULTY")
        self.assertEqual(fix["recommended_faculty"], "Dr. C")  # qualified one is preferred

    def test_free_room_is_really_free(self):
        # LH-1 is double-booked, and LAB-1 is also busy -> only a lecture hall that fits may be suggested
        schedule = [cls(1, "Dr. A", "CSE-A", "Monday", "09:00 - 10:00", "LH-1"),
                    cls(2, "Dr. B", "CSE-B", "Monday", "09:00 - 10:00", "LH-1")]
        report = make_detector().analyze_schedule(schedule)
        fix = report["suggestions"][0]
        self.assertEqual(fix["action"], "CHANGE_ROOM")
        self.assertEqual(fix["recommended_room"], "LAB-1")  # LH-2 is too small for 60 students

    def test_section_clash_suggests_a_free_slot(self):
        schedule = [cls(1, "Dr. A", "CSE-A", "Monday", "09:00 - 10:00", "LH-1"),
                    cls(2, "Dr. B", "CSE-A", "Monday", "09:00 - 10:00", "LAB-1")]
        fix = make_detector().analyze_schedule(schedule)["suggestions"][0]
        self.assertEqual(fix["action"], "MOVE_SLOT")
        self.assertNotEqual((fix["recommended_day"], fix["recommended_slot"]), ("Monday", "09:00 - 10:00"))


class TestBalanceIndex(unittest.TestCase):
    def test_uses_utilization_not_raw_hours(self):
        # Same % of cap for both teachers -> perfectly balanced even though hours differ
        catalog = {"P": {"designation": "Professor", "department": "X", "max_hours": 10},
                   "Q": {"designation": "Assistant Professor", "department": "X", "max_hours": 20}}
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        slots = ["09:00 - 10:00", "10:00 - 11:00"]
        schedule = [cls(f"p{d}", "P", "S1", d, "09:00 - 10:00", "R") for d in days]
        schedule += [cls(f"q{d}{s}", "Q", "S2", d, s, "R2") for d in days for s in slots]
        report = ConflictDetector(catalog).analyze_schedule(schedule)
        self.assertEqual(report["workload_balance_score"], 100.0)


class TestDemoScenarios(unittest.TestCase):
    def setUp(self):
        from core import database as db
        self.detector = ConflictDetector(
            {name: {"designation": d, "department": dept, "max_hours": {"Professor": 14,
             "Associate Professor": 16, "Assistant Professor": 18}[d]} for name, dept, d in db.DEMO_FACULTY},
            [{"name": n, "room_type": t, "capacity": c} for n, t, c in db.DEMO_ROOMS],
            [{"name": n, "department": d, "strength": s} for n, d, s in db.DEMO_SECTIONS],
            [{"code": c, "name": n, "department": d, "is_lab": l} for c, n, d, l in db.DEMO_SUBJECTS],
            {code: [f for f, codes in db.DEMO_FACULTY_SUBJECTS.items() if code in codes]
             for code, *_ in db.DEMO_SUBJECTS},
        )

    def test_scenario_a_is_clean(self):
        self.assertEqual(self.detector.analyze_schedule(SCENARIOS["balanced"]["schedule"])["total_conflicts"], 0)

    def test_scenario_b_has_three_hard_clashes(self):
        report = self.detector.analyze_schedule(SCENARIOS["collision"]["schedule"])
        self.assertEqual(report["critical_conflicts"], 3)

    def test_scenario_c_has_overload_and_fatigue(self):
        found = types_of(self.detector.analyze_schedule(SCENARIOS["overload"]["schedule"]))
        self.assertIn("WEEKLY_OVERLOAD", found)
        self.assertIn("CONSECUTIVE_FATIGUE", found)


if __name__ == "__main__":
    unittest.main()
