"""Tests for core/file_io.py (reading uploaded CSV/Excel files)."""
import os
import tempfile

# Use a temporary database so the tests never touch your real data in data/
os.environ.setdefault("CLASHAUDIT_DB", os.path.join(tempfile.mkdtemp(prefix="clashaudit_test_"), "test.db"))
os.environ.setdefault("CLASHAUDIT_SECRET", "test-secret")

import io
import unittest

from werkzeug.datastructures import FileStorage

from core import file_io
from core.conflict_detector import DEFAULT_RULES


def upload(text, name="file.csv"):
    """Pretend a user uploaded a file with this text."""
    return FileStorage(stream=io.BytesIO(text.encode("utf-8")), filename=name)


class TestTimetableImport(unittest.TestCase):
    def test_good_rows_are_read_and_cleaned(self):
        csv = ("Teacher,Subject Code,Class,Day,Time,Room\n"
               "Dr. A,cs301,CSE-A,mon,9:00-10:00,LH-1\n")
        df = file_io.read_table(upload(csv))
        entries, errors = file_io.parse_timetable(df, DEFAULT_RULES, {}, [])
        self.assertEqual(errors, [])
        self.assertEqual(entries[0]["faculty_name"], "Dr. A")
        self.assertEqual(entries[0]["course_code"], "CS301")        # made upper-case
        self.assertEqual(entries[0]["day"], "Monday")               # 'mon' understood
        self.assertEqual(entries[0]["time_slot"], "09:00 - 10:00")  # matched to the official slot

    def test_single_subject_column_with_names(self):
        csv = ("Teacher,Subject,Class,Day,Time,Room\n"
               "Dr. A,Operating Systems,CSE-A,Monday,09:00 - 10:00,LH-1\n")
        subjects = [{"code": "CS301", "name": "Operating Systems", "department": "CSE", "is_lab": 0}]
        entries, errors = file_io.parse_timetable(file_io.read_table(upload(csv)), DEFAULT_RULES, {}, subjects)
        self.assertEqual(entries[0]["course_code"], "CS301")
        self.assertEqual(entries[0]["course_name"], "Operating Systems")

    def test_bad_rows_are_reported_with_row_number(self):
        csv = ("faculty_name,course_code,section,day,time_slot,room\n"
               "Dr. A,CS1,CSE-A,Sunday,09:00 - 10:00,LH-1\n"
               "Dr. B,CS1,,Monday,09:00 - 10:00,LH-1\n")
        entries, errors = file_io.parse_timetable(file_io.read_table(upload(csv)), DEFAULT_RULES, {}, [])
        self.assertEqual(entries, [])
        self.assertTrue(errors[0].startswith("Row 2"))
        self.assertTrue(errors[1].startswith("Row 3"))

    def test_missing_column(self):
        csv = "faculty_name,day\nDr. A,Monday\n"
        entries, errors = file_io.parse_timetable(file_io.read_table(upload(csv)), DEFAULT_RULES, {}, [])
        self.assertEqual(entries, [])
        self.assertIn("Missing column", errors[0])

    def test_wrong_file_type(self):
        with self.assertRaises(ValueError):
            file_io.read_table(upload("hello", name="notes.txt"))


class TestFacultyImport(unittest.TestCase):
    def test_designations_are_understood(self):
        csv = ("name,department,designation\n"
               "Dr. A,CSE,Asst. Prof\nDr. B,IT,assoc professor\nDr. C,IT,HOD\nDr. D,IT,Lecturer\n")
        rows, errors = file_io.parse_faculty(file_io.read_table(upload(csv)))
        self.assertEqual([r["designation"] for r in rows],
                         ["Assistant Professor", "Associate Professor", "Professor"])
        self.assertEqual(len(errors), 1)  # 'Lecturer' is not a known designation


if __name__ == "__main__":
    unittest.main()
