import os
import tempfile

os.environ.setdefault("CHRONOS_DB", os.path.join(tempfile.mkdtemp(prefix="chronos_test_"), "test.db"))
os.environ.setdefault("CHRONOS_SECRET", "test-secret")

import re
import unittest

import app as webapp
from core import database as db

class AppTestCase(unittest.TestCase):
    def setUp(self):
        db.load_scenario("balanced")
        self.client = webapp.app.test_client()

    def token(self):
        html = self.client.get("/login").get_data(as_text=True)
        return re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)

    def login(self):
        return self.client.post("/login", data={"username": "admin", "password": "admin123",
                                                "csrf_token": self.token()})

class TestPublicPages(AppTestCase):
    def test_pages_open_without_login(self):
        for url in ["/", "/timetable", "/faculty", "/setup", "/reports", "/print",
                    "/print/section/CSE-A", "/charts/workload.png", "/download/report.xlsx"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_admin_pages_need_login(self):
        for url in ["/settings", "/leave", "/download/backup"]:
            self.assertEqual(self.client.get(url).status_code, 302, url)

    def test_report_api(self):
        data = self.client.get("/api/report").get_json()
        self.assertEqual(len(data["schedule"]), 16)
        self.assertEqual(data["report"]["total_conflicts"], 0)

class TestSecurity(AppTestCase):
    def test_wrong_password(self):
        self.client.post("/login", data={"username": "admin", "password": "nope", "csrf_token": self.token()})
        self.assertEqual(self.client.get("/settings").status_code, 302)

    def test_post_without_csrf_token_is_rejected(self):
        self.login()
        before = len(db.get_timetable())
        self.client.post("/timetable/clear")
        self.assertEqual(len(db.get_timetable()), before)

class TestAdminActions(AppTestCase):
    def test_add_clashing_class_shows_warning(self):
        self.login()
        response = self.client.post("/timetable/add", follow_redirects=True, data={
            "csrf_token": self.token(), "faculty_name": "Dr. Rajesh Sharma", "course_code": "CS301",
            "section": "CSE-B", "day": "Monday", "time_slot": "09:00 - 10:00", "room": "LH-102"})
        self.assertIn("Faculty Double-Booking", response.get_data(as_text=True))

    def test_apply_fix_removes_clash(self):
        self.login()
        db.load_scenario("collision")
        report = self.client.get("/api/report").get_json()["report"]
        for fix in report["suggestions"]:
            self.client.post("/api/resolve", headers={"X-CSRF-Token": self.token()},
                             json={"conflict_id": fix["conflict_id"], "entry_id": fix["entry_id"]})
        after = self.client.get("/api/report").get_json()["report"]
        self.assertEqual(after["total_conflicts"], 0)

    def test_cannot_delete_faculty_who_has_classes(self):
        self.login()
        self.client.post("/faculty/delete/Dr. Rajesh Sharma", data={"csrf_token": self.token()})
        self.assertIn("Dr. Rajesh Sharma", db.get_faculty_catalog())

    def test_leave_lists_substitutes(self):
        self.login()
        self.client.post("/leave/add", data={"csrf_token": self.token(), "faculty_name": "Dr. Rajesh Sharma",
                                             "leave_date": "2099-01-05", "reason": "Test"})
        html = self.client.get("/leave").get_data(as_text=True)
        self.assertIn("CS301", html)
        self.assertIn("Assign", html)
        db.execute("DELETE FROM leaves")

class TestInputValidation(AppTestCase):

    def test_holiday_with_bad_date_is_refused(self):
        self.login()
        before = len(db.get_holidays())
        self.client.post("/holidays/add", data={"csrf_token": self.token(), "holiday_date": "not-a-date",
                                                "name": "Fake day"})
        self.assertEqual(len(db.get_holidays()), before)

    def test_exam_with_unknown_room_or_same_supervisors_is_refused(self):
        self.login()
        base = {"csrf_token": self.token(), "exam_date": "2099-03-02", "time_slot": "Morning",
                "course_code": "CS301", "room": "LH-101", "sections": "CSE-A",
                "primary_supervisor": "Dr. Rajesh Sharma", "assistant_supervisor": ""}
        self.client.post("/exams/add", data={**base, "room": "No Such Room"})
        self.client.post("/exams/add", data={**base, "assistant_supervisor": "Dr. Rajesh Sharma"})
        self.client.post("/exams/add", data={**base, "primary_supervisor": "Nobody"})
        self.assertEqual(len(db.get_exam_sessions()), 0)
        self.client.post("/exams/add", data=base)
        self.assertEqual(len(db.get_exam_sessions()), 1)
        db.execute("DELETE FROM exam_sessions")

    def test_long_term_leave_for_unknown_faculty_is_refused(self):
        self.login()
        before = len(db.get_long_term_leaves())
        self.client.post("/leave/long-term/add", data={"csrf_token": self.token(), "faculty_name": "Ghost",
                                                       "start_date": "2099-01-01", "end_date": "2099-02-01"})
        self.assertEqual(len(db.get_long_term_leaves()), before)

    def test_edit_class_with_empty_fields_is_refused(self):
        self.login()
        entry = db.get_timetable()[0]
        self.client.post(f"/timetable/edit/{entry['id']}", data={"csrf_token": self.token()})
        self.assertEqual(db.get_entry(entry["id"])["faculty_name"], entry["faculty_name"])

    def test_predictor_rejects_negative_hours(self):
        response = self.client.post("/api/predict-stress", headers={"X-CSRF-Token": self.token()},
                                    json={"Designation": "Professor", "TeachingHours": -5})
        self.assertEqual(response.status_code, 400)

class TestErrorPages(AppTestCase):
    def test_unknown_page_shows_friendly_404(self):
        response = self.client.get("/this/does/not/exist")
        self.assertEqual(response.status_code, 404)
        self.assertIn("Page not found", response.get_data(as_text=True))

    def test_unknown_api_route_returns_json(self):
        response = self.client.get("/api/nothing-here")
        self.assertEqual(response.status_code, 404)
        self.assertIn("error", response.get_json())

    def test_drafts_page_is_public_but_hides_admin_buttons(self):
        html = self.client.get("/versions").get_data(as_text=True)
        self.assertNotIn("Save Draft Snapshot", html)

if __name__ == "__main__":
    unittest.main()
