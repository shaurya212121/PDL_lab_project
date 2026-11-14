"""
Timetable Versioning & Visual Diff Engine.
Compares two timetable snapshots and produces side-by-side visual difference views.
"""

DAY_ORDER = {
    "Monday": 1,
    "Tuesday": 2,
    "Wednesday": 3,
    "Thursday": 4,
    "Friday": 5,
    "Saturday": 6,
    "Sunday": 7,
}


def diff_timetables(old_slots, new_slots):
    """
    Compare two timetable snapshots (old_slots and new_slots).
    Each element is a dict containing:
      day, time_slot, section, batch, course_code, course_name, faculty_name, room.

    Returns a dict with:
      summary: counts of added, removed, modified, unchanged.
      diffs: list of diff entries sorted by day, time_slot, section.
    """
    def slot_key(e):
        return (
            e.get("day", "").strip(),
            e.get("time_slot", "").strip(),
            e.get("section", "").strip(),
            e.get("batch", "All").strip() or "All",
        )

    old_by_slot = {}
    for e in old_slots:
        k = slot_key(e)
        old_by_slot.setdefault(k, []).append(dict(e))

    new_by_slot = {}
    for e in new_slots:
        k = slot_key(e)
        new_by_slot.setdefault(k, []).append(dict(e))

    all_keys = set(old_by_slot.keys()) | set(new_by_slot.keys())

    diff_items = []

    for k in all_keys:
        day, time_slot, section, batch = k
        old_list = list(old_by_slot.get(k, []))
        new_list = list(new_by_slot.get(k, []))

        # 1. Match identical course_codes
        matched_old = []
        for o in old_list:
            match_idx = None
            for idx, n in enumerate(new_list):
                if n.get("course_code") == o.get("course_code"):
                    match_idx = idx
                    break

            if match_idx is not None:
                n = new_list.pop(match_idx)
                matched_old.append(o)

                # Check if faculty or room changed
                changes = []
                if o.get("faculty_name") != n.get("faculty_name"):
                    changes.append(f"Faculty: {o.get('faculty_name')} → {n.get('faculty_name')}")
                if o.get("room") != n.get("room"):
                    changes.append(f"Room: {o.get('room')} → {n.get('room')}")

                if changes:
                    diff_items.append({
                        "day": day,
                        "time_slot": time_slot,
                        "section": section,
                        "batch": batch,
                        "status": "modified",
                        "old": o,
                        "new": n,
                        "changes": changes,
                    })
                else:
                    diff_items.append({
                        "day": day,
                        "time_slot": time_slot,
                        "section": section,
                        "batch": batch,
                        "status": "unchanged",
                        "old": o,
                        "new": n,
                        "changes": [],
                    })

        for m in matched_old:
            old_list.remove(m)

        # 2. Pair remaining entries at the exact same slot (subject swap/reassignment)
        while old_list and new_list:
            o = old_list.pop(0)
            n = new_list.pop(0)
            changes = [
                f"Course: {o.get('course_code')} ({o.get('course_name') or ''}) → {n.get('course_code')} ({n.get('course_name') or ''})"
            ]
            if o.get("faculty_name") != n.get("faculty_name"):
                changes.append(f"Faculty: {o.get('faculty_name')} → {n.get('faculty_name')}")
            if o.get("room") != n.get("room"):
                changes.append(f"Room: {o.get('room')} → {n.get('room')}")

            diff_items.append({
                "day": day,
                "time_slot": time_slot,
                "section": section,
                "batch": batch,
                "status": "modified",
                "old": o,
                "new": n,
                "changes": changes,
            })

        # 3. Remaining in new_list -> Added
        for n in new_list:
            diff_items.append({
                "day": day,
                "time_slot": time_slot,
                "section": section,
                "batch": batch,
                "status": "added",
                "old": None,
                "new": n,
                "changes": [f"New class added: {n.get('course_code')} with {n.get('faculty_name')} in {n.get('room')}"],
            })

        # 4. Remaining in old_list -> Removed
        for o in old_list:
            diff_items.append({
                "day": day,
                "time_slot": time_slot,
                "section": section,
                "batch": batch,
                "status": "removed",
                "old": o,
                "new": None,
                "changes": [f"Class removed: {o.get('course_code')} with {o.get('faculty_name')} in {o.get('room')}"],
            })

    # Sort diffs by Day, Time, Section, Batch
    def sort_key(d):
        return (
            DAY_ORDER.get(d["day"], 99),
            d["time_slot"],
            d["section"],
            d["batch"],
        )

    diff_items.sort(key=sort_key)

    counts = {
        "added": sum(1 for d in diff_items if d["status"] == "added"),
        "removed": sum(1 for d in diff_items if d["status"] == "removed"),
        "modified": sum(1 for d in diff_items if d["status"] == "modified"),
        "unchanged": sum(1 for d in diff_items if d["status"] == "unchanged"),
    }

    return {
        "summary": {
            "total_old": len(old_slots),
            "total_new": len(new_slots),
            **counts,
            "total_changes": counts["added"] + counts["removed"] + counts["modified"],
        },
        "diffs": diff_items,
    }
