"""
Database layer for ClashAudit.

We use SQLite, which comes built into Python (import sqlite3), so nothing extra
has to be installed. All data lives in ONE file: data/clashaudit.db

Tables
------
users             -> admin login accounts (passwords are stored hashed)
faculty           -> teachers: name, department, designation, weekly hour cap
rooms             -> lecture halls and labs with seating capacity
sections          -> student classes/batches (e.g. CSE-A) with strength
subjects          -> courses (e.g. CS301 Operating Systems), lab or theory
faculty_subjects  -> which faculty member can teach which subject
timetable         -> the weekly timetable (one row = one class in one slot)
leaves            -> faculty leave on a particular date
substitutions     -> who is taking a class when the regular teacher is on leave
settings          -> college rules (time slots, working days, limits ...)
"""

import os
import sqlite3
from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "data", "clashaudit.db")

# The database file can be changed (tests use a temporary file).
DB_PATH = os.environ.get("CLASHAUDIT_DB", DEFAULT_DB_PATH)

DESIGNATIONS = ["Professor", "Associate Professor", "Assistant Professor"]
ROOM_TYPES = ["Lecture Hall", "Lab"]
ALL_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

# Every setting is saved as text in the settings table.
DEFAULT_SETTINGS = {
    "college_name": "Our College",
    "working_days": "Monday,Tuesday,Wednesday,Thursday,Friday",
    "time_slots": "09:00 - 10:00,10:00 - 11:00,11:00 - 12:00,12:00 - 01:00,"
                  "02:00 - 03:00,03:00 - 04:00,04:00 - 05:00",
    "lunch_after": "12:00 - 01:00",     # lunch break comes right after this slot
    "max_daily_hours": "5",             # warn if a teacher has more classes in a day
    "max_consecutive_hours": "3",       # warn if a teacher has more back-to-back classes
    "cap_professor": "14",              # AICTE / UGC weekly caps
    "cap_associate": "16",
    "cap_assistant": "18",
    "underload_percent": "65",          # below this % of cap = underloaded
}


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------
def get_connection():
    """Open the database. Rows behave like dictionaries (row['name'])."""
    folder = os.path.dirname(DB_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def query(sql, params=()):
    """Run a SELECT and return a list of plain dicts."""
    conn = get_connection()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def execute(sql, params=()):
    """Run INSERT / UPDATE / DELETE. Returns the id of the inserted row."""
    conn = get_connection()
    cur = conn.execute(sql, params)
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


# ---------------------------------------------------------------------------
# Creating the tables
# ---------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username      TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS faculty (
    name        TEXT PRIMARY KEY,
    department  TEXT NOT NULL,
    designation TEXT NOT NULL,
    max_hours   INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS rooms (
    name      TEXT PRIMARY KEY,
    room_type TEXT NOT NULL,
    capacity  INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sections (
    name       TEXT PRIMARY KEY,
    department TEXT NOT NULL,
    strength   INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS subjects (
    code       TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    department TEXT NOT NULL,
    is_lab     INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS faculty_subjects (
    faculty_name TEXT NOT NULL,
    course_code  TEXT NOT NULL,
    PRIMARY KEY (faculty_name, course_code)
);
CREATE TABLE IF NOT EXISTS timetable (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    faculty_name TEXT NOT NULL,
    department   TEXT NOT NULL,
    course_code  TEXT NOT NULL,
    course_name  TEXT,
    section      TEXT NOT NULL,
    day          TEXT NOT NULL,
    time_slot    TEXT NOT NULL,
    room         TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS leaves (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    faculty_name TEXT NOT NULL,
    leave_date   TEXT NOT NULL,
    reason       TEXT
);
CREATE TABLE IF NOT EXISTS substitutions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    leave_id        INTEGER NOT NULL,
    timetable_id    INTEGER NOT NULL,
    substitute_name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS elective_baskets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    basket_name  TEXT NOT NULL,
    course_code  TEXT NOT NULL,
    course_name  TEXT,
    sections     TEXT NOT NULL,
    capacity     INTEGER NOT NULL DEFAULT 60
);
"""


def init_db(seed_demo_data=True):
    """Create tables (if missing) and fill in starting data the first time."""
    conn = get_connection()
    conn.executescript(SCHEMA)

    # Default settings: only add keys that are not already saved
    for key, value in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))

    # Default admin account (the app reminds you to change this password)
    has_user = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if has_user == 0:
        conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                     ("admin", generate_password_hash("admin123")))
    conn.commit()

    has_faculty = conn.execute("SELECT COUNT(*) FROM faculty").fetchone()[0]
    conn.close()

    if seed_demo_data and has_faculty == 0:
        seed_master_data()
        load_scenario("balanced")


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
def get_settings():
    """Return settings as proper Python types (lists and numbers)."""
    raw = dict(DEFAULT_SETTINGS)
    for row in query("SELECT key, value FROM settings"):
        raw[row["key"]] = row["value"]

    return {
        "college_name": raw["college_name"],
        "working_days": [d.strip() for d in raw["working_days"].split(",") if d.strip()],
        "time_slots": [s.strip() for s in raw["time_slots"].split(",") if s.strip()],
        "lunch_after": raw["lunch_after"].strip(),
        "max_daily_hours": int(raw["max_daily_hours"]),
        "max_consecutive_hours": int(raw["max_consecutive_hours"]),
        "caps": {
            "Professor": int(raw["cap_professor"]),
            "Associate Professor": int(raw["cap_associate"]),
            "Assistant Professor": int(raw["cap_assistant"]),
        },
        "underload_percent": int(raw["underload_percent"]),
    }


def save_setting(key, value):
    execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))


def cap_for(designation):
    """Weekly hour cap for a designation (taken from settings)."""
    return get_settings()["caps"].get(designation, 16)


# ---------------------------------------------------------------------------
# Faculty
# ---------------------------------------------------------------------------
def get_faculty():
    return query("SELECT * FROM faculty ORDER BY department, name")


def get_faculty_catalog():
    """Faculty in the format the conflict detector expects: {name: {...}}"""
    return {f["name"]: {"designation": f["designation"],
                        "department": f["department"],
                        "max_hours": f["max_hours"]} for f in get_faculty()}


def save_faculty(name, department, designation, max_hours=None):
    """Add a new faculty member, or update an existing one with the same name."""
    if not max_hours:
        max_hours = cap_for(designation)
    execute("INSERT OR REPLACE INTO faculty (name, department, designation, max_hours) "
            "VALUES (?, ?, ?, ?)", (name.strip(), department.strip(), designation, int(max_hours)))


def delete_faculty(name):
    execute("DELETE FROM faculty WHERE name = ?", (name,))
    execute("DELETE FROM faculty_subjects WHERE faculty_name = ?", (name,))


def count_classes_of(faculty_name):
    return query("SELECT COUNT(*) AS n FROM timetable WHERE faculty_name = ?",
                 (faculty_name,))[0]["n"]


# ---------------------------------------------------------------------------
# Rooms, sections, subjects
# ---------------------------------------------------------------------------
def get_rooms():
    return query("SELECT * FROM rooms ORDER BY room_type, name")


def save_room(name, room_type, capacity):
    execute("INSERT OR REPLACE INTO rooms (name, room_type, capacity) VALUES (?, ?, ?)",
            (name.strip(), room_type, int(capacity)))


def delete_room(name):
    execute("DELETE FROM rooms WHERE name = ?", (name,))


def get_sections():
    return query("SELECT * FROM sections ORDER BY department, name")


def save_section(name, department, strength):
    execute("INSERT OR REPLACE INTO sections (name, department, strength) VALUES (?, ?, ?)",
            (name.strip(), department.strip(), int(strength)))


def delete_section(name):
    execute("DELETE FROM sections WHERE name = ?", (name,))


def get_subjects():
    return query("SELECT * FROM subjects ORDER BY department, code")


def save_subject(code, name, department, is_lab):
    execute("INSERT OR REPLACE INTO subjects (code, name, department, is_lab) VALUES (?, ?, ?, ?)",
            (code.strip().upper(), name.strip(), department.strip(), 1 if is_lab else 0))


def delete_subject(code):
    execute("DELETE FROM subjects WHERE code = ?", (code,))
    execute("DELETE FROM faculty_subjects WHERE course_code = ?", (code,))


def get_departments():
    """All department names used anywhere (for dropdowns)."""
    rows = query("SELECT department FROM faculty UNION SELECT department FROM sections "
                 "UNION SELECT department FROM subjects ORDER BY department")
    return [r["department"] for r in rows]


# ---------------------------------------------------------------------------
# Which faculty can teach which subject
# ---------------------------------------------------------------------------
def get_faculty_subjects():
    """Return {course_code: [faculty names who can teach it]}"""
    mapping = {}
    for row in query("SELECT * FROM faculty_subjects"):
        mapping.setdefault(row["course_code"], []).append(row["faculty_name"])
    return mapping


def get_subjects_of(faculty_name):
    rows = query("SELECT course_code FROM faculty_subjects WHERE faculty_name = ?", (faculty_name,))
    return [r["course_code"] for r in rows]


def set_subjects_of(faculty_name, course_codes):
    execute("DELETE FROM faculty_subjects WHERE faculty_name = ?", (faculty_name,))
    for code in course_codes:
        execute("INSERT OR IGNORE INTO faculty_subjects (faculty_name, course_code) VALUES (?, ?)",
                (faculty_name, code))


# ---------------------------------------------------------------------------
# Timetable
# ---------------------------------------------------------------------------
TIMETABLE_FIELDS = ["faculty_name", "department", "course_code", "course_name",
                    "section", "day", "time_slot", "room"]


def get_timetable():
    """All classes, sorted by day and then by time slot order."""
    settings = get_settings()
    day_order = {d: i for i, d in enumerate(ALL_DAYS)}
    slot_order = {s: i for i, s in enumerate(settings["time_slots"])}
    rows = query("SELECT * FROM timetable")
    rows.sort(key=lambda r: (day_order.get(r["day"], 99), slot_order.get(r["time_slot"], 99),
                             r["section"]))
    return rows


def get_entry(entry_id):
    rows = query("SELECT * FROM timetable WHERE id = ?", (entry_id,))
    return rows[0] if rows else None


def add_entry(entry):
    values = [str(entry.get(f, "") or "").strip() for f in TIMETABLE_FIELDS]
    return execute("INSERT INTO timetable (faculty_name, department, course_code, course_name, "
                   "section, day, time_slot, room) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", values)


def update_entry(entry_id, entry):
    values = [str(entry.get(f, "") or "").strip() for f in TIMETABLE_FIELDS]
    execute("UPDATE timetable SET faculty_name=?, department=?, course_code=?, course_name=?, "
            "section=?, day=?, time_slot=?, room=? WHERE id=?", values + [entry_id])


def delete_entry(entry_id):
    execute("DELETE FROM timetable WHERE id = ?", (entry_id,))
    execute("DELETE FROM substitutions WHERE timetable_id = ?", (entry_id,))


def clear_timetable():
    execute("DELETE FROM timetable")
    execute("DELETE FROM substitutions")


# ---------------------------------------------------------------------------
# Leaves and substitutions
# ---------------------------------------------------------------------------
def get_leaves():
    return query("SELECT * FROM leaves ORDER BY leave_date DESC, faculty_name")


def get_leave(leave_id):
    rows = query("SELECT * FROM leaves WHERE id = ?", (leave_id,))
    return rows[0] if rows else None


def add_leave(faculty_name, leave_date, reason):
    return execute("INSERT INTO leaves (faculty_name, leave_date, reason) VALUES (?, ?, ?)",
                   (faculty_name, leave_date, reason.strip()))


def delete_leave(leave_id):
    execute("DELETE FROM leaves WHERE id = ?", (leave_id,))
    execute("DELETE FROM substitutions WHERE leave_id = ?", (leave_id,))


def get_substitutions():
    return query("SELECT * FROM substitutions")


def assign_substitute(leave_id, timetable_id, substitute_name):
    # Only one substitute per class per leave: remove any old choice first
    execute("DELETE FROM substitutions WHERE leave_id = ? AND timetable_id = ?",
            (leave_id, timetable_id))
    execute("INSERT INTO substitutions (leave_id, timetable_id, substitute_name) VALUES (?, ?, ?)",
            (leave_id, timetable_id, substitute_name))


def remove_substitute(leave_id, timetable_id):
    execute("DELETE FROM substitutions WHERE leave_id = ? AND timetable_id = ?",
            (leave_id, timetable_id))


# ---------------------------------------------------------------------------
# Open Electives & Cross-Department Baskets
# ---------------------------------------------------------------------------
def get_elective_baskets():
    return query("SELECT * FROM elective_baskets ORDER BY basket_name, course_code")


def get_elective_basket(basket_id):
    rows = query("SELECT * FROM elective_baskets WHERE id = ?", (basket_id,))
    return rows[0] if rows else None


def save_elective_basket(basket_name, course_code, course_name, sections, capacity=60):
    execute("INSERT INTO elective_baskets (basket_name, course_code, course_name, sections, capacity) "
            "VALUES (?, ?, ?, ?, ?)",
            (basket_name.strip(), course_code.strip().upper(), course_name.strip(),
             sections.strip(), int(capacity)))


def delete_elective_basket(basket_id):
    execute("DELETE FROM elective_baskets WHERE id = ?", (basket_id,))


# ---------------------------------------------------------------------------
# Demo / starting data
# ---------------------------------------------------------------------------
DEMO_FACULTY = [
    ("Dr. Rajesh Sharma", "CSE", "Professor"),
    ("Prof. Ananya Iyer", "CSE", "Associate Professor"),
    ("Dr. Amit Verma", "CSE", "Assistant Professor"),
    ("Dr. Priya Nair", "CSE", "Assistant Professor"),
    ("Dr. Suresh Patel", "IT", "Associate Professor"),
    ("Prof. Sneha Deshmukh", "IT", "Assistant Professor"),
    ("Dr. Vikram Gupta", "AI-DS", "Professor"),
    ("Dr. Pooja Menon", "AI-DS", "Assistant Professor"),
]

DEMO_ROOMS = [
    ("LH-101", "Lecture Hall", 72), ("LH-102", "Lecture Hall", 72),
    ("LH-103", "Lecture Hall", 72), ("LH-201", "Lecture Hall", 72),
    ("LH-202", "Lecture Hall", 72), ("LH-203", "Lecture Hall", 72),
    ("LH-301", "Lecture Hall", 72),
    ("Lab-1", "Lab", 60), ("Lab-2", "Lab", 60),
]

DEMO_SECTIONS = [
    ("CSE-A", "CSE", 60), ("CSE-B", "CSE", 60),
    ("IT-A", "IT", 60), ("AI-A", "AI-DS", 60),
]

DEMO_SUBJECTS = [
    ("CS301", "Operating Systems", "CSE", 0),
    ("CS302", "Database Systems", "CSE", 0),
    ("CS303", "Computer Networks", "CSE", 0),
    ("CS304", "Algorithms", "CSE", 0),
    ("CS305", "Data Structures Lab", "CSE", 1),
    ("CS306", "Network Lab", "CSE", 1),
    ("IT301", "Web Technologies", "IT", 0),
    ("IT302", "Cloud Computing", "IT", 0),
    ("AI301", "Machine Learning", "AI-DS", 0),
    ("AI302", "Deep Learning", "AI-DS", 0),
]

DEMO_FACULTY_SUBJECTS = {
    "Dr. Rajesh Sharma": ["CS301", "CS302"],
    "Prof. Ananya Iyer": ["CS302", "CS301", "CS304"],
    "Dr. Amit Verma": ["CS303", "CS306", "CS301"],
    "Dr. Priya Nair": ["CS304", "CS305", "CS301", "CS303"],
    "Dr. Suresh Patel": ["IT301", "IT302"],
    "Prof. Sneha Deshmukh": ["IT302", "IT301"],
    "Dr. Vikram Gupta": ["AI301", "AI302"],
    "Dr. Pooja Menon": ["AI302", "AI301"],
}


def seed_master_data():
    """Fill faculty, rooms, sections and subjects with sample data."""
    for name, dept, desig in DEMO_FACULTY:
        save_faculty(name, dept, desig)
    for name, rtype, cap in DEMO_ROOMS:
        save_room(name, rtype, cap)
    for name, dept, strength in DEMO_SECTIONS:
        save_section(name, dept, strength)
    for code, name, dept, is_lab in DEMO_SUBJECTS:
        save_subject(code, name, dept, is_lab)
    for fac, codes in DEMO_FACULTY_SUBJECTS.items():
        set_subjects_of(fac, codes)


def load_scenario(key):
    """Replace the timetable with one of the demo scenarios."""
    from core.scenarios import SCENARIOS
    clear_timetable()
    for entry in SCENARIOS[key]["schedule"]:
        add_entry(entry)
