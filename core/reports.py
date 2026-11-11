"""
Summary numbers and charts for the Reports page.

pandas  -> counting / grouping the timetable
matplotlib -> drawing the charts as PNG images
"""

import io
import matplotlib
matplotlib.use("Agg")  # draw images without opening a window (needed on a server)
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import MaxNLocator

# Chart colours
BLUE = "#2a78d6"
TEXT = "#0b0b0b"
MUTED = "#52514e"
GRID = "#e4e3df"
STATUS_COLORS = {          # colour + label always appear together in the legend
    "Balanced": "#0ca30c",
    "Underloaded": "#fab219",
    "Overloaded": "#d03b3b",
    "Unassigned": "#b8b7b0",
}


def summary_stats(timetable, rooms, settings, report):
    """Key numbers shown at the top of the Reports page."""
    df = pd.DataFrame(timetable)
    total_slots_per_room = len(settings["working_days"]) * len(settings["time_slots"])

    stats = {
        "total_classes": len(df),
        "faculty_count": len(report["workload_distribution"]),
        "critical": report["critical_conflicts"],
        "warnings": report["warning_conflicts"],
        "busiest_day": "-",
        "busiest_day_count": 0,
        "top_department": "-",
        "top_department_hours": 0,
        "room_usage_percent": 0,
        "overloaded": sum(1 for w in report["workload_distribution"] if w["status"] == "Overloaded"),
        "underloaded": sum(1 for w in report["workload_distribution"] if w["status"] == "Underloaded"),
    }
    if df.empty:
        return stats

    per_day = df["day"].value_counts()
    stats["busiest_day"] = per_day.idxmax()
    stats["busiest_day_count"] = int(per_day.max())

    per_dept = df["department"].value_counts()
    stats["top_department"] = per_dept.idxmax()
    stats["top_department_hours"] = int(per_dept.max())

    if rooms and total_slots_per_room:
        room_names = {r["name"] for r in rooms}
        used = df[df["room"].isin(room_names)].drop_duplicates(["room", "day", "time_slot"])
        stats["room_usage_percent"] = round(100 * len(used) / (len(rooms) * total_slots_per_room), 1)
    return stats


def room_usage_table(timetable, rooms, settings):
    """How many slots each room is used per week, and as a %."""
    total = len(settings["working_days"]) * len(settings["time_slots"]) or 1
    df = pd.DataFrame(timetable)
    rows = []
    for r in rooms:
        used = 0 if df.empty else len(df[df["room"] == r["name"]].drop_duplicates(["day", "time_slot"]))
        rows.append({"room": r["name"], "type": r["room_type"], "used": used,
                     "total": total, "percent": round(100 * used / total, 1)})
    return rows


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------
def _style(ax):
    """Same clean look for every chart."""
    for side in ["top", "right", "left"]:
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _to_png(fig):
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=110, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buffer.seek(0)
    return buffer


def _empty_chart(message):
    fig, ax = plt.subplots(figsize=(7, 1.5))
    ax.axis("off")
    ax.text(0.5, 0.5, message, ha="center", va="center", color=MUTED, fontsize=11)
    return _to_png(fig)


def workload_chart(distribution):
    """Horizontal bar per teacher: % of weekly cap used, coloured by status."""
    if not distribution:
        return _empty_chart("No faculty added yet")

    data = sorted(distribution, key=lambda w: w["utilization_percentage"])
    names = [w["faculty_name"] for w in data]
    values = [w["utilization_percentage"] for w in data]
    colors = [STATUS_COLORS.get(w["status"], BLUE) for w in data]

    fig, ax = plt.subplots(figsize=(8, 0.4 * len(data) + 1.2))
    ax.barh(names, values, color=colors, height=0.55)
    ax.axvline(100, color=TEXT, linewidth=1, linestyle="--")
    ax.text(100, len(data) - 0.4, " weekly cap", color=TEXT, fontsize=8, va="bottom")
    for i, w in enumerate(data):
        ax.text(w["utilization_percentage"] + 1.5, i, f"{w['assigned_hours']}/{w['max_hours']} h",
                va="center", fontsize=8, color=MUTED)
    ax.set_xlim(0, max(115, max(values) + 15))
    ax.set_xlabel("% of weekly hour limit used", color=MUTED, fontsize=9)
    _style(ax)

    used_status = [s for s in STATUS_COLORS if any(w["status"] == s for w in data)]
    handles = [plt.Rectangle((0, 0), 1, 1, color=STATUS_COLORS[s]) for s in used_status]
    ax.legend(handles, used_status, loc="lower right", frameon=False, fontsize=8)
    return _to_png(fig)


def count_chart(timetable, column, order=None, xlabel="Classes per week"):
    """Simple horizontal bar chart counting classes by a column (day, department ...)."""
    df = pd.DataFrame(timetable)
    if df.empty:
        return _empty_chart("The timetable is empty")
    counts = df[column].value_counts()
    if order:
        counts = counts.reindex(order, fill_value=0)
    counts = counts.iloc[::-1]  # first item at the top

    fig, ax = plt.subplots(figsize=(6, 0.4 * len(counts) + 1.0))
    ax.barh(counts.index.astype(str), counts.values, color=BLUE, height=0.55)
    for i, v in enumerate(counts.values):
        ax.text(v + 0.1, i, str(v), va="center", fontsize=8, color=MUTED)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))  # no "0.5 classes"
    ax.set_xlabel(xlabel, color=MUTED, fontsize=9)
    _style(ax)
    return _to_png(fig)


def room_chart(usage_rows):
    if not usage_rows:
        return _empty_chart("No rooms added yet")
    rows = usage_rows[::-1]
    fig, ax = plt.subplots(figsize=(8, 0.4 * len(rows) + 1.0))
    ax.barh([r["room"] for r in rows], [r["percent"] for r in rows], color=BLUE, height=0.55)
    for i, r in enumerate(rows):
        ax.text(r["percent"] + 0.5, i, f"{r['percent']}%", va="center", fontsize=8, color=MUTED)
    ax.set_xlim(0, 105)
    ax.set_xlabel("% of weekly slots in use", color=MUTED, fontsize=9)
    _style(ax)
    return _to_png(fig)
