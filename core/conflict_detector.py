"""
Faculty Workload Distribution & Conflict Detection Engine

This file does NOT talk to the database. It receives plain Python lists and
dictionaries and returns a report. That keeps it easy to test (see tests/).

What it checks
--------------
Hard conflicts (CRITICAL - the timetable cannot work like this):
  1. Faculty double-booking  - same teacher, two classes, same day & slot
  2. Room double-booking     - same room, two classes, same day & slot
  3. Section clash           - same student section, two classes, same day & slot

Soft warnings (WARNING - possible, but should be fixed):
  4. Daily limit             - too many classes for a teacher in one day
  5. Consecutive fatigue     - too many back-to-back classes (lunch break resets the count)
  6. Weekly overload         - weekly hours above the AICTE/UGC cap
  7. Lab in a lecture hall   - a lab subject scheduled in a non-lab room
  8. Room too small          - section strength is more than room capacity
  9. Not qualified           - teacher is not listed as able to teach that subject
 10. Unknown data            - faculty/room/section/day/slot that is not registered

It also gives suggestions to fix conflicts (another teacher, another room,
or another free time slot).
"""

from collections import defaultdict
import numpy as np

# Used only when no settings are passed in (e.g. quick tests / CLI demo)
DEFAULT_RULES = {
    "working_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
    "time_slots": ["09:00 - 10:00", "10:00 - 11:00", "11:00 - 12:00", "12:00 - 01:00",
                   "02:00 - 03:00", "03:00 - 04:00", "04:00 - 05:00"],
    "lunch_after": "12:00 - 01:00",
    "max_daily_hours": 5,
    "max_consecutive_hours": 3,
    "underload_percent": 65,
}

# Kept for older code (demo_cli.py) - the web app reads faculty from the database
DEFAULT_FACULTY_CATALOG = {
    "Dr. Rajesh Sharma": {"designation": "Professor", "department": "CSE", "max_hours": 14},
    "Prof. Ananya Iyer": {"designation": "Associate Professor", "department": "CSE", "max_hours": 16},
    "Dr. Amit Verma": {"designation": "Assistant Professor", "department": "CSE", "max_hours": 18},
    "Dr. Priya Nair": {"designation": "Assistant Professor", "department": "CSE", "max_hours": 18},
    "Dr. Suresh Patel": {"designation": "Associate Professor", "department": "IT", "max_hours": 16},
    "Prof. Sneha Deshmukh": {"designation": "Assistant Professor", "department": "IT", "max_hours": 18},
    "Dr. Vikram Gupta": {"designation": "Professor", "department": "AI-DS", "max_hours": 14},
    "Dr. Pooja Menon": {"designation": "Assistant Professor", "department": "AI-DS", "max_hours": 18},
}


class ConflictDetector:
    def __init__(self, faculty_catalog=None, rooms=None, sections=None, subjects=None,
                 faculty_subjects=None, settings=None, elective_baskets=None):
        """
        faculty_catalog  : {name: {"designation", "department", "max_hours"}}
        rooms            : list of {"name", "room_type", "capacity"}
        sections         : list of {"name", "department", "strength"}
        subjects         : list of {"code", "name", "department", "is_lab"}
        faculty_subjects : {course_code: [faculty names who can teach it]}
        settings         : dict like DEFAULT_RULES
        elective_baskets : list of {"basket_name", "course_code", "sections"}
        """
        self.catalog = faculty_catalog if faculty_catalog is not None else DEFAULT_FACULTY_CATALOG
        self.rooms = {r["name"]: r for r in (rooms or [])}
        self.sections = {s["name"]: s for s in (sections or [])}
        self.subjects = {s["code"]: s for s in (subjects or [])}
        self.faculty_subjects = faculty_subjects or {}
        self.elective_baskets = elective_baskets or []
        self.rules = dict(DEFAULT_RULES)
        if settings:
            self.rules.update(settings)

    # ------------------------------------------------------------------
    # Small helper functions
    # ------------------------------------------------------------------
    def is_lab_course(self, entry):
        """A course is a lab if the subjects table says so, or its name contains 'lab'."""
        subject = self.subjects.get(entry.get("course_code"))
        if subject is not None:
            return bool(subject["is_lab"])
        return "lab" in str(entry.get("course_name", "")).lower()

    def can_teach(self, faculty_name, course_code):
        """True if the teacher may teach this course.
        If nobody is mapped to the course yet, we do not restrict it."""
        allowed = self.faculty_subjects.get(course_code)
        if not allowed:
            return True
        return faculty_name in allowed

    def max_hours_of(self, faculty_name):
        return self.catalog.get(faculty_name, {}).get("max_hours", 16)

    # ------------------------------------------------------------------
    # Main function
    # ------------------------------------------------------------------
    def analyze_schedule(self, schedule_entries):
        """Check the whole timetable and return a report dictionary."""
        conflicts = []
        time_slots = self.rules["time_slots"]
        working_days = self.rules["working_days"]

        # Group the classes in different ways so clashes are easy to find
        faculty_slot_map = defaultdict(list)   # (faculty, day, slot) -> classes
        room_slot_map = defaultdict(list)      # (room, day, slot)    -> classes
        section_slot_map = defaultdict(list)   # (section, day, slot) -> classes
        faculty_day_entries = defaultdict(lambda: defaultdict(list))  # faculty -> day -> classes
        faculty_total_hours = defaultdict(int)

        for entry in schedule_entries:
            f_name = entry.get("faculty_name")
            day = entry.get("day")
            slot = entry.get("time_slot")
            faculty_slot_map[(f_name, day, slot)].append(entry)
            room_slot_map[(entry.get("room"), day, slot)].append(entry)
            section_slot_map[(entry.get("section"), day, slot)].append(entry)
            faculty_day_entries[f_name][day].append(entry)
            faculty_total_hours[f_name] += 1   # every slot is one hour

        # ---- 1. Faculty double-booking --------------------------------
        for (f_name, day, slot), entries in faculty_slot_map.items():
            if len(entries) > 1:
                details = " & ".join(f"{e.get('course_code')} ({e.get('section')}) in {e.get('room')}"
                                     for e in entries)
                conflicts.append({
                    "id": f"FAC|{f_name}|{day}|{slot}",
                    "type": "FACULTY_TIME_CLASH", "severity": "CRITICAL", "badge": "Hard Conflict",
                    "title": f"Faculty Double-Booking: {f_name}",
                    "day": day, "time_slot": slot,
                    "description": f"{f_name} is assigned to {len(entries)} classes at {slot} on {day}: {details}.",
                    "involved_entries": [e.get("id") for e in entries],
                    "target_faculty": f_name,
                })

        # ---- 2. Room double-booking -----------------------------------
        for (room, day, slot), entries in room_slot_map.items():
            if len(entries) > 1:
                details = " & ".join(f"{e.get('faculty_name')} [{e.get('course_code')}]" for e in entries)
                conflicts.append({
                    "id": f"ROOM|{room}|{day}|{slot}",
                    "type": "ROOM_DOUBLE_BOOKING", "severity": "CRITICAL", "badge": "Hard Conflict",
                    "title": f"Room Collision: {room}",
                    "day": day, "time_slot": slot,
                    "description": f"{room} is double-booked on {day} at {slot} by: {details}.",
                    "involved_entries": [e.get("id") for e in entries],
                    "target_room": room,
                })

        # ---- 3. Section (student) clash -------------------------------
        for (section, day, slot), entries in section_slot_map.items():
            if len(entries) > 1:
                details = " & ".join(f"{e.get('course_code')} by {e.get('faculty_name')}" for e in entries)
                conflicts.append({
                    "id": f"SEC|{section}|{day}|{slot}",
                    "type": "SECTION_CLASH", "severity": "CRITICAL", "badge": "Hard Conflict",
                    "title": f"Section Clash: {section}",
                    "day": day, "time_slot": slot,
                    "description": f"Students of {section} have {len(entries)} classes at the same time "
                                   f"on {day} {slot}: {details}.",
                    "involved_entries": [e.get("id") for e in entries],
                    "target_section": section,
                })

        # ---- 4 & 5. Daily limit and back-to-back fatigue --------------
        slot_index = {s: i for i, s in enumerate(time_slots)}
        max_daily = self.rules["max_daily_hours"]
        max_streak_allowed = self.rules["max_consecutive_hours"]
        lunch_after = self.rules["lunch_after"]

        for f_name, day_dict in faculty_day_entries.items():
            for day, entries in day_dict.items():
                ids = [e.get("id") for e in entries]

                if len(entries) > max_daily:
                    conflicts.append({
                        "id": f"DAILY|{f_name}|{day}",
                        "type": "DAILY_LIMIT_EXCEEDED", "severity": "WARNING", "badge": "Soft Warning",
                        "title": f"Daily Teaching Limit Exceeded: {f_name}",
                        "day": day, "time_slot": "Full Day",
                        "description": f"{f_name} has {len(entries)} classes on {day}. "
                                       f"The daily maximum is {max_daily}.",
                        "involved_entries": ids, "target_faculty": f_name,
                    })

                # Find the longest run of back-to-back slots.
                # The lunch break breaks the run (BUG FIX: earlier the 12-1 and 2-3
                # slots were counted as continuous even though lunch is in between).
                indices = sorted({slot_index[e.get("time_slot")] for e in entries
                                  if e.get("time_slot") in slot_index})
                streak, longest = 1, (1 if indices else 0)
                for k in range(1, len(indices)):
                    previous_slot = time_slots[indices[k - 1]]
                    if indices[k] == indices[k - 1] + 1 and previous_slot != lunch_after:
                        streak += 1
                    else:
                        streak = 1
                    longest = max(longest, streak)

                if longest > max_streak_allowed:
                    conflicts.append({
                        "id": f"FATIGUE|{f_name}|{day}",
                        "type": "CONSECUTIVE_FATIGUE", "severity": "WARNING", "badge": "Fatigue Warning",
                        "title": f"Back-to-Back Classes: {f_name}",
                        "day": day, "time_slot": f"{longest} hours continuous",
                        "description": f"{f_name} has {longest} classes in a row on {day} without a break "
                                       f"(limit is {max_streak_allowed}).",
                        "involved_entries": ids, "target_faculty": f_name,
                    })

        # ---- 7, 8, 9, 10. Checks on each single class -----------------
        for entry in schedule_entries:
            eid = entry.get("id")
            f_name = entry.get("faculty_name")
            room_name = entry.get("room")
            room = self.rooms.get(room_name)
            section = self.sections.get(entry.get("section"))
            where = f"{entry.get('course_code')} ({entry.get('section')}) on {entry.get('day')} {entry.get('time_slot')}"

            def warn(kind, badge, title, text):
                conflicts.append({
                    "id": f"{kind}|{eid}", "type": kind, "severity": "WARNING", "badge": badge,
                    "title": title, "day": entry.get("day"), "time_slot": entry.get("time_slot"),
                    "description": text, "involved_entries": [eid],
                })

            # 10. Unknown / invalid data (useful after importing a file)
            if entry.get("day") not in working_days:
                warn("INVALID_DAY", "Data Problem", f"Invalid Day: {entry.get('day')}",
                     f"{where}: '{entry.get('day')}' is not a working day in Settings.")
            if entry.get("time_slot") not in slot_index:
                warn("INVALID_SLOT", "Data Problem", f"Invalid Time Slot: {entry.get('time_slot')}",
                     f"{where}: '{entry.get('time_slot')}' is not one of the time slots in Settings.")
            if self.catalog and f_name not in self.catalog:
                warn("UNKNOWN_FACULTY", "Data Problem", f"Unregistered Faculty: {f_name}",
                     f"{where}: {f_name} is not in the faculty list. Add them on the Faculty page.")
            if self.rooms and room is None:
                warn("UNKNOWN_ROOM", "Data Problem", f"Unregistered Room: {room_name}",
                     f"{where}: room {room_name} is not in the rooms list.")

            # 7. Lab subject in a lecture hall
            if room is not None and self.is_lab_course(entry) and room["room_type"] != "Lab":
                warn("LAB_ROOM_MISMATCH", "Room Type", f"Lab Class in a Lecture Hall: {room_name}",
                     f"{where} is a lab subject but {room_name} is a {room['room_type']}.")

            # 8. Room capacity
            if room is not None and section is not None and section["strength"] > room["capacity"]:
                warn("ROOM_TOO_SMALL", "Capacity", f"Room Too Small: {room_name}",
                     f"{entry.get('section')} has {section['strength']} students but {room_name} "
                     f"seats only {room['capacity']}.")

            # 9. Teacher qualified for the subject?
            if not self.can_teach(f_name, entry.get("course_code")):
                warn("NOT_QUALIFIED", "Qualification", f"Subject Not Mapped: {f_name}",
                     f"{f_name} is not listed as a teacher for {entry.get('course_code')}. "
                     f"Update the subject mapping on the Faculty page if this is correct.")

        # ---- 11. Multi-Hour Continuous Lab Integrity ------------------
        # If a lab class is scheduled on a day, check if it forms a contiguous
        # block (e.g. 2 hours) or is fragmented as isolated 1-hour sessions.
        section_day_labs = defaultdict(lambda: defaultdict(list))
        for entry in schedule_entries:
            if self.is_lab_course(entry):
                sec = entry.get("section")
                day = entry.get("day")
                code = entry.get("course_code")
                slot = entry.get("time_slot")
                if slot in slot_index:
                    section_day_labs[(sec, code)][day].append(entry)

        for (sec, code), days_dict in section_day_labs.items():
            for day, lab_entries in days_dict.items():
                if len(lab_entries) > 1:
                    # Check room consistency
                    rooms_used = {e.get("room") for e in lab_entries}
                    if len(rooms_used) > 1:
                        conflicts.append({
                            "id": f"LAB_ROOM_SPLIT|{sec}|{code}|{day}",
                            "type": "LAB_ROOM_SPLIT", "severity": "WARNING", "badge": "Lab Integrity",
                            "title": f"Lab Room Split: {code} ({sec})",
                            "day": day, "time_slot": "Multi-slot",
                            "description": f"Lab {code} for {sec} on {day} is split across different rooms: {', '.join(rooms_used)}.",
                            "involved_entries": [e.get("id") for e in lab_entries],
                        })
                    # Check contiguous sequence
                    idxs = sorted([slot_index[e.get("time_slot")] for e in lab_entries])
                    is_contiguous = True
                    for k in range(1, len(idxs)):
                        prev_s = time_slots[idxs[k - 1]]
                        if idxs[k] != idxs[k - 1] + 1 or prev_s == lunch_after:
                            is_contiguous = False
                            break
                    if not is_contiguous:
                        conflicts.append({
                            "id": f"LAB_FRAGMENTED|{sec}|{code}|{day}",
                            "type": "LAB_FRAGMENTED", "severity": "WARNING", "badge": "Lab Integrity",
                            "title": f"Fragmented Lab Block: {code} ({sec})",
                            "day": day, "time_slot": "Non-contiguous",
                            "description": f"Lab sessions for {code} ({sec}) on {day} are not scheduled back-to-back as a continuous block.",
                            "involved_entries": [e.get("id") for e in lab_entries],
                        })

        # ---- 12. Open Electives & Cross-Department Basket Conflicts ---
        # When an elective course from a basket is scheduled, students from multiple
        # sections are attending it simultaneously. Any other course scheduled for
        # those participating sections at the exact same slot causes a cross-department clash.
        if self.elective_baskets:
            # Map course_code -> list of affected sections
            course_basket_sections = defaultdict(list)
            for b in self.elective_baskets:
                c_code = b.get("course_code")
                sec_str = b.get("sections", "")
                secs = [s.strip() for s in sec_str.replace(";", ",").split(",") if s.strip()]
                course_basket_sections[c_code].extend(secs)

            for entry in schedule_entries:
                c_code = entry.get("course_code")
                if c_code in course_basket_sections:
                    day = entry.get("day")
                    slot = entry.get("time_slot")
                    enrolled_secs = course_basket_sections[c_code]
                    for enrolled_sec in enrolled_secs:
                        # Check if this enrolled section has other non-elective classes at this same day & slot
                        parallel_classes = section_slot_map.get((enrolled_sec, day, slot), [])
                        for p in parallel_classes:
                            if p.get("id") != entry.get("id") and p.get("course_code") != c_code:
                                conflicts.append({
                                    "id": f"ELECTIVE_CLASH|{c_code}|{enrolled_sec}|{day}|{slot}",
                                    "type": "ELECTIVE_SECTION_CLASH", "severity": "CRITICAL", "badge": "Hard Conflict",
                                    "title": f"Cross-Department Elective Clash: {c_code}",
                                    "day": day, "time_slot": slot,
                                    "description": f"Students of {enrolled_sec} enrolled in Open Elective {c_code} "
                                                   f"have a conflicting parallel class: {p.get('course_code')} ({p.get('faculty_name')}) "
                                                   f"on {day} at {slot}.",
                                    "involved_entries": [entry.get("id"), p.get("id")],
                                    "target_section": enrolled_sec,
                                })

        # ---- 6. Weekly workload per faculty ---------------------------
        workload_distribution = []
        utilization_list = []
        underload_limit = self.rules["underload_percent"] / 100

        all_names = sorted(set(self.catalog.keys()) | set(faculty_total_hours.keys()))
        for f_name in all_names:
            info = self.catalog.get(f_name, {"designation": "Unregistered", "department": "-",
                                             "max_hours": 16})
            assigned = faculty_total_hours.get(f_name, 0)
            max_h = info["max_hours"] or 1
            ratio = assigned / max_h
            utilization_list.append(ratio)

            if assigned == 0:
                status = "Unassigned"
            elif assigned > max_h:
                status = "Overloaded"
                conflicts.append({
                    "id": f"OVERLOAD|{f_name}",
                    "type": "WEEKLY_OVERLOAD", "severity": "WARNING", "badge": "Overload Warning",
                    "title": f"Weekly Workload Exceeded: {f_name}",
                    "day": "Weekly Total", "time_slot": f"{assigned} / {max_h} hrs",
                    "description": f"{f_name} ({info['designation']}) has {assigned} hrs/week, "
                                   f"which is {assigned - max_h} hrs above the limit of {max_h} hrs.",
                    "involved_entries": [], "target_faculty": f_name,
                })
            elif ratio < underload_limit:
                status = "Underloaded"
            else:
                status = "Balanced"

            workload_distribution.append({
                "faculty_name": f_name,
                "designation": info["designation"],
                "department": info["department"],
                "assigned_hours": assigned,
                "max_hours": max_h,
                "utilization_percentage": round(ratio * 100, 1),
                "status": status,
            })

        # Workload Balance Index (WBI).
        # BUG FIX: we now compare utilization % (hours / own cap) instead of raw
        # hours, because a Professor (cap 14) and an Assistant Professor (cap 18)
        # teaching the same hours are NOT equally loaded.
        # 0 spread -> 100%. A spread (std. deviation) of 0.5 (50 %) -> 50%.
        wbi_score = 100.0
        if len(utilization_list) > 1:
            spread = float(np.std(utilization_list))
            wbi_score = round(max(0.0, min(100.0, 100.0 - spread * 100)), 1)

        suggestions = self._generate_suggestions(conflicts, schedule_entries)

        return {
            "total_conflicts": len(conflicts),
            "critical_conflicts": sum(1 for c in conflicts if c["severity"] == "CRITICAL"),
            "warning_conflicts": sum(1 for c in conflicts if c["severity"] == "WARNING"),
            "conflicts_list": conflicts,
            "workload_distribution": workload_distribution,
            "workload_balance_score": wbi_score,
            "suggestions": suggestions,
        }

    # ------------------------------------------------------------------
    # Suggestions to fix conflicts
    # ------------------------------------------------------------------
    def _build_busy_sets(self, schedule_entries):
        """Sets that tell us quickly who/what is busy at a day+slot."""
        busy = {"faculty": set(), "room": set(), "section": set()}
        load = defaultdict(int)
        per_day = defaultdict(int)
        for e in schedule_entries:
            key = (e.get("day"), e.get("time_slot"))
            busy["faculty"].add((e.get("faculty_name"),) + key)
            busy["room"].add((e.get("room"),) + key)
            busy["section"].add((e.get("section"),) + key)
            load[e.get("faculty_name")] += 1
            per_day[(e.get("faculty_name"), e.get("day"))] += 1
        return busy, load, per_day

    def find_substitute(self, entry, busy, load, exclude=()):
        """Best other teacher for this class: same department, free at that time,
        below their weekly cap, preferably qualified, with the lowest load."""
        day, slot = entry.get("day"), entry.get("time_slot")
        original = entry.get("faculty_name")
        dept = self.catalog.get(original, {}).get("department", entry.get("department"))

        candidates = []
        for f_name, info in self.catalog.items():
            if f_name == original or f_name in exclude:
                continue
            if info["department"] != dept:
                continue
            if (f_name, day, slot) in busy["faculty"]:
                continue
            if load[f_name] + 1 > info["max_hours"]:
                continue
            qualified = self.can_teach(f_name, entry.get("course_code"))
            # sort key: qualified first (False < True so we use "not"), then lowest load
            candidates.append((not qualified, load[f_name], f_name))

        candidates.sort()
        return [(name, load_now) for _, load_now, name in candidates]

    def find_free_room(self, entry, busy):
        """A room that is free at that time, of the right type and big enough.
        BUG FIX: earlier this always returned 'LH-203' without checking."""
        day, slot = entry.get("day"), entry.get("time_slot")
        need_lab = self.is_lab_course(entry)
        section = self.sections.get(entry.get("section"))
        strength = section["strength"] if section else 0

        options = []
        for name, room in self.rooms.items():
            if name == entry.get("room") or (name, day, slot) in busy["room"]:
                continue
            if need_lab and room["room_type"] != "Lab":
                continue
            if room["capacity"] < strength:
                continue
            # prefer the right type, then the smallest room that fits (saves big rooms)
            wrong_type = (room["room_type"] == "Lab") != need_lab
            options.append((wrong_type, room["capacity"], name))
        options.sort()
        return options[0][2] if options else None

    def find_free_slot(self, entry, busy, per_day):
        """First day + slot where the teacher, the section AND the room are all free."""
        f_name, section, room = entry.get("faculty_name"), entry.get("section"), entry.get("room")
        for day in self.rules["working_days"]:
            if per_day[(f_name, day)] >= self.rules["max_daily_hours"]:
                continue
            for slot in self.rules["time_slots"]:
                if day == entry.get("day") and slot == entry.get("time_slot"):
                    continue
                if ((f_name, day, slot) not in busy["faculty"]
                        and (section, day, slot) not in busy["section"]
                        and (room, day, slot) not in busy["room"]):
                    return day, slot
        return None

    def _generate_suggestions(self, conflicts, schedule_entries):
        suggestions = []
        lookup = {e.get("id"): e for e in schedule_entries}
        busy, load, per_day = self._build_busy_sets(schedule_entries)

        def course_label(e):
            return f"{e.get('course_code')} ({e.get('section')})"

        def move_slot(c, e, why):
            free = self.find_free_slot(e, busy, per_day)
            if free:
                suggestions.append({
                    "conflict_id": c["id"], "entry_id": e.get("id"), "action": "MOVE_SLOT",
                    "course": course_label(e),
                    "recommended_day": free[0], "recommended_slot": free[1],
                    "reason": f"{why} Move {course_label(e)} to {free[0]} {free[1]} - "
                              f"{e.get('faculty_name')}, {e.get('section')} and {e.get('room')} are all free then.",
                })

        def change_room(c, e, why):
            room = self.find_free_room(e, busy)
            if room:
                suggestions.append({
                    "conflict_id": c["id"], "entry_id": e.get("id"), "action": "CHANGE_ROOM",
                    "course": course_label(e), "current_room": e.get("room"),
                    "recommended_room": room,
                    "reason": f"{why} Move {course_label(e)} to {room}, which is free on "
                              f"{e.get('day')} at {e.get('time_slot')}.",
                })
                return True
            return False

        for c in conflicts:
            involved = [lookup[i] for i in c.get("involved_entries", []) if i in lookup]

            if c["type"] == "FACULTY_TIME_CLASH" and len(involved) >= 2:
                e = involved[1]   # keep the first class, fix the second one
                subs = self.find_substitute(e, busy, load)
                if subs:
                    name, current = subs[0]
                    suggestions.append({
                        "conflict_id": c["id"], "entry_id": e.get("id"), "action": "REASSIGN_FACULTY",
                        "course": course_label(e), "current_faculty": e.get("faculty_name"),
                        "recommended_faculty": name,
                        "reason": f"Give {course_label(e)} to {name}: free on {e.get('day')} at "
                                  f"{e.get('time_slot')} and has spare capacity "
                                  f"({current} / {self.max_hours_of(name)} hrs).",
                    })
                else:
                    move_slot(c, e, "No other teacher is free.")

            elif c["type"] == "ROOM_DOUBLE_BOOKING" and len(involved) >= 2:
                e = involved[1]
                if not change_room(c, e, "Room clash."):
                    move_slot(c, e, "No suitable room is free at that time.")

            elif c["type"] == "SECTION_CLASH" and len(involved) >= 2:
                move_slot(c, involved[1], "Students cannot attend two classes at once.")

            elif c["type"] in ("LAB_ROOM_MISMATCH", "ROOM_TOO_SMALL") and involved:
                change_room(c, involved[0], "Better room available.")

            elif c["type"] == "WEEKLY_OVERLOAD":
                # Try to hand over one of this teacher's classes to someone with spare time
                own = [e for e in schedule_entries if e.get("faculty_name") == c["target_faculty"]]
                for e in own:
                    subs = self.find_substitute(e, busy, load)
                    qualified = [s for s in subs if self.can_teach(s[0], e.get("course_code"))]
                    if qualified:
                        name, current = qualified[0]
                        suggestions.append({
                            "conflict_id": c["id"], "entry_id": e.get("id"), "action": "REASSIGN_FACULTY",
                            "course": course_label(e), "current_faculty": e.get("faculty_name"),
                            "recommended_faculty": name,
                            "reason": f"Reduce {e.get('faculty_name')}'s load: give {course_label(e)} on "
                                      f"{e.get('day')} {e.get('time_slot')} to {name} "
                                      f"({current} / {self.max_hours_of(name)} hrs).",
                        })
                        break

        return suggestions
