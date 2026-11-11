"""
ClashAudit - terminal demo (no browser needed).

    python demo_cli.py              -> runs the demo "clashes" timetable
    python demo_cli.py my_file.csv  -> checks your own timetable file (CSV or Excel)
"""

import os
import sys
import joblib
import pandas as pd

from core import database as db
from core import file_io
from core.conflict_detector import ConflictDetector, DEFAULT_RULES
from core.scenarios import SCENARIOS

CAPS = {"Professor": 14, "Associate Professor": 16, "Assistant Professor": 18}


def demo_detector():
    """A detector filled with the sample faculty, rooms, sections and subjects."""
    catalog = {name: {"designation": d, "department": dept, "max_hours": CAPS[d]}
               for name, dept, d in db.DEMO_FACULTY}
    rooms = [{"name": n, "room_type": t, "capacity": c} for n, t, c in db.DEMO_ROOMS]
    sections = [{"name": n, "department": d, "strength": s} for n, d, s in db.DEMO_SECTIONS]
    subjects = [{"code": c, "name": n, "department": d, "is_lab": lab} for c, n, d, lab in db.DEMO_SUBJECTS]
    mapping = {}
    for faculty, codes in db.DEMO_FACULTY_SUBJECTS.items():
        for code in codes:
            mapping.setdefault(code, []).append(faculty)
    return ConflictDetector(catalog, rooms, sections, subjects, mapping), catalog, subjects


class FileFromDisk:
    """Lets file_io.read_table() read a file from disk like an uploaded file."""
    def __init__(self, path):
        self.filename = path
        self._f = open(path, "rb")

    def read(self, *args):
        return self._f.read(*args)

    def __getattr__(self, name):
        return getattr(self._f, name)


def print_report(schedule, report):
    print(f"  Classes analysed      : {len(schedule)}")
    print(f"  Hard conflicts        : {report['critical_conflicts']}")
    print(f"  Warnings              : {report['warning_conflicts']}")
    print(f"  Workload Balance Index: {report['workload_balance_score']}%")

    if report["conflicts_list"]:
        print("\n[PROBLEMS FOUND]")
        for c in report["conflicts_list"]:
            print(f"  [{c['badge']}] {c['title']} ({c['day']} {c['time_slot']})")
            print(f"     {c['description']}")
    if report["suggestions"]:
        print("\n[SUGGESTED FIXES]")
        for s in report["suggestions"]:
            print(f"  -> {s['action']}: {s['reason']}")


def main():
    print("=" * 72)
    print("   CLASHAUDIT: FACULTY WORKLOAD DISTRIBUTION & CONFLICT DETECTOR")
    print("=" * 72)
    detector, catalog, subjects = demo_detector()

    if len(sys.argv) > 1:
        path = sys.argv[1]
        print(f"\n[STEP 1] Checking your file: {path}")
        entries, errors = file_io.parse_timetable(file_io.read_table(FileFromDisk(path)),
                                                  DEFAULT_RULES, catalog, subjects)
        for e in errors:
            print(f"  skipped -> {e}")
        # Faculty from your file are not in the sample list, so only check clashes & limits
        schedule = [dict(e, id=i + 1) for i, e in enumerate(entries)]
        report = ConflictDetector(faculty_catalog={}).analyze_schedule(schedule)
    else:
        print("\n[STEP 1] Demo timetable with clashes:")
        schedule = SCENARIOS["collision"]["schedule"]
        report = detector.analyze_schedule(schedule)
    print_report(schedule, report)

    print("\n" + "-" * 72)
    print("[STEP 2] Machine learning burnout-risk prediction:")
    model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "model", "workload_model.joblib")
    if not os.path.exists(model_path):
        print("  Model file not found. Run: python model/train.py")
    else:
        pipe = joblib.load(model_path)
        sample = pd.DataFrame([{"Designation": "Assistant Professor", "TeachingHours": 16, "LabHours": 8,
                                "AdminHours": 2, "ResearchHours": 1, "UniqueCourses": 3, "DaysTaught": 5}])
        labels = ["Underloaded", "Balanced", "Overloaded (High Burnout Risk)"]
        pred = int(pipe.predict(sample)[0])
        prob = pipe.predict_proba(sample)[0][pred]
        print("  Assistant Professor: 16 lecture + 8 lab + 2 admin + 1 research = 27 hrs/week (cap 18)")
        print(f"  Prediction: {labels[pred]}  (confidence {prob * 100:.1f}%)")

    print("\n" + "=" * 72)
    print("Web dashboard: python app.py  ->  http://127.0.0.1:5000")
    print("=" * 72)


if __name__ == "__main__":
    main()
