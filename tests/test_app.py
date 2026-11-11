"""Tests for the web app (app.py) using Flask's built-in test client."""
import os
import tempfile

# Use a temporary database so the tests never touch your real data in data/
os.environ.setdefault("CLASHAUDIT_DB", os.path.join(tempfile.mkdtemp(prefix="clashaudit_test_"), "test.db"))
os.environ.setdefault("CLASHAUDIT_SECRET", "test-secret")

import re
import unittest

import app as webapp
from core import database as db


class AppTestCase(unittest.TestCase):
    def setUp(self):
        db.load_scenario("balanced")
        self.client = webapp.app.test_client()

    def token(self):
        """Read the CSRF token from a page, like a real browser form would."""
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
        self.client.post("/timetable/clear")  # no csrf_token -> must be ignored
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
                                             "leave_date": "2099-01-05", "reason": "Test"})  # a Monday
        html = self.client.get("/leave").get_data(as_text=True)
        self.assertIn("CS301", html)
        self.assertIn("Assign", html)
        db.execute("DELETE FROM leaves")


if __name__ == "__main__":
    unittest.main()
