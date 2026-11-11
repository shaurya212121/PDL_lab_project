"""
Ready-made demo timetables.

They are used for the demo (Settings page -> "Load demo timetable") and by
the tests. Loading a scenario REPLACES the current timetable.
"""


def cls(entry_id, faculty, dept, code, name, section, day, slot, room):
    """Small helper so each class fits on one line."""
    return {"id": entry_id, "faculty_name": faculty, "department": dept,
            "course_code": code, "course_name": name, "section": section,
            "day": day, "time_slot": slot, "room": room}


# Time slot names (short variables make the lists below easier to read)
S09, S10, S11, S12 = "09:00 - 10:00", "10:00 - 11:00", "11:00 - 12:00", "12:00 - 01:00"
S02, S03, S04 = "02:00 - 03:00", "03:00 - 04:00", "04:00 - 05:00"

RAJESH, ANANYA, AMIT, PRIYA = "Dr. Rajesh Sharma", "Prof. Ananya Iyer", "Dr. Amit Verma", "Dr. Priya Nair"
SURESH, SNEHA, VIKRAM, POOJA = "Dr. Suresh Patel", "Prof. Sneha Deshmukh", "Dr. Vikram Gupta", "Dr. Pooja Menon"


# ---------------------------------------------------------------------------
# Scenario A: a clean timetable with no problems
# ---------------------------------------------------------------------------
BALANCED = [
    cls("S1", RAJESH, "CSE", "CS301", "Operating Systems", "CSE-A", "Monday", S09, "LH-101"),
    cls("S2", ANANYA, "CSE", "CS302", "Database Systems", "CSE-B", "Monday", S10, "LH-102"),
    cls("S3", AMIT, "CSE", "CS303", "Computer Networks", "CSE-A", "Monday", S11, "LH-101"),
    cls("S4", PRIYA, "CSE", "CS304", "Algorithms", "CSE-B", "Monday", S02, "LH-103"),

    cls("S5", RAJESH, "CSE", "CS301", "Operating Systems", "CSE-A", "Tuesday", S09, "LH-101"),
    cls("S6", ANANYA, "CSE", "CS302", "Database Systems", "CSE-B", "Tuesday", S11, "LH-102"),
    cls("S7", AMIT, "CSE", "CS303", "Computer Networks", "CSE-A", "Tuesday", S02, "LH-101"),
    cls("S8", SURESH, "IT", "IT301", "Web Technologies", "IT-A", "Tuesday", S10, "LH-201"),

    cls("S9", SNEHA, "IT", "IT302", "Cloud Computing", "IT-A", "Wednesday", S09, "LH-201"),
    cls("S10", VIKRAM, "AI-DS", "AI301", "Machine Learning", "AI-A", "Wednesday", S10, "LH-301"),
    cls("S11", POOJA, "AI-DS", "AI302", "Deep Learning", "AI-A", "Wednesday", S11, "LH-301"),
    cls("S12", PRIYA, "CSE", "CS304", "Algorithms", "CSE-A", "Wednesday", S02, "LH-103"),

    cls("S13", SURESH, "IT", "IT301", "Web Technologies", "IT-A", "Thursday", S09, "LH-201"),
    cls("S14", VIKRAM, "AI-DS", "AI301", "Machine Learning", "AI-A", "Thursday", S11, "LH-301"),
    cls("S15", ANANYA, "CSE", "CS302", "Database Systems", "CSE-A", "Thursday", S02, "LH-102"),
    cls("S16", POOJA, "AI-DS", "AI302", "Deep Learning", "AI-A", "Thursday", S03, "LH-301"),
]

# ---------------------------------------------------------------------------
# Scenario B: hard clashes (faculty, room, section) + a lab in a lecture hall
# ---------------------------------------------------------------------------
COLLISION = [
    # Faculty clash: Dr. Rajesh Sharma in two classes on Monday 10:00
    cls("C1", RAJESH, "CSE", "CS301", "Operating Systems", "CSE-A", "Monday", S10, "LH-101"),
    cls("C2", RAJESH, "CSE", "CS301", "Operating Systems", "CSE-B", "Monday", S10, "LH-102"),
    # Room clash: LH-101 used by two teachers on Wednesday 11:00
    cls("C3", ANANYA, "CSE", "CS302", "Database Systems", "CSE-A", "Wednesday", S11, "LH-101"),
    cls("C4", AMIT, "CSE", "CS303", "Computer Networks", "CSE-B", "Wednesday", S11, "LH-101"),
    # Section clash: CSE-A students have two classes on Tuesday 09:00
    cls("C5", PRIYA, "CSE", "CS304", "Algorithms", "CSE-A", "Tuesday", S09, "LH-103"),
    cls("C9", ANANYA, "CSE", "CS302", "Database Systems", "CSE-A", "Tuesday", S09, "LH-102"),
    # Lab subject placed in a lecture hall
    cls("C10", PRIYA, "CSE", "CS305", "Data Structures Lab", "CSE-B", "Friday", S10, "LH-103"),
    # Normal classes
    cls("C6", SURESH, "IT", "IT301", "Web Technologies", "IT-A", "Tuesday", S11, "LH-201"),
    cls("C7", SNEHA, "IT", "IT302", "Cloud Computing", "IT-A", "Thursday", S10, "LH-201"),
    cls("C8", VIKRAM, "AI-DS", "AI301", "Machine Learning", "AI-A", "Thursday", S02, "LH-301"),
]

# ---------------------------------------------------------------------------
# Scenario C: overload and fatigue
# Dr. Amit Verma (Assistant Professor, cap 18 hrs) gets 19 hours,
# Dr. Priya Nair teaches 4 classes back-to-back on Tuesday morning.
# ---------------------------------------------------------------------------
OVERLOAD = [
    cls("O1", PRIYA, "CSE", "CS304", "Algorithms", "CSE-A", "Tuesday", S09, "LH-103"),
    cls("O2", PRIYA, "CSE", "CS304", "Algorithms", "CSE-B", "Tuesday", S10, "LH-103"),
    cls("O3", PRIYA, "CSE", "CS305", "Data Structures Lab", "CSE-A", "Tuesday", S11, "Lab-1"),
    cls("O4", PRIYA, "CSE", "CS305", "Data Structures Lab", "CSE-A", "Tuesday", S12, "Lab-1"),

    cls("O5", AMIT, "CSE", "CS303", "Computer Networks", "CSE-A", "Monday", S09, "LH-102"),
    cls("O6", AMIT, "CSE", "CS303", "Computer Networks", "CSE-B", "Monday", S11, "LH-102"),
    cls("O7", AMIT, "CSE", "CS303", "Computer Networks", "CSE-B", "Monday", S03, "LH-102"),
    cls("O8", AMIT, "CSE", "CS303", "Computer Networks", "CSE-A", "Monday", S04, "LH-102"),
    cls("O9", AMIT, "CSE", "CS303", "Computer Networks", "CSE-B", "Tuesday", S09, "LH-102"),
    cls("O10", AMIT, "CSE", "CS303", "Computer Networks", "CSE-B", "Tuesday", S11, "LH-102"),
    cls("O11", AMIT, "CSE", "CS306", "Network Lab", "CSE-A", "Tuesday", S02, "Lab-2"),
    cls("O12", AMIT, "CSE", "CS306", "Network Lab", "CSE-A", "Tuesday", S03, "Lab-2"),
    cls("O13", AMIT, "CSE", "CS303", "Computer Networks", "CSE-A", "Wednesday", S09, "LH-102"),
    cls("O14", AMIT, "CSE", "CS303", "Computer Networks", "CSE-B", "Wednesday", S10, "LH-102"),
    cls("O15", AMIT, "CSE", "CS303", "Computer Networks", "CSE-B", "Wednesday", S02, "LH-102"),
    cls("O16", AMIT, "CSE", "CS303", "Computer Networks", "CSE-A", "Wednesday", S03, "LH-102"),
    cls("O17", AMIT, "CSE", "CS306", "Network Lab", "CSE-A", "Thursday", S09, "Lab-2"),
    cls("O18", AMIT, "CSE", "CS306", "Network Lab", "CSE-A", "Thursday", S10, "Lab-2"),
    cls("O19", AMIT, "CSE", "CS303", "Computer Networks", "CSE-B", "Thursday", S02, "LH-102"),
    cls("O20", AMIT, "CSE", "CS303", "Computer Networks", "CSE-B", "Thursday", S04, "LH-102"),
    cls("O21", AMIT, "CSE", "CS303", "Computer Networks", "CSE-A", "Friday", S09, "LH-102"),
    cls("O22", AMIT, "CSE", "CS306", "Network Lab", "CSE-B", "Friday", S02, "Lab-2"),
    cls("O23", AMIT, "CSE", "CS306", "Network Lab", "CSE-B", "Friday", S03, "Lab-2"),

    cls("O24", RAJESH, "CSE", "CS301", "Operating Systems", "CSE-A", "Monday", S02, "LH-101"),
    cls("O25", SNEHA, "IT", "IT302", "Cloud Computing", "IT-A", "Wednesday", S10, "LH-201"),
]

SCENARIOS = {
    "balanced": {
        "title": "Scenario A: Clean timetable",
        "description": "No clashes, every teacher within their weekly limit.",
        "schedule": BALANCED,
    },
    "collision": {
        "title": "Scenario B: Clashes",
        "description": "A faculty double-booking, a room double-booking, a section clash "
                       "and a lab placed in a lecture hall.",
        "schedule": COLLISION,
    },
    "overload": {
        "title": "Scenario C: Overload & fatigue",
        "description": "Dr. Amit Verma has 19 hrs/week (cap 18) and Dr. Priya Nair has "
                       "4 back-to-back classes on Tuesday.",
        "schedule": OVERLOAD,
    },
}
