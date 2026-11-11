/**
 * ClashAudit - dashboard page script.
 * Loads the analysis from the server (/api/report) and shows it.
 */

let currentReport = null;
let currentSchedule = [];
const CSRF = document.querySelector('meta[name="csrf-token"]').content;

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => openTab(btn.dataset.tab));
  });
  document.getElementById('stressForm').addEventListener('submit', handleStressPrediction);
  document.getElementById('btnSampleOverload').addEventListener('click', loadOverloadExample);
  document.getElementById('calcFaculty').addEventListener('change', fillFromFaculty);
  loadReport();
  handleStressPrediction();
});

/** Make text safe to put inside HTML (names typed by users could contain < or >). */
function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
  ));
}

function openTab(tabId) {
  document.querySelectorAll('.tab-content').forEach(el => el.classList.toggle('active', el.id === tabId));
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.toggle('active', el.dataset.tab === tabId));
}

async function loadReport() {
  try {
    const res = await fetch('/api/report');
    const data = await res.json();
    currentSchedule = data.schedule;
    renderReport(data.report);
  } catch (err) {
    document.getElementById('conflictsContainer').innerHTML =
      '<div class="flash error">Could not reach the server. Is <code>python app.py</code> running?</div>';
  }
}

function renderReport(report) {
  currentReport = report;
  document.getElementById('statTotalSlots').innerText = currentSchedule.length;
  document.getElementById('statCriticalConflicts').innerText = report.critical_conflicts;
  document.getElementById('statWarningConflicts').innerText = report.warning_conflicts;
  document.getElementById('statBalanceScore').innerText = `${report.workload_balance_score}%`;
  renderConflicts(report);
  renderWorkload(report.workload_distribution);
  fillFacultyDropdown(report.workload_distribution);
}

/** One card per problem, with its suggested fix underneath (if there is one). */
function renderConflicts(report) {
  const container = document.getElementById('conflictsContainer');
  if (report.conflicts_list.length === 0) {
    container.innerHTML = `
      <div class="flash success">✅ <strong>No conflicts.</strong>
        No double-bookings, section clashes, overloads or room problems found.</div>`;
    return;
  }

  // Critical first, then warnings
  const sorted = [...report.conflicts_list].sort((a, b) =>
    (a.severity === 'CRITICAL' ? 0 : 1) - (b.severity === 'CRITICAL' ? 0 : 1));

  container.innerHTML = sorted.map(c => {
    const fixes = report.suggestions.filter(s => s.conflict_id === c.id);
    const fixHtml = fixes.map(s => `
      <div class="fix-box">
        <span>💡 ${esc(s.reason)}</span>
        ${IS_ADMIN ? `<button class="btn btn-resolve btn-sm" data-conflict="${esc(s.conflict_id)}"
                       data-entry="${esc(s.entry_id)}">Apply fix</button>` : ''}
      </div>`).join('');
    const badgeColor = c.severity === 'CRITICAL' ? 'red' : 'amber';
    return `
      <div class="conflict-card ${c.severity}">
        <div class="conflict-left">
          <div class="conflict-title-row">
            <span class="tag-badge ${badgeColor}">${esc(c.badge)}</span>
            <h4>${esc(c.title)}</h4>
          </div>
          <p class="conflict-desc">${esc(c.description)}</p>
          <div class="conflict-meta">
            <span>📅 <strong>${esc(c.day)}</strong></span>
            <span>⏰ <strong>${esc(c.time_slot)}</strong></span>
          </div>
          ${fixHtml}
        </div>
      </div>`;
  }).join('');

  container.querySelectorAll('button[data-conflict]').forEach(btn => {
    btn.addEventListener('click', () => applyFix(btn.dataset.conflict, Number(btn.dataset.entry), btn));
  });
}

async function applyFix(conflictId, entryId, button) {
  button.disabled = true;
  button.innerText = 'Applying…';
  try {
    const res = await fetch('/api/resolve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': CSRF },
      body: JSON.stringify({ conflict_id: conflictId, entry_id: entryId })
    });
    const data = await res.json();
    if (!res.ok) {
      alert(data.error || 'Could not apply the fix.');
      loadReport();
      return;
    }
    currentSchedule = data.schedule;
    renderReport(data.report);
  } catch (err) {
    alert('Could not reach the server.');
    button.disabled = false;
    button.innerText = 'Apply fix';
  }
}

function renderWorkload(list) {
  const colors = { Overloaded: 'red', Underloaded: 'amber', Balanced: 'green', Unassigned: 'grey' };
  document.getElementById('workloadList').innerHTML = list.map(f => `
    <div class="workload-item">
      <div class="workload-info">
        <h4><a href="/print/faculty/${encodeURIComponent(f.faculty_name)}">${esc(f.faculty_name)}</a></h4>
        <p>${esc(f.designation)} &bull; ${esc(f.department)}</p>
      </div>
      <div class="bar-container">
        <div class="bar-labels">
          <span>${f.utilization_percentage}% of limit</span>
          <span>${f.assigned_hours} / ${f.max_hours} hrs</span>
        </div>
        <div class="bar-track"><div class="bar-fill ${colors[f.status]}" style="width:${Math.min(f.utilization_percentage, 100)}%"></div></div>
      </div>
      <div class="workload-status"><span class="tag-badge ${colors[f.status]}">${esc(f.status)}</span></div>
    </div>`).join('') || '<p class="muted">No faculty added yet.</p>';
}

/* ---------------- Burnout predictor ---------------- */

function fillFacultyDropdown(list) {
  const select = document.getElementById('calcFaculty');
  const chosen = select.value;
  select.innerHTML = '<option value="">-- choose --</option>' +
    list.map(f => `<option value="${esc(f.faculty_name)}">${esc(f.faculty_name)}</option>`).join('');
  select.value = chosen;
}

/** Count a teacher's lecture hours, lab hours, subjects and days from the timetable. */
function fillFromFaculty() {
  const name = document.getElementById('calcFaculty').value;
  if (!name) return;
  const info = currentReport.workload_distribution.find(f => f.faculty_name === name);
  const own = currentSchedule.filter(e => e.faculty_name === name);
  const labs = own.filter(e => (e.course_name || '').toLowerCase().includes('lab')).length;
  if (['Professor', 'Associate Professor', 'Assistant Professor'].includes(info.designation)) {
    document.getElementById('calcDesig').value = info.designation;
  }
  document.getElementById('calcTeaching').value = own.length - labs;
  document.getElementById('calcLab').value = labs;
  document.getElementById('calcCourses').value = Math.max(1, new Set(own.map(e => e.course_code)).size);
  document.getElementById('calcDays').value = Math.max(1, new Set(own.map(e => e.day)).size);
  handleStressPrediction();
}

function loadOverloadExample() {
  document.getElementById('calcFaculty').value = '';
  document.getElementById('calcDesig').value = 'Assistant Professor';
  document.getElementById('calcTeaching').value = 16;
  document.getElementById('calcLab').value = 8;
  document.getElementById('calcAdmin').value = 3;
  document.getElementById('calcResearch').value = 2;
  document.getElementById('calcCourses').value = 3;
  document.getElementById('calcDays').value = 5;
  handleStressPrediction();
}

async function handleStressPrediction(event) {
  if (event) event.preventDefault();
  const num = id => parseFloat(document.getElementById(id).value) || 0;
  const payload = {
    Designation: document.getElementById('calcDesig').value,
    TeachingHours: num('calcTeaching'),
    LabHours: num('calcLab'),
    AdminHours: num('calcAdmin'),
    ResearchHours: num('calcResearch'),
    UniqueCourses: num('calcCourses') || 1,
    DaysTaught: num('calcDays') || 1
  };
  try {
    const res = await fetch('/api/predict-stress', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': CSRF },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok) {
      document.getElementById('stressRecommendation').innerText = data.error || 'Prediction failed.';
      return;
    }
    renderStressResult(data);
  } catch (err) {
    document.getElementById('stressRecommendation').innerText = 'Could not reach the server.';
  }
}

function renderStressResult(data) {
  const badge = document.getElementById('stressBadge');
  const looks = {
    2: ['red', '⚠️ HIGH BURNOUT RISK (OVERLOADED)'],
    0: ['amber', '⚡ UNDERLOADED / SPARE CAPACITY'],
    1: ['green', '✅ BALANCED WORKLOAD']
  }[data.prediction_code];
  badge.className = `stress-badge tag-badge ${looks[0]}`;
  badge.innerText = looks[1];

  document.getElementById('stressHoursInfo').innerHTML =
    `Total: <strong>${data.total_hours} hrs/week</strong> | Limit: <strong>${data.max_allowed_hours} hrs</strong> (${data.utilization_ratio}%)`;

  const p = data.probabilities;
  [['probUnderload', p.Underloaded], ['probBalanced', p.Balanced], ['probOverload', p.Overloaded]]
    .forEach(([id, value]) => {
      document.getElementById(id).style.width = `${value}%`;
      document.getElementById(id + 'Val').innerText = `${value}%`;
    });
  document.getElementById('stressRecommendation').innerText = data.recommendation;
}
