import { useMemo, useState } from 'react'
import { post } from '../api.js'
import { ApptStatus, BandBadge, ErrorBox, Loading, Modal, RiskProfileCard, Shell, Timeline } from '../components.jsx'
import { fmtDate } from '../i18n.js'
import { useApp, useLoad } from '../state.jsx'
import { answerLabel } from './Survey.jsx'

const NEXT = {
  pending: ['await_result'],
  negative_benign: ['routine_review', 'clinician_plan'],
  incomplete_suspicious: ['further_imaging', 'biopsy', 'specialist_referral', 'clinician_plan'],
  biopsy_confirmed: ['specialist_referral', 'clinician_plan'],
}

function inTab(a, tab) {
  if (tab === 'requests') return ['requested', 'reschedule_requested'].includes(a.status)
  if (tab === 'upcoming') return a.status === 'confirmed' && a.attendance === 'unknown'
  if (tab === 'results') return a.attendance === 'attended' && (!a.findings.length || a.findings[a.findings.length - 1].state === 'pending' || ['incomplete_suspicious'].includes(a.findings[a.findings.length - 1].state))
  return true
}

function FindingForm({ a, onSaved }) {
  const { t } = useApp()
  const [state, setState] = useState('negative_benign')
  const [next, setNext] = useState('routine_review')
  const [date, setDate] = useState('')
  const [clin, setClin] = useState('')
  const [note, setNote] = useState('')
  const [err, setErr] = useState(null)
  return (
    <div className="stack">
      <div className="note blue small">{t('findingHelp')}</div>
      <label className="field">{t('findingState')}
        <select value={state} onChange={(e) => { setState(e.target.value); setNext(NEXT[e.target.value][0]) }}>
          {Object.keys(NEXT).map((s) => <option key={s} value={s}>{t('fs_' + s)}</option>)}
        </select>
      </label>
      <label className="field">{t('nextStep')}
        <select value={next} onChange={(e) => setNext(e.target.value)}>
          {NEXT[state].map((s) => <option key={s} value={s}>{t('ns_' + s)}</option>)}
        </select>
      </label>
      {state !== 'pending' && (
        <div className="grid-2">
          <label className="field">{t('nextReviewDate')}<input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>
          <label className="field">{t('clinicianName')}<input type="text" value={clin} onChange={(e) => setClin(e.target.value)} /></label>
        </div>
      )}
      <label className="field">{t('clinicalNote')}<textarea value={note} onChange={(e) => setNote(e.target.value)} /></label>
      <ErrorBox error={err} />
      <div><button className="btn btn-primary" onClick={async () => {
        setErr(null)
        try { await post(`/api/provider/appointments/${a.id}/finding`, { state, next_step: next, next_review_date: date || null, clinician_name: clin, clinical_note: note }); onSaved() } catch (e) { setErr(e) }
      }}>{t('saveFinding')}</button></div>
    </div>
  )
}

function Detail({ a, onClose, onChanged }) {
  const { t, lang, notify } = useApp()
  const { data: d } = useLoad(`/api/provider/participants/${a.participant.id}`)
  const { data: survey } = useLoad('/api/survey')
  const firstSlot = useMemo(() => {
    const dt = new Date(); dt.setDate(dt.getDate() + 3)
    return dt.toISOString().slice(0, 10)
  }, [])
  const [date, setDate] = useState(a.preferred_date || firstSlot)
  const [time, setTime] = useState('09:00')
  const [missed, setMissed] = useState('transport')
  const [decline, setDecline] = useState('')
  const [err, setErr] = useState(null)
  const act = async (fn, msg) => {
    setErr(null)
    try { await fn(); onChanged(); notify(msg || t('savedDraft')) } catch (e) { setErr(e) }
  }
  const qmap = useMemo(() => Object.fromEntries((survey?.sections || []).flatMap((s) => s.questions).map((q) => [q.id, q])), [survey])
  const lastFinding = a.findings[a.findings.length - 1]

  return (
    <Modal title={`${a.participant.display_name} (${a.participant.code})`} onClose={onClose}>
      <div className="stack">
        <div className="row"><ApptStatus a={a} /><span className="badge t-grey plain">{t('service_' + a.service)}</span>
          {a.recommendation && <span className="badge t-blue plain">{t('pa_' + a.recommendation.action)}</span>}</div>
        <dl className="kv">
          <dt>{t('ageLabel')}</dt><dd>{a.participant.age ?? '—'}</dd>
          <dt>{t('requestedOn')}</dt><dd>{fmtDate(a.created_at, lang, true)}</dd>
          <dt>{t('preferred')}</dt><dd>{a.preferred_date ? fmtDate(a.preferred_date, lang) : '—'} {a.preferred_time ? t('time_' + a.preferred_time) : ''}</dd>
          {a.confirmed_at && <><dt>{t('confirmedFor')}</dt><dd>{fmtDate(a.confirmed_at, lang, true)} ({a.confirmed_by})</dd></>}
          {a.attendance !== 'unknown' && <><dt>{t('recordedBy')}</dt><dd>{a.attendance_by}</dd></>}
          <dt>{t('reportedSymptoms')}</dt><dd>{qmap.q_symptoms ? answerLabel(qmap.q_symptoms, a.symptoms, lang, t) : '—'}</dd>
          <dt>{t('col_band')}</dt><dd><BandBadge model={a.prediction} /></dd>
        </dl>
        {a.participant_note && <div className="note"><strong>{t('noteToHospital')}</strong><br />{a.participant_note}</div>}
        {d?.assessment?.free_text && <div className="note rose"><strong>{t('freeText')}</strong><br />{d.assessment.free_text}</div>}

        {['requested', 'reschedule_requested'].includes(a.status) && (
          <section className="panel stack">
            <h3 className="mb0">{t('confirmDate')}</h3>
            {a.hospital.demo_slots?.length > 0 && <div className="row small"><span className="sim-tag">{t('simulatedSlots')}</span><span className="ltr">{a.hospital.demo_slots.join(', ')}</span></div>}
            <div className="grid-2">
              <input type="date" value={date} onChange={(e) => setDate(e.target.value)} aria-label={t('preferredDate')} />
              <input type="text" className="ltr" value={time} onChange={(e) => setTime(e.target.value)} pattern="\d{2}:\d{2}" aria-label="Time" />
            </div>
            <div className="btn-row">
              <button className="btn btn-primary" onClick={() => act(() => post(`/api/provider/appointments/${a.id}/confirm`, { date, time }), t('ap_confirmed'))}>{t('confirm')}</button>
            </div>
            <div className="row">
              <input type="text" placeholder={t('declineReason')} value={decline} onChange={(e) => setDecline(e.target.value)} style={{ flex: 1 }} />
              <button className="btn btn-danger btn-sm" onClick={() => act(() => post(`/api/provider/appointments/${a.id}/decline`, { reason: decline || 'No capacity' }))}>{t('decline')}</button>
            </div>
          </section>
        )}

        {a.status === 'confirmed' && a.attendance === 'unknown' && (
          <section className="panel stack">
            <h3 className="mb0">{t('col_appointment')}</h3>
            {a.attendance_source === 'self_report' && <div className="note warn small">{t('fl_self_report_unverified')}</div>}
            <div className="btn-row">
              <button className="btn btn-primary" onClick={() => act(() => post(`/api/provider/appointments/${a.id}/attendance`, { attended: true }))}>{t('markAttended')}</button>
              <select value={missed} onChange={(e) => setMissed(e.target.value)} aria-label={t('missedReason')} style={{ width: 'auto' }}>
                {['transport', 'cost', 'worry', 'time', 'illness', 'forgot', 'unreachable', 'other', 'unknown'].map((r) => <option key={r} value={r}>{t('mr_' + r)}</option>)}
              </select>
              <button className="btn btn-secondary" onClick={() => act(() => post(`/api/provider/appointments/${a.id}/attendance`, { attended: false, missed_reason: missed }))}>{t('markMissed')}</button>
            </div>
          </section>
        )}

        {a.attendance === 'attended' && (
          <section className="panel stack">
            <h3 className="mb0">{t('recordFinding')}</h3>
            {lastFinding && (
              <div className="note small">
                <strong>{t('fs_' + lastFinding.state)}</strong> · {t('ns_' + lastFinding.next_step)}
                {lastFinding.next_review_date && <> · {fmtDate(lastFinding.next_review_date, lang)}</>}
                <div className="muted">{lastFinding.clinician_name} · {t('recordedBy')} {lastFinding.entered_by}</div>
                {lastFinding.clinical_note && <div>{lastFinding.clinical_note}</div>}
              </div>
            )}
            {(!lastFinding || ['pending', 'incomplete_suspicious'].includes(lastFinding.state)) && <FindingForm a={a} onSaved={() => { onChanged(); notify(t('saveFinding')) }} />}
          </section>
        )}
        <ErrorBox error={err} />
        {d?.risk_profile && <RiskProfileCard rp={d.risk_profile} staff />}
        {d && <section><h3>{t('timeline')}</h3><Timeline items={[...d.timeline].reverse()} /></section>}
      </div>
    </Modal>
  )
}

export default function Provider() {
  const { t, lang, user } = useApp()
  const { data, error, reload } = useLoad('/api/provider/appointments')
  const [tab, setTab] = useState('requests')
  const [openId, setOpenId] = useState(null)
  if (!data) return <Shell>{error ? <ErrorBox error={error} /> : <Loading />}</Shell>
  const rows = data.filter((a) => inTab(a, tab))
  const open = data.find((a) => a.id === openId)
  const hospName = user?.hospital ? (lang === 'ar' ? user.hospital.name_ar : user.hospital.name_en) : ''
  return (
    <Shell nav={[{ to: '/provider', label: t('nav_requests'), end: true }]}>
      <div className="stack">
        <div>
          <h1 className="mb0">{t('providerTitle')}</h1>
          <div className="muted">{hospName}</div>
        </div>
        <div className="toolbar">
          <div className="seg" role="group">
            {['requests', 'upcoming', 'results', 'all'].map((k) => (
              <button key={k} aria-pressed={tab === k} onClick={() => setTab(k)}>{t('tab_' + k)}<span className="count">{data.filter((a) => inTab(a, k)).length}</span></button>
            ))}
          </div>
        </div>
        <div className="table-wrap">
          <table className="tbl">
            <thead><tr>
              <th>{t('col_participant')}</th><th>{t('serviceLabel')}</th><th>{t('col_action')}</th><th>{t('preferred')}</th><th>{t('col_appointment')}</th><th />
            </tr></thead>
            <tbody>
              {rows.length === 0 && <tr><td colSpan={6} className="empty">{t('noRequests')}</td></tr>}
              {rows.map((a) => (
                <tr key={a.id} className={`click pr-${a.recommendation?.priority || 'normal'}`} onClick={() => setOpenId(a.id)}>
                  <td><div className="cell-strong">{a.participant.display_name}</div><div className="cell-sub ltr">{a.participant.code}</div></td>
                  <td>{t('service_' + a.service)}</td>
                  <td>{a.recommendation ? t('pa_' + a.recommendation.action) : '—'}{a.has_free_text && <div className="cell-sub">✎ {t('freeText')}</div>}</td>
                  <td>{a.preferred_date ? fmtDate(a.preferred_date, lang) : '—'}<div className="cell-sub">{a.preferred_time ? t('time_' + a.preferred_time) : ''}</div></td>
                  <td><ApptStatus a={a} />{a.confirmed_at && <div className="cell-sub">{fmtDate(a.confirmed_at, lang, true)}</div>}</td>
                  <td><button className="btn btn-secondary btn-sm">{t('view')}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {open && <Detail key={open.id + open.status + open.attendance + open.findings.length} a={open} onClose={() => setOpenId(null)} onChanged={reload} />}
    </Shell>
  )
}
