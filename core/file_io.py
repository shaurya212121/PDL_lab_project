"""
Import and export of files (CSV and Excel) using pandas.

Import : read a timetable or faculty list that the college already has in Excel/CSV.
Export : download the timetable and the full conflict report.
"""

import io
import re
import pandas as pd

from core.database import DESIGNATIONS

# Different colleges name their columns differently. We map common names
# to the names our program uses. Keys are already lower-case with underscores.
COLUMN_ALIASES = {
    "faculty": "faculty_name", "teacher": "faculty_name", "faculty_name": "faculty_name",
    "teacher_name": "faculty_name", "name": "name",
    "dept": "department", "department": "department", "branch": "department",
    "course": "course_code", "course_code": "course_code", "subject_code": "course_code",
    "code": "course_code",
    "course_name": "course_name", "subject": "course_name", "subject_name": "course_name",
    "course_title": "course_name",
    "section": "section", "class": "section", "division": "section", "batch": "section",
    "day": "day",
    "time_slot": "time_slot", "slot": "time_slot", "time": "time_slot", "timing": "time_slot",
    "room": "room", "room_no": "room", "classroom": "room", "venue": "room",
    "designation": "designation", "post": "designation",
    "max_hours": "max_hours", "cap": "max_hours", "weekly_cap": "max_hours",
}

TIMETABLE_REQUIRED = ["faculty_name", "course_code", "section", "day", "time_slot", "room"]


def read_table(uploaded_file):
    """Read an uploaded .csv / .xlsx file into a pandas DataFrame with clean column names."""
    filename = (uploaded_file.filename or "").lower()
    if filename.endswith(".csv"):
        df = pd.read_csv(uploaded_file, dtype=str)
    elif filename.endswith(".xlsx") or filename.endswith(".xls"):
        df = pd.read_excel(uploaded_file, dtype=str)
    else:
        raise ValueError("Please upload a .csv or .xlsx file.")

    clean = {}
    for col in df.columns:
        key = re.sub(r"[^a-z0-9]+", "_", str(col).strip().lower()).strip("_")
        clean[col] = COLUMN_ALIASES.get(key, key)
    df = df.rename(columns=clean)
    df = df.fillna("")
    # remove extra spaces from every cell
    for col in df.columns:
        df[col] = df[col].astype(str).str.strip()
    # drop rows that are completely empty
    df = df[(df != "").any(axis=1)]
    return df


def normalize_slot(text):
    """'9:00-10:00', '09:00 - 10:00' and '9:00 -10:00' should all be treated the same."""
    text = str(text).replace(" ", "")
    return re.sub(r"(^|-)0(\d)", r"\1\2", text)


def parse_timetable(df, settings, faculty_catalog, subjects):
    """Turn the rows of an uploaded timetable into class entries.
    Returns (entries, errors). Rows with errors are skipped."""
    if "course_code" not in df.columns and "course_name" in df.columns:
        # Many sheets have just one "Subject" column holding either a code (CS301)
        # or a name (Operating Systems). Turn known names into their codes.
        name_to_code = {s["name"].lower(): s["code"] for s in subjects}
        df = df.copy()
        df["course_code"] = [name_to_code.get(v.lower(), v) for v in df["course_name"]]
        df["course_name"] = ""

    missing = [c for c in TIMETABLE_REQUIRED if c not in df.columns]
    if missing:
        return [], [f"Missing column(s): {', '.join(missing)}. "
                    f"Required: {', '.join(TIMETABLE_REQUIRED)}."]

    slot_lookup = {normalize_slot(s): s for s in settings["time_slots"]}
    day_lookup = {d.lower(): d for d in settings["working_days"]}
    day_lookup.update({d[:3].lower(): d for d in settings["working_days"]})  # 'Mon' -> 'Monday'
    subject_lookup = {s["code"]: s for s in subjects}

    entries, errors = [], []
    for position, row in enumerate(df.to_dict("records")):
        row_no = position + 2  # +2 because row 1 in the file is the header
        problems = [f"'{c}' is empty" for c in TIMETABLE_REQUIRED if not row.get(c)]

        day = day_lookup.get(str(row.get("day", "")).lower())
        if row.get("day") and not day:
            problems.append(f"day '{row['day']}' is not a working day")

        slot = slot_lookup.get(normalize_slot(row.get("time_slot", "")))
        if row.get("time_slot") and not slot:
            problems.append(f"time slot '{row['time_slot']}' is not in Settings")

        if problems:
            errors.append(f"Row {row_no}: " + "; ".join(problems))
            continue

        code = row["course_code"].upper()
        subject = subject_lookup.get(code, {})
        department = (row.get("department")
                      or faculty_catalog.get(row["faculty_name"], {}).get("department")
                      or subject.get("department") or "General")
        entries.append({
            "faculty_name": row["faculty_name"],
            "department": department,
            "course_code": code,
            "course_name": row.get("course_name") or subject.get("name", ""),
            "section": row["section"],
            "day": day,
            "time_slot": slot,
            "room": row["room"],
        })
    return entries, errors


def match_designation(text):
    """Accept 'Asst. Prof', 'assistant professor', 'Prof', etc."""
    t = str(text).lower()
    if "assoc" in t:
        return "Associate Professor"
    if "assist" in t or "asst" in t:
        return "Assistant Professor"
    if "prof" in t or "hod" in t:
        return "Professor"
    return None


def parse_faculty(df):
    """Rows of an uploaded faculty list -> list of dicts. Returns (rows, errors)."""
    if "name" not in df.columns and "faculty_name" in df.columns:
        df = df.rename(columns={"faculty_name": "name"})
    missing = [c for c in ["name", "department", "designation"] if c not in df.columns]
    if missing:
        return [], [f"Missing column(s): {', '.join(missing)}. Required: name, department, designation."]

    rows, errors = [], []
    for position, row in enumerate(df.to_dict("records")):
        row_no = position + 2
        designation = match_designation(row.get("designation", ""))
        if not row.get("name") or not row.get("department"):
            errors.append(f"Row {row_no}: name and department are required")
            continue
        if designation is None:
            errors.append(f"Row {row_no}: designation '{row.get('designation')}' must be one of "
                          f"{', '.join(DESIGNATIONS)}")
            continue
        max_hours = row.get("max_hours", "")
        rows.append({
            "name": row["name"], "department": row["department"], "designation": designation,
            "max_hours": int(float(max_hours)) if str(max_hours).replace(".", "", 1).isdigit() else None,
        })
    return rows, errors


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
EXPORT_COLUMNS = ["day", "time_slot", "section", "course_code", "course_name",
                  "faculty_name", "department", "room"]


def timetable_csv(timetable):
    df = pd.DataFrame(timetable, columns=EXPORT_COLUMNS)
    return df.to_csv(index=False).encode("utf-8")


def report_excel(timetable, report):
    """One Excel file with 4 sheets: Timetable, Conflicts, Workload, Suggestions."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(timetable, columns=EXPORT_COLUMNS).to_excel(writer, sheet_name="Timetable", index=False)

        conflicts = pd.DataFrame(report["conflicts_list"],
                                 columns=["severity", "badge", "title", "day", "time_slot", "description"])
        conflicts.to_excel(writer, sheet_name="Conflicts", index=False)

        workload = pd.DataFrame(report["workload_distribution"],
                                columns=["faculty_name", "department", "designation", "assigned_hours",
                                         "max_hours", "utilization_percentage", "status"])
        workload.to_excel(writer, sheet_name="Workload", index=False)

        suggestions = pd.DataFrame(report["suggestions"], columns=["course", "action", "reason"])
        suggestions.to_excel(writer, sheet_name="Suggestions", index=False)

        # make columns wide enough to read
        for sheet in writer.sheets.values():
            for column in sheet.columns:
                longest = max(len(str(cell.value or "")) for cell in column)
                sheet.column_dimensions[column[0].column_letter].width = min(longest + 2, 80)
    output.seek(0)
    return output


def timetable_template():
    """A sample file the college can fill in and upload."""
    sample = pd.DataFrame([
        {"faculty_name": "Dr. Rajesh Sharma", "department": "CSE", "course_code": "CS301",
         "course_name": "Operating Systems", "section": "CSE-A", "day": "Monday",
         "time_slot": "09:00 - 10:00", "room": "LH-101"},
        {"faculty_name": "Dr. Priya Nair", "department": "CSE", "course_code": "CS305",
         "course_name": "Data Structures Lab", "section": "CSE-B", "day": "Tuesday",
         "time_slot": "02:00 - 03:00", "room": "Lab-1"},
    ])
    return sample.to_csv(index=False).encode("utf-8")


def faculty_template():
    sample = pd.DataFrame([
        {"name": "Dr. Example Name", "department": "CSE", "designation": "Assistant Professor", "max_hours": ""},
        {"name": "Prof. Another Name", "department": "IT", "designation": "Associate Professor", "max_hours": 16},
    ])
    return sample.to_csv(index=False).encode("utf-8")
