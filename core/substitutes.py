"""
Leave and substitute arrangement.

When a teacher is on leave on a date, we find their classes on that weekday
and suggest other teachers who can take each class.
"""

from datetime import date


def weekday_of(date_text):
    """'2026-11-16' -> 'Monday'"""
    return date.fromisoformat(date_text).strftime("%A")


def classes_missed(leave, timetable):
    """Classes the teacher on leave would normally take on that day."""
    day = weekday_of(leave["leave_date"])
    return [e for e in timetable if e["faculty_name"] == leave["faculty_name"] and e["day"] == day]


def substitute_options(entry, leave, detector, timetable, all_leaves, substitutions, limit=4):
    """Best substitutes for one class on the leave date.

    A substitute must: be in the same department, have no class of their own at
    that time, not already be substituting somewhere else at that time, not be
    on leave themselves that day, and be below their weekly cap.
    Qualified teachers (mapped to the subject) are listed first.
    """
    busy, load, _ = detector._build_busy_sets(timetable)

    # Teachers already given a substitute class on the same date and slot are busy too
    leave_dates = {lv["id"]: lv["leave_date"] for lv in all_leaves}
    entry_lookup = {e["id"]: e for e in timetable}
    for sub in substitutions:
        other = entry_lookup.get(sub["timetable_id"])
        if (other and leave_dates.get(sub["leave_id"]) == leave["leave_date"]
                and other["time_slot"] == entry["time_slot"] and other["id"] != entry["id"]):
            busy["faculty"].add((sub["substitute_name"], entry["day"], entry["time_slot"]))

    on_leave_same_day = {lv["faculty_name"] for lv in all_leaves if lv["leave_date"] == leave["leave_date"]}

    options = []
    for name, current_load in detector.find_substitute(entry, busy, load, exclude=on_leave_same_day):
        options.append({
            "name": name,
            "load": current_load,
            "max_hours": detector.max_hours_of(name),
            "qualified": detector.can_teach(name, entry["course_code"]),
        })
    return options[:limit]
