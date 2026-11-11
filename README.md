# ClashAudit — Faculty Workload Distribution & Conflict Detector

ClashAudit is a web application for colleges that checks a weekly timetable for clashes, keeps every faculty member's teaching load within AICTE / UGC limits, and helps the office arrange substitutes when a teacher is on leave. It is written in Python (Flask, SQLite, pandas, matplotlib and scikit-learn) and runs on any ordinary computer. Other computers on the college network can open it in a browser.

*Python Data Lab (PDL) mini project.*

---

## 1. The problem

A department's timetable has hundreds of entries: faculty, subjects, sections, rooms, days and time slots. When it is prepared by hand in a spreadsheet, mistakes are common and are usually found only after the semester starts:

- one teacher is given **two classes at the same time**
- one room is **booked twice** for the same hour
- one section of students has **two lectures at once**
- a lab is placed in an ordinary classroom, or a class of 70 is put in a 40-seat room
- some faculty get **more hours than the AICTE / UGC limit** while others are under-used
- a teacher gets **four or five classes back-to-back** without a break
- when someone is on leave, finding a free and suitable substitute is done by phone calls

ClashAudit finds all of these automatically, explains each one in plain English and suggests a fix.

---

## 2. Features

### Timetable checking
| Check | Type | What it means |
|---|---|---|
| Faculty double-booking | **Hard clash** | Same teacher, two classes, same day and slot |
| Room double-booking | **Hard clash** | Same room, two classes, same day and slot |
| Section clash | **Hard clash** | Same student section, two classes, same day and slot |
| Daily limit | Warning | More classes in a day than allowed (default 5) |
| Back-to-back fatigue | Warning | More consecutive classes than allowed (default 3). The lunch break resets the count |
| Weekly overload | Warning | Weekly hours above the designation's cap (14 / 16 / 18) |
| Lab in a lecture hall | Warning | A lab subject is scheduled in a non-lab room |
| Room too small | Warning | Section strength is greater than room capacity |
| Subject not mapped | Warning | Teacher is not listed as able to teach that subject |
| Data problems | Warning | Unknown faculty / room, or a day / time slot not in Settings (useful after importing a file) |

### Suggested fixes (one click for the admin)
- **Reassign faculty**: another teacher from the same department who is free at that time, under their weekly limit, and preferably mapped to the subject.
- **Change room**: a room that is actually free at that time, of the right type (lab / lecture hall) and big enough for the section. The smallest room that fits is chosen.
- **Move to another slot**: the first day and slot when the teacher, the section and the room are all free.

### Day-to-day use
- **Admin login.** Anyone can view; only the admin can change data. Passwords are stored hashed and every form is protected against cross-site request forgery (CSRF).
- **Manage faculty, rooms, sections and subjects** from the browser, including which teacher can teach which subject.
- **Add, edit and delete classes.** You are warned immediately if a change causes a clash.
- **Import** an existing timetable or faculty list from **Excel (.xlsx) or CSV**. Common column names ("Teacher", "Class", "Time" ...) and formats ("mon", "9:00-10:00") are understood. Bad rows are skipped and reported with their row number.
- **Export** the timetable (CSV) and a full report (Excel with Timetable, Conflicts, Workload and Suggestions sheets).
- **Leave & substitutes.** Mark a teacher on leave for a date. The app lists their classes that day with suggested substitutes, and you can print the day's arrangement for the notice board. The permanent timetable is not changed.
- **Printable timetables** for every faculty member, section and room (A4 landscape, lunch break shown, can be saved as PDF).
- **Reports & charts.** Summary numbers (busiest day, room usage %, overloaded faculty ...) and four matplotlib charts, each with a table view.
- **Settings.** College name, working days (Saturday optional), time slots, lunch break, daily and back-to-back limits, weekly caps and the underload threshold.
- **Backup.** The whole database can be downloaded as one file.
- **Demo timetables** for presentations: clean, clashes, and overload.

### Burnout-risk predictor (machine learning)
A logistic-regression model predicts whether a faculty member is **Underloaded, Balanced or Overloaded** from lecture, lab, admin and research hours, number of subjects and teaching days. The dashboard can fill the form from a teacher's real timetable.

---

## 3. How it works

```
 Browser (HTML/CSS/JS)
        │  pages + JSON API
        ▼
 app.py  (Flask routes, login, forms)
        │
        ├── core/database.py         SQLite: faculty, rooms, sections, subjects, timetable, leave, settings
        ├── core/conflict_detector.py  all checks + fix suggestions (pure Python, no database)
        ├── core/substitutes.py      substitute finder for leave days
        ├── core/file_io.py          Excel/CSV import & export (pandas, openpyxl)
        ├── core/reports.py          summary numbers & charts (pandas, matplotlib)
        └── model/workload_model.joblib   trained scikit-learn model
```

### Finding clashes
Every class is put into dictionaries keyed by `(faculty, day, slot)`, `(room, day, slot)` and `(section, day, slot)`. If any key holds more than one class, that is a hard clash. This takes one pass over the timetable, so it stays fast even for large departments.

### Back-to-back classes
For each teacher and day, the slot numbers are sorted and the longest run of neighbouring slots is counted. A run is broken by a free slot **or by the lunch break** (set in Settings).

### Workload Balance Index (WBI)
For every faculty member: `utilization = hours assigned ÷ own weekly cap`.
`WBI = 100 − (standard deviation of all utilizations × 100)`, kept between 0 and 100.
Using utilization (not raw hours) is fair across designations: a Professor at 14/14 and an Assistant Professor at 18/18 are equally loaded.

### Substitute choice
Candidates must be in the same department, free at that slot, not on leave that day, not already substituting at that time, and below their weekly cap. They are sorted by: mapped to the subject first, then lowest current load.

---

## 4. Installation

Needs **Python 3.10 or newer**.

```bash
git clone https://github.com/shaurya212121/PDL_lab_project.git
cd PDL_lab_project
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000**.

On first start the app creates `data/clashaudit.db` with sample faculty, rooms, sections, subjects and a clean demo timetable.

### First login
| Username | Password |
|---|---|
| `admin` | `admin123` |

A yellow banner reminds you to **change this password** (top right → *Change password*) before anyone else uses the system.

### Using it from other computers in the college
`app.py` listens on all network addresses. Find the IP address of the computer running it (`ipconfig` on Windows, `ip addr` on Linux) and open `http://<that-ip>:5000` from any computer on the same network. Allow Python through the firewall if Windows asks.

> The built-in Flask server is fine for a department-level tool on the college network. It should **not** be exposed to the public internet.

---

## 5. Setting it up for a real department

1. **Log in** and change the password.
2. **Settings:** enter the college name, working days, your actual time slots and the lunch break. Check the weekly caps.
3. **Rooms, Sections & Subjects:** add your rooms (type + seats), sections (with number of students) and subjects (mark labs).
4. **Faculty:** add faculty one by one or import a list. Click **Edit** on each one to tick the subjects they can teach.
5. **Timetable:** clear the demo timetable, then import your timetable file or add classes one by one.
6. **Dashboard:** fix every hard clash, review the warnings, and download the Excel report.
7. **Print:** print faculty, section and room timetables.
8. **Every day:** use **Leave & Substitutes** when someone is absent and print the arrangement.
9. **Backup:** download a backup from Settings regularly.

### Import file format
Timetable (CSV or Excel). The first row must be the column names:

| faculty_name | department | course_code | course_name | section | day | time_slot | room |
|---|---|---|---|---|---|---|---|
| Dr. Rajesh Sharma | CSE | CS301 | Operating Systems | CSE-A | Monday | 09:00 - 10:00 | LH-101 |

`department` and `course_name` are optional (taken from the faculty / subject lists). Sample files are in `dataset/samples/` and can also be downloaded from the app.

Faculty list: `name, department, designation` (+ optional `max_hours`). Designations such as "Asst. Prof", "Assoc Professor" and "HOD" are recognised.

---

## 6. Project structure

```
PDL_lab_project/
├── app.py                      Flask web app: pages, login, JSON API
├── demo_cli.py                 terminal demo; can also check your own CSV/Excel file
├── requirements.txt
├── core/
│   ├── conflict_detector.py    clash checks, workload, WBI, fix suggestions
│   ├── database.py             SQLite tables and helper functions, demo data
│   ├── file_io.py              Excel/CSV import and export
│   ├── reports.py              summary numbers and matplotlib charts
│   ├── scenarios.py            three demo timetables
│   └── substitutes.py          leave-day substitute finder
├── model/
│   ├── train.py                trains and compares 4 ML models
│   ├── workload_model.joblib   saved model (retrained automatically if incompatible)
│   └── model_metadata.json     accuracy figures shown in the app
├── dataset/
│   ├── faculty_workload.csv    400-faculty training dataset
│   ├── generate_dataset.py     script that generated the dataset
│   └── samples/                sample import files
├── templates/                  HTML pages (Jinja2)
├── static/css, static/js       styles and dashboard script
├── tests/                      unit tests (unittest)
└── data/                       created at runtime: database + secret key (not in Git)
```

### Database tables
`faculty`, `rooms`, `sections`, `subjects`, `faculty_subjects` (who can teach what), `timetable`, `leaves`, `substitutions`, `settings`, `users`.

---

## 7. Machine learning model

Dataset: 400 synthetic faculty records (`dataset/faculty_workload.csv`) across CSE, IT, AI-DS and ECE, labelled Underloaded / Balanced / Overloaded.
Features: designation, teaching hours, lab hours, admin hours, research hours, number of subjects, teaching days.
Preprocessing: `StandardScaler` for numbers, `OneHotEncoder` for designation, inside a scikit-learn `Pipeline`.
Evaluation: stratified 80/20 split plus 5-fold stratified cross-validation.

| Model | Test accuracy | Precision | Recall | F1 | 5-fold CV |
|---|---|---|---|---|---|
| **Logistic Regression (used)** | **96.25%** | **96.52%** | **96.25%** | **96.24%** | **95.50% ± 1.7** |
| Decision Tree | 93.75% | 94.04% | 93.75% | 93.76% | 90.00% ± 3.95 |
| Random Forest | 91.25% | 92.58% | 91.25% | 91.19% | 92.25% ± 3.1 |
| Gaussian Naive Bayes | 48.75% | 50.42% | 48.75% | 41.16% | 53.50% ± 2.15 |

Logistic Regression was chosen for the best accuracy, the most stable cross-validation score, and coefficients that are easy to interpret. Retrain with `python model/train.py`. If the saved model was made with a different scikit-learn version, the app retrains it automatically on start-up.

The dataset is synthetic, so the predictor is a guide, not a measurement. The timetable checks do not depend on it.

---

## 8. Testing

```bash
python -m unittest discover tests -v
```

33 tests cover every conflict rule (including the lunch-break case), the fix suggestions, the balance index, the three demo scenarios, file import (column aliases, a single "Subject" column, bad rows, wrong file types), login, CSRF protection, applying fixes, delete protection and the leave page. Tests use a temporary database and never touch `data/`.

Terminal demo:
```bash
python demo_cli.py                                   # demo timetable with clashes
python demo_cli.py dataset/samples/timetable_sample.csv   # check any CSV/Excel timetable
```

---

## 9. Data, security and backup

- All data lives in **one file**: `data/clashaudit.db`. Download a backup from **Settings**. To restore, stop the app and put the backup file back in `data/`.
- `data/` is in `.gitignore`, so the college's real data and the secret key are never uploaded to GitHub.
- Passwords are hashed with Werkzeug. Every form carries a CSRF token. Uploads are limited to 5 MB.
- Faculty, rooms, sections and subjects that are still used in the timetable cannot be deleted by accident.

---

## 10. Limitations & future scope

- Every slot counts as one hour. Two-hour labs are entered as two consecutive slots.
- One admin account. Separate HOD / faculty logins could be added.
- The timetable is checked and repaired, not generated from scratch. An automatic timetable generator would be a natural next step.
- Email or SMS alerts to substitutes.
- Semester-wise history so workload can be compared across terms.

---

## API (used by the dashboard)

| Method | URL | Purpose |
|---|---|---|
| GET | `/api/report` | Current timetable + full analysis |
| POST | `/api/analyze` | Analyse a timetable sent as JSON (nothing is saved) |
| POST | `/api/resolve` | Apply one suggested fix (admin) |
| POST | `/api/predict-stress` | Burnout-risk prediction |
| GET | `/api/model-info` | Model metrics |
| GET | `/api/scenarios` | Demo timetables |
| GET | `/api/health` | Health check |

---

*Created for the Python Data Lab (PDL) mini project.*
