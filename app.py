"""
ClashAudit - Faculty Workload Distribution & Conflict Detector
Flask web application.

Run:  python app.py      then open  http://127.0.0.1:5000

Anyone can VIEW the dashboard, timetable, reports and printable timetables.
Changing anything (adding classes, faculty, settings, leave ...) needs the admin login.
"""

import io
import os
import json
import secrets
from collections import defaultdict
from datetime import date
from functools import wraps

import joblib
import pandas as pd
from flask import (Flask, request, jsonify, render_template, redirect, url_for, flash,
                   session, send_file, abort)
from werkzeug.security import check_password_hash, generate_password_hash

from core import database as db
from core import file_io, reports
from core.conflict_detector import ConflictDetector
from core.generator import TimetableGenerator
from core.scenarios import SCENARIOS
from core.substitutes import classes_missed, substitute_options, weekday_of

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "model", "workload_model.joblib")
METADATA_PATH = os.path.join(BASE_DIR, "model", "model_metadata.json")
SECRET_KEY_PATH = os.path.join(BASE_DIR, "data", "secret_key.txt")

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # uploads up to 5 MB


def load_secret_key():
    """Flask needs a secret key to keep people logged in. We create one the first
    time and save it in data/ (that folder is not uploaded to GitHub)."""
    os.makedirs(os.path.dirname(SECRET_KEY_PATH), exist_ok=True)
    if not os.path.exists(SECRET_KEY_PATH):
        with open(SECRET_KEY_PATH, "w") as f:
            f.write(secrets.token_hex(32))
    with open(SECRET_KEY_PATH) as f:
        return f.read().strip()


app.secret_key = os.environ.get("CLASHAUDIT_SECRET") or load_secret_key()
db.init_db()

# ---------------------------------------------------------------------------
# Machine learning model (burnout risk predictor)
# ---------------------------------------------------------------------------
def load_model():
    """Load the saved model. If it is missing, or was saved with a different
    scikit-learn version (this happens on a new computer), train it again."""
    import warnings
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            model = joblib.load(MODEL_PATH)
        if not any("InconsistentVersion" in type(w.message).__name__ for w in caught):
            return model
        print("[INFO] Model was saved with another scikit-learn version. Retraining...")
    except Exception as e:
        print(f"[INFO] Could not load the model ({e}). Training it now...")
    try:
        from model.train import train
        train()
        return joblib.load(MODEL_PATH)
    except Exception as e:
        print(f"[ERROR] Training failed: {e}. The burnout predictor will be disabled.")
        return None


ml_pipeline = load_model()
model_meta = {}

try:
    with open(METADATA_PATH, "r", encoding="utf-8") as f:
        model_meta = json.load(f)
except Exception as e:
    print(f"[ERROR] Failed to load model metadata: {e}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def make_detector():
    """Build a conflict detector using the latest data in the database."""
    return ConflictDetector(
        faculty_catalog=db.get_faculty_catalog(),
        rooms=db.get_rooms(),
        sections=db.get_sections(),
        subjects=db.get_subjects(),
        faculty_subjects=db.get_faculty_subjects(),
        settings=db.get_settings(),
        elective_baskets=db.get_elective_baskets(),
    )


def run_analysis():
    timetable = db.get_timetable()
    report = make_detector().analyze_schedule(timetable)
    return timetable, report


def is_admin():
    return session.get("user") is not None


def login_required(view):
    """Put @login_required above a route to allow only the logged-in admin."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not is_admin():
            if request.path.startswith("/api/"):
                return jsonify({"error": "Please log in as admin."}), 401
            flash("Please log in to make changes.", "warning")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapper


def csrf_token():
    """A random token put in every form. A request from another website will not
    know it, so it cannot submit forms on our behalf (CSRF protection)."""
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


@app.before_request
def check_csrf():
    if request.method == "POST" and app.config.get("CSRF_CHECK", True):
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not sent or sent != session.get("csrf"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Session expired. Please reload the page."}), 400
            flash("Your session expired. Please try again.", "error")
            return redirect(request.referrer or url_for("home"))


@app.context_processor
def template_globals():
    """Variables available in every HTML template."""
    password_changed = db.query("SELECT value FROM settings WHERE key = 'admin_password_changed'")
    return {
        "is_admin": is_admin(),
        "csrf_token": csrf_token,
        "settings": db.get_settings(),
        "default_password": is_admin() and not password_changed,
    }


def form_int(name, default=0):
    try:
        return int(request.form.get(name, default))
    except (TypeError, ValueError):
        return default


def entry_from_form():
    """Read the add/edit class form and fill in department and course name."""
    code = request.form.get("course_code", "").strip().upper()
    faculty = request.form.get("faculty_name", "").strip()
    subject = next((s for s in db.get_subjects() if s["code"] == code), {})
    faculty_info = db.get_faculty_catalog().get(faculty, {})
    return {
        "faculty_name": faculty,
        "course_code": code,
        "course_name": subject.get("name", request.form.get("course_name", "")),
        "department": subject.get("department") or faculty_info.get("department", "General"),
        "section": request.form.get("section", "").strip(),
        "batch": request.form.get("batch", "All").strip() or "All",
        "day": request.form.get("day", "").strip(),
        "time_slot": request.form.get("time_slot", "").strip(),
        "room": request.form.get("room", "").strip(),
    }


def flash_conflicts_for(entry_id):
    """After adding/editing a class, tell the user straight away if it causes a problem."""
    _, report = run_analysis()
    problems = [c for c in report["conflicts_list"] if entry_id in c.get("involved_entries", [])]
    for c in problems:
        flash(f"Check this: {c['title']} - {c['description']}",
              "error" if c["severity"] == "CRITICAL" else "warning")
    return problems


def form_choices():
    """Lists used in the dropdowns of the class form."""
    return {
        "faculty": db.get_faculty(),
        "subjects": db.get_subjects(),
        "sections": db.get_sections(),
        "rooms": db.get_rooms(),
    }


# ---------------------------------------------------------------------------
# Login / logout / password
# ---------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = db.query("SELECT * FROM users WHERE username = ?", (username,))
        if user and check_password_hash(user[0]["password_hash"], password):
            session["user"] = username
            flash(f"Welcome, {username}.", "success")
            next_page = request.args.get("next", "")
            # only allow redirects inside our own site
            return redirect(next_page if next_page.startswith("/") and not next_page.startswith("//")
                            else url_for("home"))
        flash("Wrong username or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("user", None)
    flash("Logged out.", "success")
    return redirect(url_for("home"))


@app.route("/account/password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current = request.form.get("current", "")
        new = request.form.get("new", "")
        confirm = request.form.get("confirm", "")
        user = db.query("SELECT * FROM users WHERE username = ?", (session["user"],))[0]
        if not check_password_hash(user["password_hash"], current):
            flash("Current password is wrong.", "error")
        elif len(new) < 8:
            flash("New password must be at least 8 characters.", "error")
        elif new != confirm:
            flash("The two new passwords do not match.", "error")
        else:
            db.execute("UPDATE users SET password_hash = ? WHERE username = ?",
                       (generate_password_hash(new), session["user"]))
            db.save_setting("admin_password_changed", "1")
            flash("Password changed.", "success")
            return redirect(url_for("home"))
    return render_template("password.html")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@app.route("/")
def home():
    return render_template("index.html", model_meta=model_meta)


# ---------------------------------------------------------------------------
# Timetable
# ---------------------------------------------------------------------------
@app.route("/timetable")
def timetable_page():
    timetable, report = run_analysis()

    # Which rows have a problem? (to colour them in the table)
    row_status = {}
    for c in report["conflicts_list"]:
        for eid in c.get("involved_entries", []):
            if c["severity"] == "CRITICAL" or row_status.get(eid) != "CRITICAL":
                row_status[eid] = c["severity"]

    # Simple filters from the URL, e.g. /timetable?day=Monday
    filters = {k: request.args.get(k, "") for k in ["day", "faculty", "section", "room"]}
    rows = [e for e in timetable
            if (not filters["day"] or e["day"] == filters["day"])
            and (not filters["faculty"] or e["faculty_name"] == filters["faculty"])
            and (not filters["section"] or e["section"] == filters["section"])
            and (not filters["room"] or e["room"] == filters["room"])]

    return render_template("timetable.html", rows=rows, total=len(timetable),
                           row_status=row_status, filters=filters, **form_choices())


@app.route("/timetable/add", methods=["POST"])
@login_required
def timetable_add():
    entry = entry_from_form()
    if not all([entry["faculty_name"], entry["course_code"], entry["section"],
                entry["day"], entry["time_slot"], entry["room"]]):
        flash("Please fill in every field.", "error")
        return redirect(url_for("timetable_page"))

    duration = form_int("duration", 1)
    if duration <= 1:
        new_id = db.add_entry(entry)
        if not flash_conflicts_for(new_id):
            flash(f"Added {entry['course_code']} ({entry['section']}) on {entry['day']} {entry['time_slot']}. "
                  f"No conflicts.", "success")
    else:
        # Multi-hour continuous block: find consecutive slots
        settings = db.get_settings()
        time_slots = settings.get("time_slots", [])
        lunch_after = settings.get("lunch_after", "")
        start_slot = entry["time_slot"]
        if start_slot not in time_slots:
            flash(f"Invalid starting time slot '{start_slot}'.", "error")
            return redirect(url_for("timetable_page"))

        start_idx = time_slots.index(start_slot)
        if start_idx + duration > len(time_slots):
            flash(f"Cannot schedule a {duration}-hour block starting at {start_slot}: exceeds daily schedule.", "error")
            return redirect(url_for("timetable_page"))

        consecutive_slots = time_slots[start_idx:start_idx + duration]
        # Check if lunch break is crossed inside the block
        crosses_lunch = False
        for s in consecutive_slots[:-1]:
            if s == lunch_after:
                crosses_lunch = True
                break
        if crosses_lunch:
            flash(f"A {duration}-hour continuous block cannot cross the lunch break ({lunch_after}).", "error")
            return redirect(url_for("timetable_page"))

        added_ids = []
        for s in consecutive_slots:
            slot_entry = dict(entry)
            slot_entry["time_slot"] = s
            added_ids.append(db.add_entry(slot_entry))

        any_problems = False
        for eid in added_ids:
            if flash_conflicts_for(eid):
                any_problems = True

        if not any_problems:
            flash(f"Added {duration}-hour block for {entry['course_code']} ({entry['section']}) on {entry['day']} "
                  f"({consecutive_slots[0]} to {consecutive_slots[-1]}). No conflicts.", "success")

    return redirect(url_for("timetable_page"))


@app.route("/timetable/edit/<int:entry_id>", methods=["GET", "POST"])
@login_required
def timetable_edit(entry_id):
    entry = db.get_entry(entry_id)
    if entry is None:
        abort(404)
    if request.method == "POST":
        db.update_entry(entry_id, entry_from_form())
        if not flash_conflicts_for(entry_id):
            flash("Class updated. No conflicts.", "success")
        return redirect(url_for("timetable_page"))
    return render_template("timetable_edit.html", entry=entry, **form_choices())


@app.route("/timetable/delete/<int:entry_id>", methods=["POST"])
@login_required
def timetable_delete(entry_id):
    db.delete_entry(entry_id)
    flash("Class deleted.", "success")
    return redirect(request.referrer or url_for("timetable_page"))


@app.route("/timetable/clear", methods=["POST"])
@login_required
def timetable_clear():
    db.clear_timetable()
    flash("All classes removed from the timetable.", "success")
    return redirect(url_for("timetable_page"))


@app.route("/timetable/import", methods=["POST"])
@login_required
def timetable_import():
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        flash("Please choose a file to upload.", "error")
        return redirect(url_for("timetable_page"))
    try:
        df = file_io.read_table(uploaded)
        entries, errors = file_io.parse_timetable(df, db.get_settings(), db.get_faculty_catalog(),
                                                  db.get_subjects())
    except Exception as e:
        flash(f"Could not read the file: {e}", "error")
        return redirect(url_for("timetable_page"))

    if not entries:
        flash("No classes were imported. " + " | ".join(errors[:5]), "error")
        return redirect(url_for("timetable_page"))

    if request.form.get("mode") == "replace":
        db.clear_timetable()
    for entry in entries:
        db.add_entry(entry)

    flash(f"Imported {len(entries)} classes.", "success")
    if errors:
        flash(f"{len(errors)} row(s) skipped: " + " | ".join(errors[:5])
              + (" ..." if len(errors) > 5 else ""), "warning")
    return redirect(url_for("timetable_page"))


# ---------------------------------------------------------------------------
# Automated Timetable Generator (CSP / Backtracking)
# ---------------------------------------------------------------------------
@app.route("/generate")
@login_required
def generate_page():
    return render_template("generate.html", sections=db.get_sections(),
                           subjects=db.get_subjects(), faculty=db.get_faculty(),
                           rooms=db.get_rooms())


@app.route("/generate/run", methods=["POST"])
@login_required
def generate_run():
    reqs_json = request.form.get("requirements_json", "[]")
    mode = request.form.get("mode", "replace")
    try:
        requirements = json.loads(reqs_json)
    except Exception as e:
        flash(f"Invalid requirements format: {e}", "error")
        return redirect(url_for("generate_page"))

    if not requirements:
        flash("No course requirements provided to generate timetable.", "error")
        return redirect(url_for("generate_page"))

    # Instantiate the CSP solver
    generator = TimetableGenerator(
        faculty=db.get_faculty(),
        rooms=db.get_rooms(),
        sections=db.get_sections(),
        subjects=db.get_subjects(),
        faculty_subjects=db.get_faculty_subjects(),
        settings=db.get_settings()
    )

    existing = db.get_timetable() if mode == "append" else []
    success, schedule, stats = generator.generate(requirements, existing_schedule=existing)

    if not success and not schedule:
        flash(f"Generation failed: constraints could not be satisfied. Tried {stats.get('backtracks', 0)} backtracks.", "error")
        return redirect(url_for("generate_page"))

    # Apply generated timetable
    if mode == "replace":
        db.clear_timetable()
        to_insert = schedule
    else:
        # Only insert new classes
        existing_ids = {e.get("id") for e in existing if e.get("id")}
        to_insert = [e for e in schedule if e.get("id") not in existing_ids]

    for entry in to_insert:
        db.add_entry(entry)

    msg = f"Generated {len(to_insert)} classes successfully across departments! ({stats.get('backtracks', 0)} backtracks)."
    if not success:
        msg = f"Partial schedule generated: {len(to_insert)} classes placed. Some constraints could not be fitted."
        flash(msg, "warning")
    else:
        flash(msg, "success")

    return redirect(url_for("timetable_page"))


# ---------------------------------------------------------------------------
# Interactive Visual Timetable Editor
# ---------------------------------------------------------------------------
@app.route("/editor")
@login_required
def interactive_editor():
    timetable, report = run_analysis()
    settings = db.get_settings()
    working_days = settings.get("working_days", [])
    selected_day = request.args.get("day", working_days[0] if working_days else "Monday")
    group_by = request.args.get("group_by", "sections")

    # Clashed entry IDs for visual red highlight
    clashed_ids = set()
    for c in report["conflicts_list"]:
        if c["severity"] == "CRITICAL":
            for eid in c.get("involved_entries", []):
                clashed_ids.add(eid)

    # Determine columns based on grouping
    if group_by == "sections":
        columns = [s["name"] for s in db.get_sections()]
    else:
        columns = [r["name"] for r in db.get_rooms()]

    # Grid map: (time_slot, col_name) -> list of entries
    grid = defaultdict(list)
    for e in timetable:
        if e["day"] == selected_day:
            col_val = e["section"] if group_by == "sections" else e["room"]
            grid[(e["time_slot"], col_val)].append(e)

    return render_template("editor.html", selected_day=selected_day, group_by=group_by,
                           columns=columns, grid=grid, clashed_ids=clashed_ids,
                           faculty=db.get_faculty(), rooms=db.get_rooms(),
                           sections=db.get_sections(), subjects=db.get_subjects(),
                           settings=settings)


@app.route("/editor/save", methods=["POST"])
@login_required
def interactive_editor_save():
    eid = form_int("entry_id")
    entry = db.get_entry(eid)
    if not entry:
        flash("Class not found.", "error")
        return redirect(url_for("interactive_editor"))

    updated = {
        "faculty_name": request.form.get("faculty_name", entry["faculty_name"]),
        "course_code": entry["course_code"],
        "course_name": entry.get("course_name", ""),
        "department": entry.get("department", ""),
        "section": request.form.get("section", entry["section"]),
        "batch": request.form.get("batch", entry.get("batch", "All")),
        "day": request.form.get("day", entry["day"]),
        "time_slot": request.form.get("time_slot", entry["time_slot"]),
        "room": request.form.get("room", entry["room"]),
    }

    db.update_entry(eid, updated)
    flash_conflicts_for(eid)
    flash("Updated class allocation.", "success")
    return redirect(url_for("interactive_editor", day=updated["day"], group_by=request.args.get("group_by", "sections")))


# ---------------------------------------------------------------------------
# Faculty
# ---------------------------------------------------------------------------
@app.route("/faculty")
def faculty_page():
    _, report = run_analysis()
    workload = {w["faculty_name"]: w for w in report["workload_distribution"]}
    faculty = db.get_faculty()
    for f in faculty:
        f["subjects"] = db.get_subjects_of(f["name"])
        f["workload"] = workload.get(f["name"], {})
    return render_template("faculty.html", faculty=faculty, designations=db.DESIGNATIONS,
                           departments=db.get_departments())


@app.route("/faculty/add", methods=["POST"])
@login_required
def faculty_add():
    name = request.form.get("name", "").strip()
    dept = request.form.get("department", "").strip()
    desig = request.form.get("designation", "")
    if not name or not dept or desig not in db.DESIGNATIONS:
        flash("Name, department and designation are required.", "error")
    elif name in db.get_faculty_catalog():
        flash(f"{name} already exists. Use Edit to change their details.", "error")
    else:
        db.save_faculty(name, dept, desig, form_int("max_hours") or None)
        flash(f"Added {name}. Click Edit to choose which subjects they teach.", "success")
    return redirect(url_for("faculty_page"))


@app.route("/faculty/edit/<name>", methods=["GET", "POST"])
@login_required
def faculty_edit(name):
    person = db.get_faculty_catalog().get(name)
    if person is None:
        abort(404)
    if request.method == "POST":
        desig = request.form.get("designation", person["designation"])
        db.save_faculty(name, request.form.get("department", person["department"]), desig,
                        form_int("max_hours") or None)
        db.set_subjects_of(name, request.form.getlist("subjects"))
        flash(f"Saved {name}.", "success")
        return redirect(url_for("faculty_page"))
    return render_template("faculty_edit.html", name=name, person=person,
                           designations=db.DESIGNATIONS, departments=db.get_departments(),
                           subjects=db.get_subjects(), chosen=db.get_subjects_of(name))


@app.route("/faculty/delete/<name>", methods=["POST"])
@login_required
def faculty_delete(name):
    count = db.count_classes_of(name)
    if count:
        flash(f"{name} still has {count} classes in the timetable. Reassign or delete those first.", "error")
    else:
        db.delete_faculty(name)
        flash(f"Removed {name}.", "success")
    return redirect(url_for("faculty_page"))


@app.route("/faculty/import", methods=["POST"])
@login_required
def faculty_import():
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        flash("Please choose a file to upload.", "error")
        return redirect(url_for("faculty_page"))
    try:
        rows, errors = file_io.parse_faculty(file_io.read_table(uploaded))
    except Exception as e:
        flash(f"Could not read the file: {e}", "error")
        return redirect(url_for("faculty_page"))
    for r in rows:
        db.save_faculty(r["name"], r["department"], r["designation"], r["max_hours"])
    flash(f"Imported {len(rows)} faculty members.", "success" if rows else "error")
    if errors:
        flash(f"{len(errors)} row(s) skipped: " + " | ".join(errors[:5]), "warning")
    return redirect(url_for("faculty_page"))


# ---------------------------------------------------------------------------
# Rooms, sections and subjects ("master data")
# ---------------------------------------------------------------------------
@app.route("/setup")
def masters_page():
    teachers = db.get_faculty_subjects()
    return render_template("masters.html", rooms=db.get_rooms(), sections=db.get_sections(),
                           subjects=db.get_subjects(), teachers=teachers, room_types=db.ROOM_TYPES,
                           departments=db.get_departments(),
                           baskets=db.get_elective_baskets())


def used_in_timetable(column, value):
    return db.query(f"SELECT COUNT(*) AS n FROM timetable WHERE {column} = ?", (value,))[0]["n"]


@app.route("/rooms/save", methods=["POST"])
@login_required
def room_save():
    name = request.form.get("name", "").strip()
    if not name or request.form.get("room_type") not in db.ROOM_TYPES or form_int("capacity") <= 0:
        flash("Room name, type and a capacity above 0 are required.", "error")
    else:
        db.save_room(name, request.form["room_type"], form_int("capacity"))
        flash(f"Saved room {name}.", "success")
    return redirect(url_for("masters_page") + "#rooms")


@app.route("/rooms/delete/<name>", methods=["POST"])
@login_required
def room_delete(name):
    n = used_in_timetable("room", name)
    if n:
        flash(f"{name} is used by {n} classes. Move them to another room first.", "error")
    else:
        db.delete_room(name)
        flash(f"Removed room {name}.", "success")
    return redirect(url_for("masters_page") + "#rooms")


@app.route("/sections/save", methods=["POST"])
@login_required
def section_save():
    name = request.form.get("name", "").strip()
    dept = request.form.get("department", "").strip()
    if not name or not dept or form_int("strength") <= 0:
        flash("Section name, department and a strength above 0 are required.", "error")
    else:
        db.save_section(name, dept, form_int("strength"))
        flash(f"Saved section {name}.", "success")
    return redirect(url_for("masters_page") + "#sections")


@app.route("/sections/delete/<name>", methods=["POST"])
@login_required
def section_delete(name):
    n = used_in_timetable("section", name)
    if n:
        flash(f"{name} has {n} classes in the timetable. Delete those first.", "error")
    else:
        db.delete_section(name)
        flash(f"Removed section {name}.", "success")
    return redirect(url_for("masters_page") + "#sections")


@app.route("/subjects/save", methods=["POST"])
@login_required
def subject_save():
    code = request.form.get("code", "").strip()
    name = request.form.get("name", "").strip()
    dept = request.form.get("department", "").strip()
    if not code or not name or not dept:
        flash("Subject code, name and department are required.", "error")
    else:
        db.save_subject(code, name, dept, request.form.get("is_lab") == "1")
        flash(f"Saved subject {code.upper()}.", "success")
    return redirect(url_for("masters_page") + "#subjects")


@app.route("/subjects/delete/<code>", methods=["POST"])
@login_required
def subject_delete(code):
    n = used_in_timetable("course_code", code)
    if n:
        flash(f"{code} has {n} classes in the timetable. Delete those first.", "error")
    else:
        db.delete_subject(code)
        flash(f"Removed subject {code}.", "success")
    return redirect(url_for("masters_page") + "#subjects")


@app.route("/baskets/save", methods=["POST"])
@login_required
def basket_save():
    b_name = request.form.get("basket_name", "").strip()
    c_code = request.form.get("course_code", "").strip().upper()
    c_name = request.form.get("course_name", "").strip()
    secs = request.form.get("sections", "").strip()
    cap = form_int("capacity", 60)
    if not b_name or not c_code or not secs:
        flash("Basket name, course code, and eligible sections are required.", "error")
    else:
        db.save_elective_basket(b_name, c_code, c_name, secs, cap)
        flash(f"Saved Open Elective Basket '{b_name}' for {c_code}.", "success")
    return redirect(url_for("masters_page") + "#electives")


@app.route("/baskets/delete/<int:basket_id>", methods=["POST"])
@login_required
def basket_delete(basket_id):
    db.delete_elective_basket(basket_id)
    flash("Removed elective basket.", "success")
    return redirect(url_for("masters_page") + "#electives")


# ---------------------------------------------------------------------------
# Leave & substitutes
# ---------------------------------------------------------------------------
@app.route("/leave")
@login_required
def leave_page():
    today = date.today().isoformat()
    timetable = db.get_timetable()
    leaves = db.get_leaves()
    substitutions = db.get_substitutions()
    detector = make_detector()
    assigned = {(s["leave_id"], s["timetable_id"]): s["substitute_name"] for s in substitutions}

    upcoming, past = [], []
    for lv in leaves:
        if lv["leave_date"] < today:
            past.append(lv)
            continue
        lv["weekday"] = weekday_of(lv["leave_date"])
        lv["classes"] = []
        for entry in classes_missed(lv, timetable):
            lv["classes"].append({
                "entry": entry,
                "assigned": assigned.get((lv["id"], entry["id"])),
                "options": substitute_options(entry, lv, detector, timetable, leaves, substitutions),
            })
        upcoming.append(lv)
    upcoming.sort(key=lambda lv: lv["leave_date"])

    # Long-term / Maternity cover plans
    long_term_leaves = db.get_long_term_leaves()
    long_term_covers = db.get_long_term_covers()
    lt_assigned = {(c["long_term_leave_id"], c["timetable_id"]): c["cover_faculty_name"] for c in long_term_covers}

    faculty_list = db.get_faculty()
    faculty_catalog = db.get_faculty_catalog()

    # Pre-calculate workload and availability for long-term cover options
    weekly_load = defaultdict(int)
    for e in timetable:
        weekly_load[e["faculty_name"]] += 1

    for ltl in long_term_leaves:
        f_name = ltl["faculty_name"]
        own_classes = [e for e in timetable if e["faculty_name"] == f_name]
        ltl["recurring_classes"] = []

        for entry in own_classes:
            assigned_cover = lt_assigned.get((ltl["id"], entry["id"]))
            # Eligible colleagues: same department or qualified, free at that day+slot, below weekly limit
            eligible_covers = []
            for f in faculty_list:
                cand_name = f["name"]
                if cand_name == f_name:
                    continue
                cand_info = faculty_catalog.get(cand_name, {})
                cand_dept = cand_info.get("department")
                cur_load = weekly_load[cand_name]
                max_h = cand_info.get("max_hours", 16)

                # Check if free at this recurring slot
                slot_free = not any(
                    e["faculty_name"] == cand_name and e["day"] == entry["day"] and e["time_slot"] == entry["time_slot"]
                    for e in timetable
                )

                if slot_free and cur_load < max_h:
                    is_qual = detector.can_teach(cand_name, entry.get("course_code"))
                    eligible_covers.append({
                        "name": cand_name,
                        "department": cand_dept,
                        "current_hours": cur_load,
                        "max_hours": max_h,
                        "qualified": is_qual
                    })

            # Sort eligible covers: qualified first, then least loaded
            eligible_covers.sort(key=lambda c: (0 if c["qualified"] else 1, c["current_hours"]))

            ltl["recurring_classes"].append({
                "entry": entry,
                "assigned_cover": assigned_cover,
                "eligible_covers": eligible_covers
            })

    return render_template("leave.html", upcoming=upcoming, past=past, today=today,
                           faculty=faculty_list, long_term_leaves=long_term_leaves)


@app.route("/leave/add", methods=["POST"])
@login_required
def leave_add():
    name = request.form.get("faculty_name", "")
    leave_date = request.form.get("leave_date", "")
    try:
        day = weekday_of(leave_date)
    except ValueError:
        flash("Please choose a valid date.", "error")
        return redirect(url_for("leave_page"))
    if name not in db.get_faculty_catalog():
        flash("Please choose a faculty member.", "error")
    elif db.get_holiday(leave_date):
        h = db.get_holiday(leave_date)
        flash(f"{leave_date} is already an institutional holiday ({h['name']}). All classes are suspended; no leave required.", "warning")
    elif db.query("SELECT id FROM leaves WHERE faculty_name = ? AND leave_date = ?", (name, leave_date)):
        flash(f"{name} is already marked on leave on {leave_date}.", "warning")
    else:
        db.add_leave(name, leave_date, request.form.get("reason", ""))
        missed = [e for e in db.get_timetable() if e["faculty_name"] == name and e["day"] == day]
        flash(f"Leave saved. {name} has {len(missed)} class(es) on {day} {leave_date} that need a substitute.",
              "success")
    return redirect(url_for("leave_page"))


@app.route("/leave/delete/<int:leave_id>", methods=["POST"])
@login_required
def leave_delete(leave_id):
    db.delete_leave(leave_id)
    flash("Leave removed.", "success")
    return redirect(url_for("leave_page"))


@app.route("/leave/<int:leave_id>/assign", methods=["POST"])
@login_required
def leave_assign(leave_id):
    timetable_id = form_int("timetable_id")
    substitute = request.form.get("substitute", "")
    if substitute not in db.get_faculty_catalog():
        flash("Please choose a substitute.", "error")
    else:
        db.assign_substitute(leave_id, timetable_id, substitute)
        flash(f"{substitute} will take the class.", "success")
    return redirect(url_for("leave_page") + f"#leave-{leave_id}")


@app.route("/leave/<int:leave_id>/unassign/<int:timetable_id>", methods=["POST"])
@login_required
def leave_unassign(leave_id, timetable_id):
    db.remove_substitute(leave_id, timetable_id)
    flash("Substitute removed.", "success")
    return redirect(url_for("leave_page") + f"#leave-{leave_id}")


# ---------------------------------------------------------------------------
# Long-Term Leave & Maternity Cover Actions
# ---------------------------------------------------------------------------
@app.route("/leave/long-term/add", methods=["POST"])
@login_required
def long_term_leave_add():
    faculty_name = request.form.get("faculty_name", "")
    leave_type = request.form.get("leave_type", "Maternity Leave")
    start_date = request.form.get("start_date", "")
    end_date = request.form.get("end_date", "")
    notes = request.form.get("notes", "")

    if not faculty_name or not start_date or not end_date:
        flash("Faculty, start date, and end date are required.", "error")
        return redirect(url_for("leave_page"))

    if start_date > end_date:
        flash("Start date must be before end date.", "error")
        return redirect(url_for("leave_page"))

    new_id = db.add_long_term_leave(faculty_name, leave_type, start_date, end_date, notes)
    flash(f"Created {leave_type} cover plan for {faculty_name} ({start_date} to {end_date}). Assign designated cover faculty below.", "success")
    return redirect(url_for("leave_page"))


@app.route("/leave/long-term/delete/<int:leave_id>", methods=["POST"])
@login_required
def long_term_leave_delete(leave_id):
    db.delete_long_term_leave(leave_id)
    flash("Long-term leave cover plan deleted.", "success")
    return redirect(url_for("leave_page"))


@app.route("/leave/long-term/<int:leave_id>/assign", methods=["POST"])
@login_required
def long_term_assign(leave_id):
    timetable_id = form_int("timetable_id")
    cover_faculty = request.form.get("cover_faculty", "")
    if not cover_faculty:
        flash("Please select a cover faculty member.", "error")
    else:
        db.assign_long_term_cover(leave_id, timetable_id, cover_faculty)
        flash(f"Assigned {cover_faculty} as recurring cover for this course.", "success")
    return redirect(url_for("leave_page"))


@app.route("/leave/long-term/<int:leave_id>/unassign/<int:timetable_id>", methods=["POST"])
@login_required
def long_term_unassign(leave_id, timetable_id):
    db.remove_long_term_cover(leave_id, timetable_id)
    flash("Cover assignment removed.", "success")
    return redirect(url_for("leave_page"))


# ---------------------------------------------------------------------------
# Institutional Holidays & Academic Calendar
# ---------------------------------------------------------------------------
@app.route("/holidays")
def holidays_page():
    return render_template("holidays.html", holidays=db.get_holidays(),
                           today=date.today().isoformat())


@app.route("/holidays/add", methods=["POST"])
@login_required
def holiday_add():
    h_date = request.form.get("holiday_date", "").strip()
    name = request.form.get("name", "").strip()
    h_type = request.form.get("holiday_type", "Institutional").strip()
    desc = request.form.get("description", "").strip()

    if not h_date or not name:
        flash("Date and holiday name are required.", "error")
    else:
        db.add_holiday(h_date, name, h_type, desc)
        flash(f"Declared institutional holiday '{name}' on {h_date}.", "success")
    return redirect(url_for("holidays_page"))


@app.route("/holidays/delete/<int:holiday_id>", methods=["POST"])
@login_required
def holiday_delete(holiday_id):
    db.delete_holiday(holiday_id)
    flash("Holiday removed.", "success")
    return redirect(url_for("holidays_page"))


# ---------------------------------------------------------------------------
# Printable timetables
# ---------------------------------------------------------------------------
@app.route("/print")
def print_menu():
    return render_template("print_menu.html", faculty=db.get_faculty(), sections=db.get_sections(),
                           rooms=db.get_rooms(), today=date.today().isoformat())


@app.route("/print/<kind>/<name>")
def print_timetable(kind, name):
    columns = {"faculty": "faculty_name", "section": "section", "room": "room"}
    if kind not in columns:
        abort(404)
    settings = db.get_settings()
    entries = [e for e in db.get_timetable() if e[columns[kind]] == name]

    # grid[slot][day] = list of classes in that cell
    grid = {slot: {day: [] for day in settings["working_days"]} for slot in settings["time_slots"]}
    for e in entries:
        if e["time_slot"] in grid and e["day"] in grid[e["time_slot"]]:
            grid[e["time_slot"]][e["day"]].append(e)

    extra = {}
    if kind == "faculty":
        extra = db.get_faculty_catalog().get(name, {})
    return render_template("print_grid.html", kind=kind, name=name, grid=grid, total=len(entries),
                           extra=extra)


@app.route("/print/arrangements")
@login_required
def print_arrangements():
    day_date = request.args.get("date") or date.today().isoformat()
    try:
        weekday = weekday_of(day_date)
    except ValueError:
        abort(400)
    timetable = db.get_timetable()
    assigned = {(s["leave_id"], s["timetable_id"]): s["substitute_name"] for s in db.get_substitutions()}
    rows = []
    for lv in db.query("SELECT * FROM leaves WHERE leave_date = ?", (day_date,)):
        for e in classes_missed(lv, timetable):
            rows.append({"entry": e, "absent": lv["faculty_name"],
                         "substitute": assigned.get((lv["id"], e["id"]), "")})
    slot_order = {s: i for i, s in enumerate(db.get_settings()["time_slots"])}
    rows.sort(key=lambda r: slot_order.get(r["entry"]["time_slot"], 99))
    return render_template("print_arrangements.html", rows=rows, day_date=day_date, weekday=weekday)


# ---------------------------------------------------------------------------
# Reports, charts and downloads
# ---------------------------------------------------------------------------
@app.route("/reports")
def reports_page():
    timetable, report = run_analysis()
    settings = db.get_settings()
    rooms = db.get_rooms()
    return render_template("reports.html",
                           stats=reports.summary_stats(timetable, rooms, settings, report),
                           workload=report["workload_distribution"],
                           room_usage=reports.room_usage_table(timetable, rooms, settings))


@app.route("/charts/<name>.png")
def chart_image(name):
    timetable, report = run_analysis()
    settings = db.get_settings()
    if name == "workload":
        image = reports.workload_chart(report["workload_distribution"])
    elif name == "days":
        image = reports.count_chart(timetable, "day", order=settings["working_days"])
    elif name == "departments":
        image = reports.count_chart(timetable, "department", xlabel="Teaching hours per week")
    elif name == "rooms":
        image = reports.room_chart(reports.room_usage_table(timetable, db.get_rooms(), settings))
    else:
        abort(404)
    return send_file(image, mimetype="image/png")


@app.route("/download/timetable.csv")
def download_timetable():
    data = file_io.timetable_csv(db.get_timetable())
    return send_file(io.BytesIO(data), mimetype="text/csv", as_attachment=True,
                     download_name=f"timetable_{date.today().isoformat()}.csv")


@app.route("/download/report.xlsx")
def download_report():
    timetable, report = run_analysis()
    return send_file(file_io.report_excel(timetable, report), as_attachment=True,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     download_name=f"clashaudit_report_{date.today().isoformat()}.xlsx")


@app.route("/download/template/<kind>.csv")
def download_template(kind):
    if kind == "timetable":
        data = file_io.timetable_template()
    elif kind == "faculty":
        data = file_io.faculty_template()
    else:
        abort(404)
    return send_file(io.BytesIO(data), mimetype="text/csv", as_attachment=True,
                     download_name=f"{kind}_template.csv")


@app.route("/download/backup")
@login_required
def download_backup():
    """The whole database in one file. Keep a copy somewhere safe."""
    return send_file(db.DB_PATH, as_attachment=True,
                     download_name=f"clashaudit_backup_{date.today().isoformat()}.db")


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings_page():
    if request.method == "POST":
        slots = [s.strip() for s in request.form.get("time_slots", "").splitlines() if s.strip()]
        days = [d for d in db.ALL_DAYS if d in request.form.getlist("working_days")]
        caps = {k: form_int(k) for k in ["cap_professor", "cap_associate", "cap_assistant"]}
        numbers = {k: form_int(k) for k in ["max_daily_hours", "max_consecutive_hours", "underload_percent"]}
        lunch = request.form.get("lunch_after", "")

        if not slots or not days:
            flash("You need at least one time slot and one working day.", "error")
        elif any(v <= 0 for v in list(caps.values()) + list(numbers.values())):
            flash("All limits must be numbers above 0.", "error")
        elif lunch and lunch not in slots:
            flash("The lunch break must come after one of the time slots.", "error")
        else:
            db.save_setting("college_name", request.form.get("college_name", "").strip() or "Our College")
            db.save_setting("time_slots", ",".join(slots))
            db.save_setting("working_days", ",".join(days))
            db.save_setting("lunch_after", lunch)
            for key, value in {**caps, **numbers}.items():
                db.save_setting(key, value)

            if request.form.get("update_faculty_caps") == "1":
                for f in db.get_faculty():
                    db.save_faculty(f["name"], f["department"], f["designation"], None)
                flash("Weekly caps of all faculty updated to the new designation limits.", "success")
            flash("Settings saved.", "success")
            return redirect(url_for("settings_page"))
    return render_template("settings.html", all_days=db.ALL_DAYS, scenarios=SCENARIOS)


@app.route("/settings/demo/<key>", methods=["POST"])
@login_required
def load_demo(key):
    if key not in SCENARIOS:
        abort(404)
    if not db.get_faculty():
        db.seed_master_data()
    db.load_scenario(key)
    flash(f"Loaded demo: {SCENARIOS[key]['title']}. The old timetable was replaced.", "success")
    return redirect(url_for("home"))


# ---------------------------------------------------------------------------
# JSON API (used by the dashboard's JavaScript)
# ---------------------------------------------------------------------------
@app.route("/api/health")
def health():
    return jsonify({"status": "healthy", "ml_model_loaded": ml_pipeline is not None, "version": "2.0.0"})


@app.route("/api/report")
def api_report():
    timetable, report = run_analysis()
    return jsonify({"schedule": timetable, "report": report})


@app.route("/api/scenarios")
def get_scenarios():
    return jsonify({k: {"title": v["title"], "description": v["description"], "schedule": v["schedule"]}
                    for k, v in SCENARIOS.items()})


@app.route("/api/analyze", methods=["POST"])
def analyze():
    """Analyse a timetable sent as JSON (does not save anything)."""
    data = request.get_json(silent=True)
    if not data or "schedule" not in data:
        return jsonify({"error": "Missing schedule entries in payload."}), 400
    return jsonify(make_detector().analyze_schedule(data["schedule"]))


@app.route("/api/resolve", methods=["POST"])
@login_required
def resolve():
    """Apply one suggested fix. The browser only sends WHICH suggestion; the server
    works out the suggestion again itself, so nobody can send a fake change."""
    data = request.get_json(silent=True) or {}
    _, report = run_analysis()
    chosen = next((s for s in report["suggestions"]
                   if s["conflict_id"] == data.get("conflict_id") and s["entry_id"] == data.get("entry_id")),
                  None)
    if chosen is None:
        return jsonify({"error": "This suggestion is out of date. Reload the page."}), 409

    entry = db.get_entry(chosen["entry_id"])
    if chosen["action"] == "REASSIGN_FACULTY":
        entry["faculty_name"] = chosen["recommended_faculty"]
    elif chosen["action"] == "CHANGE_ROOM":
        entry["room"] = chosen["recommended_room"]
    elif chosen["action"] == "MOVE_SLOT":
        entry["day"] = chosen["recommended_day"]
        entry["time_slot"] = chosen["recommended_slot"]
    db.update_entry(entry["id"], entry)

    timetable, report = run_analysis()
    return jsonify({"status": "resolved", "applied": chosen, "schedule": timetable, "report": report})


@app.route("/api/predict-stress", methods=["POST"])
def predict_stress():
    if ml_pipeline is None:
        return jsonify({"error": "ML model not available. Please run model/train.py."}), 500
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Missing payload."}), 400
    try:
        desig = str(data.get("Designation", "Assistant Professor"))
        teaching = float(data.get("TeachingHours", 12))
        lab = float(data.get("LabHours", 4))
        admin = float(data.get("AdminHours", 2))
        research = float(data.get("ResearchHours", 2))
        input_df = pd.DataFrame([{
            "Designation": desig, "TeachingHours": teaching, "LabHours": lab,
            "AdminHours": admin, "ResearchHours": research,
            "UniqueCourses": int(data.get("UniqueCourses", 2)),
            "DaysTaught": int(data.get("DaysTaught", 4)),
        }])
        pred_class = int(ml_pipeline.predict(input_df)[0])
        probabilities = ml_pipeline.predict_proba(input_df)[0].tolist()
    except (TypeError, ValueError) as ex:
        return jsonify({"error": f"Invalid input: {ex}"}), 400

    labels = ["Underloaded", "Balanced / Optimal", "Overloaded (Burnout Risk)"]
    total_hours = teaching + lab + admin + research
    max_h = db.cap_for(desig)
    if pred_class == 2:
        recommendation = (f"Workload is above the limit ({total_hours:.0f}/{max_h} hrs). "
                          f"Move at least {max(total_hours - max_h, 1):.0f} hours to other faculty.")
    elif pred_class == 0:
        recommendation = (f"Faculty has spare capacity ({total_hours:.0f}/{max_h} hrs) "
                          f"and can take extra tutorial or lab duties.")
    else:
        recommendation = f"Workload is balanced ({total_hours:.0f}/{max_h} hrs) and within AICTE/UGC norms."

    return jsonify({
        "prediction_code": pred_class,
        "prediction_label": labels[pred_class],
        "total_hours": total_hours,
        "max_allowed_hours": max_h,
        "utilization_ratio": round(total_hours / max_h * 100, 1),
        "probabilities": {
            "Underloaded": round(probabilities[0] * 100, 1),
            "Balanced": round(probabilities[1] * 100, 1),
            "Overloaded": round(probabilities[2] * 100, 1),
        },
        "recommendation": recommendation,
    })


@app.route("/api/model-info")
def model_info():
    return jsonify(model_meta)


@app.errorhandler(413)
def too_large(_):
    flash("That file is too big (limit 5 MB).", "error")
    return redirect(request.referrer or url_for("home"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"[*] ClashAudit running on http://127.0.0.1:{port}")
    print("[*] Other computers on the same network can open http://<this-computer's-IP>:" + str(port))
    app.run(host="0.0.0.0", port=port, debug=False)
