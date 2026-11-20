
import unittest
from core import database as db
from core import exam_scheduler

class TestExamSupervision(unittest.TestCase):
    def setUp(self):
        db.init_db()
        db.execute("DELETE FROM exam_sessions")
        db.execute("DELETE FROM leaves")
        db.execute("DELETE FROM holidays")

    def test_multi_class_pooling_and_capacity(self):
        eid = db.add_exam_session(
            exam_date="2026-12-15",
            time_slot="09:30 - 12:30",
            session_title="Mid-Term Examination",
            course_code="CS301",
            course_name="Operating Systems",
            sections="CSE-A, CSE-B",
            room="LH-101",
            primary_supervisor="Dr. Rajesh Sharma",
            assistant_supervisor="Prof. Ananya Iyer",
            notes="Combined sitting"
        )
        self.assertIsNotNone(eid)

        session = db.get_exam_session(eid)
        self.assertEqual(session["total_students"], 120)
        self.assertIn("CSE-A", session["sections"])
        self.assertIn("CSE-B", session["sections"])

        report = exam_scheduler.check_exam_conflicts([session])
        self.assertTrue(any(c["type"] == "HALL_CAPACITY_OVERFLOW" for c in report["conflicts"]))

    def test_supervisor_double_booking_conflict(self):
        db.add_exam_session(
            exam_date="2026-12-15",
            time_slot="09:30 - 12:30",
            session_title="Mid-Term Examination",
            course_code="CS301",
            course_name="Operating Systems",
            sections="CSE-A",
            room="LH-101",
            primary_supervisor="Dr. Rajesh Sharma"
        )

        db.add_exam_session(
            exam_date="2026-12-15",
            time_slot="09:30 - 12:30",
            session_title="Mid-Term Examination",
            course_code="IT301",
            course_name="Web Technologies",
            sections="IT-A",
            room="LH-102",
            primary_supervisor="Dr. Rajesh Sharma"
        )

        report = exam_scheduler.check_exam_conflicts()
        self.assertTrue(any(c["type"] == "SUPERVISOR_CLASH" for c in report["conflicts"]))
        self.assertGreaterEqual(report["critical_count"], 1)

    def test_room_collision_conflict(self):
        db.add_exam_session(
            exam_date="2026-12-16",
            time_slot="14:00 - 17:00",
            session_title="End-Semester Exam",
            course_code="CS302",
            course_name="Database Systems",
            sections="CSE-A",
            room="LH-201",
            primary_supervisor="Prof. Ananya Iyer"
        )

        db.add_exam_session(
            exam_date="2026-12-16",
            time_slot="14:00 - 17:00",
            session_title="End-Semester Exam",
            course_code="AI301",
            course_name="Machine Learning",
            sections="AI-A",
            room="LH-201",
            primary_supervisor="Dr. Vikram Gupta"
        )

        report = exam_scheduler.check_exam_conflicts()
        self.assertTrue(any(c["type"] == "ROOM_DOUBLE_BOOKING" for c in report["conflicts"]))

    def test_section_exam_clash(self):
        db.add_exam_session(
            exam_date="2026-12-17",
            time_slot="09:30 - 12:30",
            session_title="Mid-Term",
            course_code="CS301",
            course_name="Operating Systems",
            sections="CSE-A",
            room="LH-101",
            primary_supervisor="Dr. Rajesh Sharma"
        )

        db.add_exam_session(
            exam_date="2026-12-17",
            time_slot="09:30 - 12:30",
            session_title="Mid-Term",
            course_code="CS303",
            course_name="Computer Networks",
            sections="CSE-A",
            room="LH-102",
            primary_supervisor="Dr. Amit Verma"
        )

        report = exam_scheduler.check_exam_conflicts()
        self.assertTrue(any(c["type"] == "SECTION_EXAM_CLASH" for c in report["conflicts"]))

    def test_supervisor_duty_stats(self):
        db.add_exam_session(
            exam_date="2026-12-18",
            time_slot="09:30 - 12:30",
            session_title="Mid-Term",
            course_code="CS301",
            course_name="Operating Systems",
            sections="CSE-A",
            room="LH-101",
            primary_supervisor="Dr. Rajesh Sharma",
            assistant_supervisor="Dr. Amit Verma"
        )

        summary = exam_scheduler.get_invigilation_roster_stats()
        self.assertEqual(summary["total_duties"], 2)
        stat_dict = {f["faculty_name"]: f for f in summary["stats"]}
        self.assertEqual(stat_dict["Dr. Rajesh Sharma"]["primary_duties"], 1)
        self.assertEqual(stat_dict["Dr. Amit Verma"]["assistant_duties"], 1)

if __name__ == "__main__":
    unittest.main()
