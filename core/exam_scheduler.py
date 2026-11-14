"""
Exam Supervision & Multi-Class Cohort Scheduling Engine.
Validates multi-class pooling, supervisor double-booking, hall capacities, and invigilation fair distribution.
"""

from core import database as db


def check_exam_conflicts(sessions=None):
    """
    Check all exam sessions for scheduling conflicts, supervisor double-bookings,
    and hall capacity overflows.
    """
    if sessions is None:
        sessions = db.get_exam_sessions()

    rooms = {r["name"]: r["capacity"] for r in db.get_rooms()}
    leaves = {(l["faculty_name"], l["leave_date"]) for l in db.get_leaves()}
    holidays = {h["holiday_date"]: h["name"] for h in db.get_holidays()}

    conflicts = []

    # 1. Holiday collision check
    for s in sessions:
        h_date = s.get("exam_date", "")
        if h_date in holidays:
            conflicts.append({
                "type": "HOLIDAY_EXAM_WARNING",
                "severity": "WARNING",
                "session_id": s["id"],
                "title": "Exam Scheduled on Institutional Holiday",
                "message": f"Exam '{s['session_title']}' ({s['course_code']}) is scheduled on {h_date}, which is declared as '{holidays[h_date]}'."
            })

    # 2. Hall capacity check
    for s in sessions:
        r_name = s.get("room", "")
        cap = rooms.get(r_name, 72)
        total_students = s.get("total_students", 0)
        if total_students > cap:
            conflicts.append({
                "type": "HALL_CAPACITY_OVERFLOW",
                "severity": "WARNING",
                "session_id": s["id"],
                "title": "Exam Hall Seating Capacity Exceeded",
                "message": f"Combined classes ({s['sections']}) have {total_students} students, but room {r_name} only accommodates {cap} candidates."
            })

    # 3. Pairwise clash checks: supervisor clashes, room collisions, section clashes
    n = len(sessions)
    for i in range(n):
        s1 = sessions[i]
        d1 = s1.get("exam_date")
        t1 = s1.get("time_slot")

        # Supervisor on leave check
        for role, fac in [("Primary Supervisor", s1.get("primary_supervisor")),
                          ("Assistant Supervisor", s1.get("assistant_supervisor"))]:
            if fac and (fac, d1) in leaves:
                conflicts.append({
                    "type": "SUPERVISOR_ON_LEAVE",
                    "severity": "WARNING",
                    "session_id": s1["id"],
                    "title": f"Invigilator On Leave ({role})",
                    "message": f"{fac} is scheduled for invigilation on {d1} ({t1}) in {s1.get('room')}, but is marked on approved leave."
                })

        for j in range(i + 1, n):
            s2 = sessions[j]
            d2 = s2.get("exam_date")
            t2 = s2.get("time_slot")

            if d1 != d2 or t1 != t2:
                continue

            # a) Room double-booking (two different exams in the same room at the same time)
            if s1.get("room") == s2.get("room"):
                conflicts.append({
                    "type": "ROOM_DOUBLE_BOOKING",
                    "severity": "CRITICAL",
                    "session_id": s1["id"],
                    "title": "Exam Room Collision",
                    "message": f"Room {s1['room']} is booked simultaneously for '{s1['session_title']}' ({s1['course_code']}) and '{s2['session_title']}' ({s2['course_code']}) on {d1} at {t1}."
                })

            # b) Supervisor double-booking
            team1 = {s1.get("primary_supervisor"), s1.get("assistant_supervisor")} - {"", None}
            team2 = {s2.get("primary_supervisor"), s2.get("assistant_supervisor")} - {"", None}
            clashing_supervisors = team1 & team2

            for fac in clashing_supervisors:
                conflicts.append({
                    "type": "SUPERVISOR_CLASH",
                    "severity": "CRITICAL",
                    "session_id": s1["id"],
                    "title": "Invigilator Double-Booking",
                    "message": f"{fac} is assigned to supervise two different exam halls ({s1['room']} and {s2['room']}) at the same time on {d1} ({t1})."
                })

            # c) Section exam clash
            sec1 = {x.strip() for x in s1.get("sections", "").split(",") if x.strip()}
            sec2 = {x.strip() for x in s2.get("sections", "").split(",") if x.strip()}
            clashing_sections = sec1 & sec2

            if clashing_sections:
                conflicts.append({
                    "type": "SECTION_EXAM_CLASH",
                    "severity": "CRITICAL",
                    "session_id": s1["id"],
                    "title": "Student Section Exam Collision",
                    "message": f"Section(s) {', '.join(clashing_sections)} are scheduled for two simultaneous examinations on {d1} at {t1}: '{s1['course_code']}' and '{s2['course_code']}'."
                })

    critical_count = sum(1 for c in conflicts if c["severity"] == "CRITICAL")
    warning_count = sum(1 for c in conflicts if c["severity"] == "WARNING")

    return {
        "total_sessions": len(sessions),
        "total_conflicts": len(conflicts),
        "critical_count": critical_count,
        "warning_count": warning_count,
        "conflicts": conflicts,
    }


def get_invigilation_roster_stats():
    """
    Calculate supervision duties per faculty and analyze allocation balance.
    """
    stats = db.get_supervisor_duty_stats()
    total_duties = sum(f["total_duties"] for f in stats)
    num_fac = len(stats) if stats else 1
    avg_duties = round(total_duties / num_fac, 1) if num_fac else 0.0

    for f in stats:
        d = f["total_duties"]
        if d == 0:
            f["status"] = "No Duties Assigned"
            f["badge_class"] = "amber"
        elif d > avg_duties + 1:
            f["status"] = "Heavy Workload"
            f["badge_class"] = "red"
        elif d < avg_duties - 1:
            f["status"] = "Light Workload"
            f["badge_class"] = "blue"
        else:
            f["status"] = "Balanced"
            f["badge_class"] = "green"

    return {
        "stats": stats,
        "total_duties": total_duties,
        "avg_duties": avg_duties,
    }
