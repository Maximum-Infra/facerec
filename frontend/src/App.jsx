import React, { useCallback, useEffect, useState } from 'react'
import {
  Activity,
  Camera,
  CheckCircle2,
  CircleUserRound,
  ClipboardCheck,
  Download,
  Database,
  FlaskConical,
  History,
  LoaderCircle,
  Play,
  Plus,
  RefreshCw,
  Save,
  ScanFace,
  ShieldCheck,
  ShieldOff,
  Square,
  Target,
  Trash2,
  UserRoundCheck,
  Users,
  WifiOff,
  X,
} from 'lucide-react'

const api = async (path, options = {}) => {
  const response = await fetch(path, {
    ...options,
    headers: { 'Content-Type': 'application/json', 'X-Operator': 'local-dashboard', ...(options.headers || {}) },
  })
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      const body = await response.json()
      message = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {}
    throw new Error(message)
  }
  if (response.status === 204) return null
  return response.json()
}

const timeLabel = (value) => {
  if (!value) return '—'
  return new Intl.DateTimeFormat(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
  }).format(new Date(value))
}

function StatusPill({ ok, children }) {
  return <span className={`status-pill ${ok ? 'ok' : 'bad'}`}><span />{children}</span>
}

function App() {
  const [employees, setEmployees] = useState([])
  const [events, setEvents] = useState([])
  const [worker, setWorker] = useState(null)
  const [config, setConfig] = useState(null)
  const [stats, setStats] = useState({ employees: 0, enrolled: 0, events: 0 })
  const [enrollment, setEnrollment] = useState({ active: false, captured: 0, required: 15 })
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [streamKey, setStreamKey] = useState(Date.now())
  const [calibration, setCalibration] = useState(null)
  const [calibrationName, setCalibrationName] = useState('Entrance calibration')
  const [attemptType, setAttemptType] = useState('genuine')
  const [expectedEmployeeId, setExpectedEmployeeId] = useState('')
  const [subjectLabel, setSubjectLabel] = useState('')
  const [pose, setPose] = useState('front')
  const [distance, setDistance] = useState('normal')
  const [antiSpoof, setAntiSpoof] = useState({ active: false })
  const [antiSpoofTests, setAntiSpoofTests] = useState([])
  const [antiSpoofReport, setAntiSpoofReport] = useState(null)
  const [antiSpoofType, setAntiSpoofType] = useState('live')
  const [antiSpoofEmployeeId, setAntiSpoofEmployeeId] = useState('')
  const [antiSpoofLabel, setAntiSpoofLabel] = useState('')
  const [retention, setRetention] = useState(null)
  const [retentionForm, setRetentionForm] = useState(null)
  const [auditLog, setAuditLog] = useState([])
  const [retentionResult, setRetentionResult] = useState(null)

  const loadSlow = useCallback(async () => {
    try {
      const [employeeData, eventData, configData, statsData, sessionData, spoofTests, spoofReport, retentionData, auditData] = await Promise.all([
        api('/api/employees'), api('/api/events?limit=50'), api('/api/config'), api('/api/stats'),
        api('/api/calibration/sessions?limit=1'), api('/api/anti-spoof/tests?limit=50'),
        api('/api/anti-spoof/report'), api('/api/admin/retention'), api('/api/admin/audit?limit=50'),
      ])
      setEmployees(employeeData)
      setEvents(eventData)
      setConfig(configData)
      setStats(statsData)
      setAntiSpoofTests(spoofTests)
      setAntiSpoofReport(spoofReport)
      setRetention(retentionData)
      setRetentionForm(current => current || {
        enabled: retentionData.enabled,
        recognition_event_days: retentionData.recognition_event_days,
        calibration_days: retentionData.calibration_days,
        anti_spoof_days: retentionData.anti_spoof_days,
      })
      setAuditLog(auditData)
      const latestSession = sessionData[0]
      setCalibration(latestSession ? await api(`/api/calibration/sessions/${latestSession.id}`) : null)
      const availableEmployees = employeeData.filter(employee => employee.active && employee.template_count)
      setExpectedEmployeeId(current => (
        availableEmployees.some(employee => String(employee.id) === current)
          ? current
          : (availableEmployees[0] ? String(availableEmployees[0].id) : '')
      ))
      setAntiSpoofEmployeeId(current => (
        availableEmployees.some(employee => String(employee.id) === current)
          ? current
          : (availableEmployees[0] ? String(availableEmployees[0].id) : '')
      ))
      setError('')
    } catch (err) {
      setError(err.message)
    }
  }, [])

  const loadFast = useCallback(async () => {
    try {
      const [workerData, enrollmentData, antiSpoofData] = await Promise.all([
        api('/api/worker/status'), api('/api/enrollment/status'), api('/api/anti-spoof/status'),
      ])
      setWorker(workerData)
      setEnrollment(enrollmentData)
      setAntiSpoof(antiSpoofData)
      if (!enrollmentData.active && enrollment.active) loadSlow()
      if (!antiSpoofData.active && antiSpoof.active) loadSlow()
    } catch (err) {
      setWorker(null)
      setError(err.message)
    }
  }, [antiSpoof.active, enrollment.active, loadSlow])

  useEffect(() => { loadSlow(); loadFast() }, [])
  useEffect(() => {
    const fastTimer = setInterval(loadFast, 1500)
    const slowTimer = setInterval(loadSlow, 6000)
    return () => { clearInterval(fastTimer); clearInterval(slowTimer) }
  }, [loadFast, loadSlow])

  const addEmployee = async (event) => {
    event.preventDefault()
    if (!name.trim()) return
    setBusy(true)
    try {
      await api('/api/employees', { method: 'POST', body: JSON.stringify({ name: name.trim() }) })
      setName('')
      await loadSlow()
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  const enroll = async (employee) => {
    setBusy(true)
    try {
      const result = await api(`/api/employees/${employee.id}/enroll`, { method: 'POST' })
      setEnrollment(result)
      setError('')
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  const cancelEnrollment = async () => {
    try { setEnrollment(await api('/api/enrollment/cancel', { method: 'POST' })) }
    catch (err) { setError(err.message) }
  }

  const toggleEmployee = async (employee) => {
    try {
      await api(`/api/employees/${employee.id}`, {
        method: 'PATCH', body: JSON.stringify({ active: !employee.active }),
      })
      await loadSlow()
    } catch (err) { setError(err.message) }
  }

  const removeEmployee = async (employee) => {
    if (!window.confirm(`Delete ${employee.name} and all face templates?`)) return
    try {
      await api(`/api/employees/${employee.id}`, { method: 'DELETE' })
      await loadSlow()
    } catch (err) { setError(err.message) }
  }

  const startCalibration = async (event) => {
    event.preventDefault()
    if (calibrationName.trim().length < 2) return
    setBusy(true)
    try {
      await api('/api/calibration/sessions', {
        method: 'POST', body: JSON.stringify({ name: calibrationName.trim() }),
      })
      await loadSlow()
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  const armAttempt = async (event) => {
    event.preventDefault()
    if (!calibration || calibration.status !== 'active') return
    if (attemptType === 'genuine' && !expectedEmployeeId) return
    setBusy(true)
    try {
      await api(`/api/calibration/sessions/${calibration.id}/attempts`, {
        method: 'POST',
        body: JSON.stringify({
          expected_type: attemptType,
          expected_employee_id: attemptType === 'genuine' ? Number(expectedEmployeeId) : null,
          subject_label: attemptType === 'impostor' ? (subjectLabel.trim() || 'Unknown participant') : null,
          pose,
          distance,
        }),
      })
      await loadSlow()
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  const cancelAttempt = async () => {
    const armed = calibration?.armed_attempt
    if (!armed) return
    try {
      await api(`/api/calibration/attempts/${armed.id}/cancel`, { method: 'POST' })
      await loadSlow()
    } catch (err) { setError(err.message) }
  }

  const recordNoDecision = async () => {
    const armed = calibration?.armed_attempt
    if (!armed) return
    try {
      await api(`/api/calibration/attempts/${armed.id}/no-decision`, { method: 'POST' })
      await loadSlow()
    } catch (err) { setError(err.message) }
  }

  const completeCalibration = async () => {
    if (!calibration || !window.confirm('Complete this calibration session?')) return
    try {
      await api(`/api/calibration/sessions/${calibration.id}/complete`, { method: 'POST' })
      await loadSlow()
    } catch (err) { setError(err.message) }
  }

  const startAntiSpoof = async (event) => {
    event.preventDefault()
    if (antiSpoofType === 'live' && !antiSpoofEmployeeId) return
    setBusy(true)
    try {
      await api('/api/anti-spoof/tests', {
        method: 'POST',
        body: JSON.stringify({
          test_type: antiSpoofType,
          expected_employee_id: antiSpoofType === 'live' ? Number(antiSpoofEmployeeId) : null,
          subject_label: antiSpoofType === 'live' ? null : (antiSpoofLabel.trim() || antiSpoofType.replaceAll('_', ' ')),
        }),
      })
      setError('')
      await loadFast()
      await loadSlow()
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  const cancelAntiSpoof = async () => {
    try {
      await api('/api/anti-spoof/cancel', { method: 'POST' })
      setAntiSpoof({ active: false })
      await loadSlow()
    } catch (err) { setError(err.message) }
  }

  const clearCalibrationEvidence = async () => {
    if (!window.confirm('Permanently clear all calibration sessions and attempts? Employees and templates will not be affected.')) return
    setBusy(true)
    try {
      await api('/api/calibration/sessions', { method: 'DELETE' })
      setCalibration(null)
      await loadSlow()
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  const clearAntiSpoofEvidence = async () => {
    if (!window.confirm('Permanently clear all RGB presentation-attack test evidence? Employees and templates will not be affected.')) return
    setBusy(true)
    try {
      await api('/api/anti-spoof/tests', { method: 'DELETE' })
      setAntiSpoofTests([])
      await loadSlow()
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  const clearRecognitionEvents = async () => {
    if (!window.confirm('Permanently clear all recognition events? Employees, templates and copied calibration results will not be affected.')) return
    setBusy(true)
    try {
      await api('/api/events', { method: 'DELETE' })
      setEvents([])
      await loadSlow()
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  const saveRetention = async (event) => {
    event.preventDefault()
    setBusy(true)
    try {
      const saved = await api('/api/admin/retention', {
        method: 'PUT',
        body: JSON.stringify({
          ...retentionForm,
          recognition_event_days: Number(retentionForm.recognition_event_days),
          calibration_days: Number(retentionForm.calibration_days),
          anti_spoof_days: Number(retentionForm.anti_spoof_days),
        }),
      })
      setRetention(saved)
      setRetentionForm({
        enabled: saved.enabled,
        recognition_event_days: saved.recognition_event_days,
        calibration_days: saved.calibration_days,
        anti_spoof_days: saved.anti_spoof_days,
      })
      setRetentionResult(null)
      await loadSlow()
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  const runRetentionNow = async () => {
    if (!window.confirm('Run retention cleanup now using the saved age limits? Active work, employees and templates will not be removed.')) return
    setBusy(true)
    try {
      const result = await api('/api/admin/retention/run', { method: 'POST' })
      setRetentionResult(result)
      await loadSlow()
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  const progress = enrollment.required ? (enrollment.captured / enrollment.required) * 100 : 0
  const systemReady = worker?.camera_connected && worker?.model_ready

  return (
    <div className="app-shell">
      <header>
        <div className="brand-mark"><ScanFace size={25} /></div>
        <div className="brand-copy"><h1>FaceRec</h1><p>Entrance recognition lab</p></div>
        <div className="header-status">
          <span className="lab-chip"><FlaskConical size={14} /> LAB MODE</span>
          <StatusPill ok={worker?.camera_connected}>{worker?.camera_connected ? 'Camera online' : 'Camera offline'}</StatusPill>
          <StatusPill ok={worker?.model_ready}>{worker?.model_ready ? 'Models ready' : 'Models unavailable'}</StatusPill>
          <button className="icon-button" title="Refresh" onClick={() => { loadSlow(); loadFast(); setStreamKey(Date.now()) }}><RefreshCw size={17} /></button>
        </div>
      </header>

      <main>
        <section className="notice"><ShieldOff size={18} /><div><strong>Shadow mode only</strong><span>No door controller is connected. FaceRec records lab decisions and never stores continuous video.</span></div></section>
        {error && <section className="error-banner"><WifiOff size={18} /><span>{error}</span><button onClick={() => setError('')}><X size={16} /></button></section>}

        <section className="kpi-grid">
          <article><Users /><div><span>Employees</span><strong>{stats.employees}</strong></div></article>
          <article><UserRoundCheck /><div><span>Enrolled</span><strong>{stats.enrolled}</strong></div></article>
          <article><Activity /><div><span>Processed FPS</span><strong>{worker?.processed_fps ?? '—'}</strong></div></article>
          <article><History /><div><span>Lab events</span><strong>{stats.events}</strong></div></article>
        </section>

        <section className="primary-grid">
          <article className="panel scanner-panel">
            <div className="panel-heading"><div><Camera size={19} /><span>Live scanner</span></div><small>Minrray · 1920×1080 · 15 FPS source</small></div>
            <div className="video-stage">
              <img key={streamKey} src={`/stream/live.mjpg?v=${streamKey}`} alt="Live FaceRec camera with recognition overlay" />
              {!systemReady && <div className="video-placeholder"><LoaderCircle className="spin" /><strong>Waiting for video</strong><span>{worker?.error || worker?.message || 'Connecting to recognition worker'}</span></div>}
              <div className="video-footer"><span className={`live-dot ${systemReady ? '' : 'offline'}`} />{worker?.message || 'Starting FaceRec'}</div>
            </div>

            {enrollment.active && <div className="enrollment-card">
              <div className="enrollment-top"><div><CircleUserRound /><span><strong>Enrolling {enrollment.employee_name}</strong><small>{enrollment.message || 'Follow the guidance over the video'}</small></span></div><button onClick={cancelEnrollment}>Cancel</button></div>
              <div className="progress-track"><span style={{ width: `${progress}%` }} /></div>
              <div className="progress-copy"><span>{enrollment.captured} captured</span><span>{enrollment.required} required</span></div>
            </div>}

            <div className="scanner-meta">
              <div><span>Templates loaded</span><strong>{worker?.template_count ?? 0}</strong></div>
              <div><span>Match threshold</span><strong>{config?.match_threshold ?? '—'}</strong></div>
              <div><span>Last frame</span><strong>{worker?.last_frame_at ? timeLabel(worker.last_frame_at) : '—'}</strong></div>
            </div>
          </article>

          <article className="panel people-panel">
            <div className="panel-heading"><div><Users size={19} /><span>Employees</span></div><small>{employees.length} lab users</small></div>
            <form className="add-form" onSubmit={addEmployee}>
              <input value={name} onChange={event => setName(event.target.value)} placeholder="Employee name" maxLength={120} />
              <button disabled={busy || name.trim().length < 2}><Plus size={17} /> Add</button>
            </form>
            <div className="people-list">
              {employees.length === 0 && <div className="empty-state"><CircleUserRound /><strong>No employees yet</strong><span>Add the first volunteer, then start enrollment.</span></div>}
              {employees.map(employee => <div className={`person-row ${employee.active ? '' : 'disabled'}`} key={employee.id}>
                <div className="avatar">{employee.name.slice(0, 2).toUpperCase()}</div>
                <div className="person-copy"><strong>{employee.name}</strong><span>{employee.template_count ? `${employee.template_count} face templates` : 'Not enrolled'}</span></div>
                <button className="enroll-button" disabled={busy || enrollment.active || antiSpoof.active || !employee.active} onClick={() => enroll(employee)}>{employee.template_count ? 'Re-enroll' : 'Enroll'}</button>
                <button className={`toggle ${employee.active ? 'on' : ''}`} title={employee.active ? 'Disable' : 'Enable'} onClick={() => toggleEmployee(employee)}><span /></button>
                <button className="trash" title="Delete employee" onClick={() => removeEmployee(employee)}><Trash2 size={16} /></button>
              </div>)}
            </div>
          </article>
        </section>

        <section className="panel calibration-panel">
          <div className="panel-heading">
            <div><ClipboardCheck size={19} /><span>Calibration evidence</span></div>
            <span className="panel-heading-actions"><small>Phase 2 · numerical evidence only · no face images</small><button className="clear-button" onClick={clearCalibrationEvidence} disabled={busy || !calibration || calibration.status === 'active'}><Trash2 size={13} /> Clear</button></span>
          </div>

          {!calibration || calibration.status === 'completed' ? <div className="calibration-start">
            <div>
              <strong>Start a structured entrance test</strong>
              <span>Arm one labeled attempt, let the person enter, then leave until the scanner shows No face.</span>
            </div>
            <form onSubmit={startCalibration}>
              <input value={calibrationName} onChange={event => setCalibrationName(event.target.value)} maxLength={160} />
              <button disabled={busy || calibrationName.trim().length < 2}><Play size={15} /> Start session</button>
            </form>
          </div> : null}

          {calibration?.status === 'active' && <>
            <div className="calibration-summary">
              <div><span>Session</span><strong>{calibration.name}</strong></div>
              <div><span>Captured</span><strong>{calibration.captured_count}</strong></div>
              <div><span>Threshold</span><strong>{calibration.match_threshold}</strong></div>
              <div><span>Minimum face</span><strong>{calibration.min_face_width}px</strong></div>
              <a href={`/api/calibration/sessions/${calibration.id}/attempts.csv`}><Download size={15} /> CSV</a>
              <button className="complete-button" onClick={completeCalibration} disabled={Boolean(calibration.armed_attempt)}><Square size={14} /> Complete</button>
            </div>

            {calibration.armed_attempt ? <div className="armed-attempt">
              <Target size={20} />
              <div><strong>Attempt armed — send the subject into view</strong><span>{calibration.armed_attempt.expected_type === 'genuine' ? calibration.armed_attempt.expected_employee_name : calibration.armed_attempt.subject_label} · {calibration.armed_attempt.pose} · {calibration.armed_attempt.distance}</span></div>
              <div className="armed-actions"><button className="no-decision" onClick={recordNoDecision}>Record no decision</button><button onClick={cancelAttempt}>Cancel</button></div>
            </div> : <form className="attempt-form" onSubmit={armAttempt}>
              <label><span>Attempt type</span><select value={attemptType} onChange={event => setAttemptType(event.target.value)}><option value="genuine">Enrolled employee</option><option value="impostor">Unknown / disabled</option></select></label>
              {attemptType === 'genuine' ? <label><span>Expected identity</span><select value={expectedEmployeeId} onChange={event => setExpectedEmployeeId(event.target.value)}>{employees.filter(employee => employee.active && employee.template_count).map(employee => <option key={employee.id} value={employee.id}>{employee.name}</option>)}</select></label>
                : <label><span>Subject label</span><input value={subjectLabel} onChange={event => setSubjectLabel(event.target.value)} placeholder="Example: Volunteer B disabled" maxLength={120} /></label>}
              <label><span>Pose</span><select value={pose} onChange={event => setPose(event.target.value)}><option value="front">Front</option><option value="left">Slight left</option><option value="right">Slight right</option></select></label>
              <label><span>Distance</span><select value={distance} onChange={event => setDistance(event.target.value)}><option value="near">Near</option><option value="normal">Normal entrance</option><option value="far">Far</option></select></label>
              <button disabled={busy}><Target size={15} /> Arm next attempt</button>
            </form>}

            <div className="calibration-report">
              <article><span>Genuine</span><strong>{calibration.report.attempts.genuine}</strong></article>
              <article><span>Impostor</span><strong>{calibration.report.attempts.impostor}</strong></article>
              <article><span>False reject rate</span><strong>{calibration.report.outcomes.false_reject_rate == null ? 'Pending' : `${(calibration.report.outcomes.false_reject_rate * 100).toFixed(1)}%`}</strong></article>
              <article><span>False accept rate</span><strong>{calibration.report.outcomes.false_accept_rate == null ? 'Pending' : `${(calibration.report.outcomes.false_accept_rate * 100).toFixed(1)}%`}</strong></article>
            </div>
            <div className={`threshold-recommendation ${calibration.report.recommendation.ready ? 'ready' : ''}`}>
              <Target size={16} /><div><strong>{calibration.report.recommendation.ready ? `Suggested threshold: ${calibration.report.recommendation.threshold}` : 'Threshold recommendation pending'}</strong><span>{calibration.report.recommendation.reason} No value is applied automatically.</span></div>
            </div>
          </>}

          {calibration?.attempts?.length > 0 && <div className="table-wrap calibration-table"><table><thead><tr><th>Time</th><th>Expected</th><th>Pose / distance</th><th>Observed</th><th>Score</th><th>Margin</th><th>Result</th></tr></thead><tbody>
            {calibration.attempts.slice(0, 20).map(attempt => <tr key={attempt.id}>
              <td>{timeLabel(attempt.captured_at || attempt.armed_at)}</td>
              <td>{attempt.expected_type === 'genuine' ? attempt.expected_employee_name : attempt.subject_label}</td>
              <td>{attempt.pose} / {attempt.distance}</td>
              <td>{attempt.status === 'captured' ? (attempt.observed_employee_name || 'Unknown') : attempt.status}</td>
              <td className="mono">{attempt.similarity == null ? '—' : attempt.similarity.toFixed(4)}</td>
              <td className="mono">{attempt.score_margin == null ? '—' : attempt.score_margin.toFixed(4)}</td>
              <td><span className={`result-chip ${attempt.result || attempt.status}`}>{(attempt.result || attempt.status).replaceAll('_', ' ')}</span></td>
            </tr>)}
          </tbody></table></div>}

          {calibration?.status === 'completed' && <div className="completed-report">
            <div><CheckCircle2 /><span><strong>{calibration.name} completed</strong><small>{calibration.report.attempts.total} captured attempts</small></span></div>
            <div className="report-copy"><span>Genuine: {calibration.report.attempts.genuine}</span><span>Impostor: {calibration.report.attempts.impostor}</span><span>FRR: {calibration.report.outcomes.false_reject_rate == null ? 'Pending' : `${(calibration.report.outcomes.false_reject_rate * 100).toFixed(1)}%`}</span><span>FAR: {calibration.report.outcomes.false_accept_rate == null ? 'Pending' : `${(calibration.report.outcomes.false_accept_rate * 100).toFixed(1)}%`}</span></div>
            <a href={`/api/calibration/sessions/${calibration.id}/attempts.csv`}><Download size={15} /> Export CSV</a>
          </div>}
          {calibration?.status === 'completed' && <div className={`threshold-recommendation ${calibration.report.recommendation.ready ? 'ready' : ''}`}><Target size={16} /><div><strong>{calibration.report.recommendation.ready ? `Suggested threshold: ${calibration.report.recommendation.threshold}` : 'Threshold recommendation pending'}</strong><span>{calibration.report.recommendation.reason} No value is applied automatically.</span></div></div>}
        </section>

        <section className="panel anti-spoof-panel">
          <div className="panel-heading">
            <div><ShieldCheck size={19} /><span>RGB presentation-attack lab</span></div>
            <span className="panel-heading-actions"><small>Phase 3 · experimental challenge · no images stored</small><button className="clear-button" onClick={clearAntiSpoofEvidence} disabled={busy || antiSpoof.active || antiSpoofTests.length === 0}><Trash2 size={13} /> Clear</button></span>
          </div>

          <div className="spoof-warning">
            <ShieldOff size={17} />
            <span>This motion challenge is evidence only, not production-grade liveness. A pass never unlocks a door.</span>
          </div>

          {antiSpoof.active ? <div className="challenge-active">
            <div className="challenge-copy">
              <span className="challenge-kicker">Active {antiSpoof.test_type.replaceAll('_', ' ')} test · {antiSpoof.subject_label}</span>
              <strong>{antiSpoof.prompt}</strong>
              <small>Hold each movement for {antiSpoof.required_confirmations} processed frames. Keep the same face visible.</small>
            </div>
            <div className="challenge-sequence">
              {antiSpoof.sequence.map((step, index) => <span key={`${step}-${index}`} className={index < antiSpoof.current_step_index ? 'done' : (index === antiSpoof.current_step_index ? 'current' : '')}>{step.replaceAll('_', ' ')}</span>)}
            </div>
            <div className="challenge-actions"><span>{antiSpoof.elapsed_seconds}s</span><button onClick={cancelAntiSpoof}>Cancel test</button></div>
          </div> : <form className="spoof-form" onSubmit={startAntiSpoof}>
            <label><span>Evidence type</span><select value={antiSpoofType} onChange={event => setAntiSpoofType(event.target.value)}><option value="live">Live person</option><option value="print">Printed photo</option><option value="phone_photo">Phone photo</option><option value="phone_video">Phone video</option></select></label>
            {antiSpoofType === 'live' ? <label><span>Expected identity</span><select value={antiSpoofEmployeeId} onChange={event => setAntiSpoofEmployeeId(event.target.value)}>{employees.filter(employee => employee.active && employee.template_count).map(employee => <option key={employee.id} value={employee.id}>{employee.name}</option>)}</select></label>
              : <label><span>Evidence label</span><input value={antiSpoofLabel} onChange={event => setAntiSpoofLabel(event.target.value)} placeholder="Example: Max printed photo" maxLength={120} /></label>}
            <div className="spoof-form-copy"><strong>Randomized movement sequence</strong><span>Start with no face visible, then present the selected subject or attack medium.</span></div>
            <button disabled={busy || enrollment.active || !systemReady}><Play size={15} /> Start challenge</button>
          </form>}

          <div className="spoof-report">
            <article><span>Completed tests</span><strong>{antiSpoofReport?.tests.completed ?? 0}</strong></article>
            <article><span>Live accept rate</span><strong>{antiSpoofReport?.outcomes.live_accept_rate == null ? 'Pending' : `${(antiSpoofReport.outcomes.live_accept_rate * 100).toFixed(1)}%`}</strong></article>
            <article><span>Attack detection</span><strong>{antiSpoofReport?.outcomes.attack_detection_rate == null ? 'Pending' : `${(antiSpoofReport.outcomes.attack_detection_rate * 100).toFixed(1)}%`}</strong></article>
            <article><span>Missed attacks</span><strong>{antiSpoofReport?.outcomes.missed_attack ?? 0}</strong></article>
            <a href="/api/anti-spoof/tests.csv"><Download size={15} /> CSV</a>
          </div>

          <div className="table-wrap spoof-table"><table><thead><tr><th>Time</th><th>Type</th><th>Subject</th><th>Outcome</th><th>Evaluation</th><th>Duration</th><th>Reason</th></tr></thead><tbody>
            {antiSpoofTests.length === 0 && <tr><td colSpan="7"><div className="table-empty">Run a live baseline and each presentation-attack type.</div></td></tr>}
            {antiSpoofTests.map(test => <tr key={test.id}>
              <td>{timeLabel(test.completed_at || test.started_at)}</td>
              <td>{test.test_type.replaceAll('_', ' ')}</td>
              <td>{test.subject_label}</td>
              <td>{test.observed_outcome || test.status}</td>
              <td><span className={`result-chip ${test.evaluation || test.status}`}>{(test.evaluation || test.status).replaceAll('_', ' ')}</span></td>
              <td>{test.duration_seconds == null ? '—' : `${test.duration_seconds.toFixed(1)}s`}</td>
              <td>{test.reason || '—'}</td>
            </tr>)}
          </tbody></table></div>
        </section>

        <section className="panel events-panel">
          <div className="panel-heading"><div><History size={19} /><span>Recognition events</span></div><span className="panel-heading-actions"><small>Latest 50 · no images stored</small><button className="clear-button" onClick={clearRecognitionEvents} disabled={busy || events.length === 0}><Trash2 size={13} /> Clear</button></span></div>
          <div className="table-wrap"><table><thead><tr><th>Time</th><th>Decision</th><th>Identity</th><th>Similarity</th><th>Message</th></tr></thead>
            <tbody>
              {events.length === 0 && <tr><td colSpan="5"><div className="table-empty">Events will appear after recognition begins.</div></td></tr>}
              {events.map(event => <tr key={event.id}>
                <td>{timeLabel(event.created_at)}</td>
                <td><span className={`decision ${event.event_type}`}>{event.event_type === 'recognized' ? <CheckCircle2 size={14} /> : <X size={14} />}{event.event_type}</span></td>
                <td>{event.employee_name || 'Unknown'}</td>
                <td className="mono">{event.similarity == null ? '—' : event.similarity.toFixed(4)}</td>
                <td>{event.guidance || '—'}</td>
              </tr>)}
            </tbody>
          </table></div>
        </section>

        <section className="panel admin-panel">
          <div className="panel-heading"><div><Database size={19} /><span>Administration & privacy</span></div><small>Phase 4 · retention and audit</small></div>
          <div className="admin-grid">
            <form className="retention-card" onSubmit={saveRetention}>
              <div className="admin-card-title"><div><strong>Automatic evidence retention</strong><span>Cleanup runs hourly. Active work, employees and templates are excluded.</span></div><label className="retention-toggle"><input type="checkbox" checked={retentionForm?.enabled ?? false} onChange={event => setRetentionForm(current => ({ ...current, enabled: event.target.checked }))} /><span>{retentionForm?.enabled ? 'Enabled' : 'Disabled'}</span></label></div>
              <div className="retention-fields">
                <label><span>Recognition events</span><div><input type="number" min="1" max="3650" value={retentionForm?.recognition_event_days ?? 30} onChange={event => setRetentionForm(current => ({ ...current, recognition_event_days: event.target.value }))} /><small>days</small></div></label>
                <label><span>Calibration evidence</span><div><input type="number" min="1" max="3650" value={retentionForm?.calibration_days ?? 180} onChange={event => setRetentionForm(current => ({ ...current, calibration_days: event.target.value }))} /><small>days</small></div></label>
                <label><span>RGB evidence</span><div><input type="number" min="1" max="3650" value={retentionForm?.anti_spoof_days ?? 180} onChange={event => setRetentionForm(current => ({ ...current, anti_spoof_days: event.target.value }))} /><small>days</small></div></label>
              </div>
              <div className="retention-actions"><span>Last run: {retention?.last_run_at ? timeLabel(retention.last_run_at) : 'Not yet'}{retentionResult ? ` · Deleted ${Object.values(retentionResult.deleted).reduce((sum, count) => sum + count, 0)} rows` : ''}</span><button type="button" className="run-button" onClick={runRetentionNow} disabled={busy}>Run now</button><button disabled={busy || !retentionForm}><Save size={14} /> Save policy</button></div>
            </form>
            <div className="audit-card">
              <div className="admin-card-title"><div><strong>Audit trail</strong><span>Newest administrative actions. Audit entries cannot be cleared from the dashboard.</span></div><small>{auditLog.length} shown</small></div>
              <div className="table-wrap audit-table"><table><thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Target</th><th>Details</th></tr></thead><tbody>
                {auditLog.length === 0 && <tr><td colSpan="5"><div className="table-empty">Administrative actions will appear here.</div></td></tr>}
                {auditLog.map(entry => <tr key={entry.id}><td>{timeLabel(entry.created_at)}</td><td>{entry.actor}</td><td className="mono">{entry.action}</td><td>{entry.target_type}{entry.target_id ? ` #${entry.target_id}` : ''}</td><td className="audit-details">{entry.details ? JSON.stringify(entry.details) : '—'}</td></tr>)}
              </tbody></table></div>
            </div>
          </div>
        </section>
      </main>
      <footer><span>FaceRec v0.4.2 · LAB</span><span>Door integration: disabled</span><span>Continuous recording: disabled</span></footer>
    </div>
  )
}

export default App
