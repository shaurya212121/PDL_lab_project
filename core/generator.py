
from collections import defaultdict
import random

class TimetableGenerator:
    def __init__(self, faculty, rooms, sections, subjects, faculty_subjects=None, settings=None):
        self.faculty = {f["name"]: f for f in faculty}
        self.rooms = {r["name"]: r for r in rooms}
        self.sections = {s["name"]: s for s in sections}
        self.subjects = {s["code"]: s for s in subjects}
        self.faculty_subjects = faculty_subjects or {}

        settings = settings or {}
        self.working_days = list(settings.get("working_days", [
            "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"
        ]))
        self.time_slots = list(settings.get("time_slots", [
            "09:00 - 10:00", "10:00 - 11:00", "11:00 - 12:00", "12:00 - 01:00",
            "02:00 - 03:00", "03:00 - 04:00", "04:00 - 05:00"
        ]))
        self.lunch_after = settings.get("lunch_after", "12:00 - 01:00")
        self.slot_indices = {s: i for i, s in enumerate(self.time_slots)}

    def get_valid_slot_sequences(self, duration=1):
        sequences = []
        for day in self.working_days:
            n = len(self.time_slots)
            for i in range(n - duration + 1):
                chunk = self.time_slots[i:i + duration]
                crosses_lunch = False
                for s in chunk[:-1]:
                    if s == self.lunch_after:
                        crosses_lunch = True
                        break
                if not crosses_lunch:
                    sequences.append((day, chunk))
        return sequences

    def get_candidate_faculty(self, course_code, preferred_faculty=None):
        if preferred_faculty and preferred_faculty in self.faculty:
            return [preferred_faculty]

        allowed = self.faculty_subjects.get(course_code, [])
        if allowed:
            cands = [f for f in allowed if f in self.faculty]
            if cands:
                return cands

        subj = self.subjects.get(course_code, {})
        subj_dept = subj.get("department")
        dept_fac = [f["name"] for f in self.faculty.values() if f.get("department") == subj_dept]
        if dept_fac:
            return dept_fac

        return list(self.faculty.keys())

    def get_candidate_rooms(self, is_lab, min_capacity, preferred_room=None):
        if preferred_room and preferred_room in self.rooms:
            r = self.rooms[preferred_room]
            if r["capacity"] >= min_capacity and (not is_lab or r["room_type"].lower() == "lab"):
                return [preferred_room]

        matching = []
        for r_name, r in self.rooms.items():
            r_type = r.get("room_type", "").lower()
            if is_lab and r_type != "lab":
                continue
            if r.get("capacity", 0) < min_capacity:
                continue
            matching.append(r_name)

        matching.sort(key=lambda name: (
            0 if (is_lab and self.rooms[name].get("room_type", "").lower() == "lab") else
            (0 if (not is_lab and self.rooms[name].get("room_type", "").lower() != "lab") else 1),
            self.rooms[name].get("capacity", 999)
        ))
        return matching

    def generate(self, requirements, existing_schedule=None, max_backtracks=5000):
        faculty_busy = set()
        room_busy = set()
        section_busy = set()
        faculty_hours = defaultdict(int)
        section_day_courses = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

        placed_entries = []
        if existing_schedule:
            for e in existing_schedule:
                f = e.get("faculty_name")
                r = e.get("room")
                sec = e.get("section")
                d = e.get("day")
                s = e.get("time_slot")
                c = e.get("course_code")
                faculty_busy.add((f, d, s))
                room_busy.add((r, d, s))
                section_busy.add((sec, d, s))
                faculty_hours[f] += 1
                section_day_courses[sec][d][c] += 1
                placed_entries.append(dict(e))

        tasks = []
        task_id = 1
        for req in requirements:
            sec = req["section"]
            c_code = req["course_code"]
            total_hours = int(req.get("hours_per_week", 3))
            duration = int(req.get("duration", 1))
            pref_fac = req.get("faculty_name")
            pref_room = req.get("preferred_room")

            is_lab = False
            subj = self.subjects.get(c_code)
            if subj:
                is_lab = bool(subj.get("is_lab"))
            elif "lab" in c_code.lower():
                is_lab = True

            if is_lab and "duration" not in req:
                duration = 2

            strength = self.sections.get(sec, {}).get("strength", 50)
            candidate_faculty = self.get_candidate_faculty(c_code, pref_fac)
            candidate_rooms = self.get_candidate_rooms(is_lab, strength, pref_room)

            hours_needed = total_hours
            while hours_needed > 0:
                block_dur = min(duration, hours_needed)
                tasks.append({
                    "id": f"GEN_T{task_id}",
                    "section": sec,
                    "course_code": c_code,
                    "course_name": subj.get("name", c_code) if subj else c_code,
                    "department": subj.get("department", self.sections.get(sec, {}).get("department", "CSE")),
                    "is_lab": is_lab,
                    "duration": block_dur,
                    "candidate_faculty": candidate_faculty,
                    "candidate_rooms": candidate_rooms,
                })
                task_id += 1
                hours_needed -= block_dur

        tasks.sort(key=lambda t: (
            -t["duration"],
            0 if t["is_lab"] else 1,
            len(t["candidate_faculty"]) * len(t["candidate_rooms"])
        ))

        slot_sequences_by_dur = {
            1: self.get_valid_slot_sequences(1),
            2: self.get_valid_slot_sequences(2),
            3: self.get_valid_slot_sequences(3)
        }

        backtracks = [0]

        def backtrack(task_idx):
            if task_idx == len(tasks):
                return True

            if backtracks[0] >= max_backtracks:
                return False

            task = tasks[task_idx]
            dur = task["duration"]
            seqs = slot_sequences_by_dur.get(dur, self.get_valid_slot_sequences(dur))

            available_placements = []

            for fac in task["candidate_faculty"]:
                fac_cap = self.faculty.get(fac, {}).get("max_hours", 18)
                if faculty_hours[fac] + dur > fac_cap:
                    continue

                for rm in task["candidate_rooms"]:
                    for day, slots in seqs:
                        if not task["is_lab"] and section_day_courses[task["section"]][day][task["course_code"]] >= 1:
                            continue

                        clash = False
                        for s in slots:
                            if ((fac, day, s) in faculty_busy or
                                (rm, day, s) in room_busy or
                                (task["section"], day, s) in section_busy):
                                clash = True
                                break

                        if not clash:
                            score = (
                                section_day_courses[task["section"]][day][task["course_code"]] * 10 +
                                len([s for s in self.time_slots if (fac, day, s) in faculty_busy])
                            )
                            available_placements.append((score, fac, rm, day, slots))

            available_placements.sort(key=lambda p: p[0])

            for _, fac, rm, day, slots in available_placements:
                for s in slots:
                    faculty_busy.add((fac, day, s))
                    room_busy.add((rm, day, s))
                    section_busy.add((task["section"], day, s))

                faculty_hours[fac] += dur
                section_day_courses[task["section"]][day][task["course_code"]] += 1

                assigned_entries = []
                for s in slots:
                    entry = {
                        "faculty_name": fac,
                        "department": task["department"],
                        "course_code": task["course_code"],
                        "course_name": task["course_name"],
                        "section": task["section"],
                        "day": day,
                        "time_slot": s,
                        "room": rm
                    }
                    assigned_entries.append(entry)
                    placed_entries.append(entry)

                if backtrack(task_idx + 1):
                    return True

                backtracks[0] += 1
                for _ in range(len(assigned_entries)):
                    placed_entries.pop()

                for s in slots:
                    faculty_busy.remove((fac, day, s))
                    room_busy.remove((rm, day, s))
                    section_busy.remove((task["section"], day, s))

                faculty_hours[fac] -= dur
                section_day_courses[task["section"]][day][task["course_code"]] -= 1

            return False

        success = backtrack(0)

        stats = {
            "total_tasks": len(tasks),
            "placed_classes": len(placed_entries),
            "backtracks": backtracks[0],
            "success": success
        }

        return success, placed_entries, stats
