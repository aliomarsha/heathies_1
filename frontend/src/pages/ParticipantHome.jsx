import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { post, put } from '../api.js'
import { ApptStatus, ErrorBox, JourneyRail, Loading, Modal, RiskProfileCard, Shell, Timeline } from '../components.jsx'
import { fmtDate } from '../i18n.js'
import { useApp, useLoad } from '../state.jsx'

function NextStep({ o }) {
  const { t } = useApp()
  const rec = o.recommendation
  const j = o.journey
  const navigate = useNavigate()
  const live = o.appointments.find((a) => ['requested', 'confirmed', 'reschedule_requested'].includes(a.status) && a.attendance === 'unknown')

  if (!o.latest_assessment) {
    return (
      <section className="result-hero" id="next-step">
        <div className="result-kicker">{t('yourNextStep')}</div>
        <h2>{t('na_complete_assessment')}</h2>
        <button className="btn btn-primary mt" onClick={() => navigate('/me/assessment')}>{t(o.draft && Object.keys(o.draft.answers || {}).length ? 'continueAssessment' : 'startAssessment')}</button>
      </section>
    )
  }

  const action = rec.action
  const young = rec.reason_codes.includes('BELOW_CAMPAIGN_AGE')
  const cls = action === 'clinical_assessment' ? 'clinical' : action === 'clarification' ? 'clarify' : ''
  const done = ['attended', 'next_step_recorded'].includes(j.stage)
  const showBooking = rec.booking_eligible && !live && !done

  return (
    <section className={`result-hero ${cls}`} id="next-step">
      <div className="result-kicker">{t('yourNextStep')}</div>
      {done ? (
        <h2>{t('na_' + j.next_action)}</h2>
      ) : (
        <>
          <h2>{t('act_' + action)}</h2>
          <p className="ink2">{young && action === 'plan_review' ? t('act_plan_review_young_body') : t('act_' + action + '_body')}</p>
          {j.next_action !== 'request_appointment' && <p className="mb0"><strong>{t('na_' + j.next_action)}</strong></p>}
        </>
      )}
      <div className="btn-row mt">
        {showBooking && !done && <Link className="btn btn-primary" to="/me/hospitals">{t('chooseHospital')}</Link>}
      </div>
      {!done && (
        <>
          <hr className="divider" />
          <h3>{t('whyTitle')}</h3>
          <ul className="reasons">
            {rec.reason_codes.map((r) => <li key={r}>{t('rs_' + r)}</li>)}
          </ul>
          {rec.clinician_review && <p className="muted small mt mb0">{t('clinicianReviewNote')}</p>}
        </>
      )}
    </section>
  )
}

function Estimate({ pred }) {
  const { t } = useApp()
  if (!pred) return null
  return (
    <section className="panel">
      <h3>{t('estimateTitle')}</h3>
      {pred.status === 'ok' ? (
        <>
          <div className="band-scale" aria-label={t('estimateTitle')}>
            {['lower', 'intermediate', 'higher'].map((b) => <span key={b} className={pred.band === b ? 'on' : ''}>{t('band_' + b)}</span>)}
          </div>
          {pred.is_fixture && <span className="sim-tag">{t('estimateDemo')}</span>}
          <p className="muted small mt mb0">{t('estimateNote')}</p>
        </>
      ) : (
        <>
          <span className="badge t-amber">{t('estimatePending')}</span>
          <p className="muted small mt mb0">{t('estimatePendingNote')}</p>
        </>
      )}
    </section>
  )
}

function Appointment({ a, onChanged }) {
  const { t, lang, notify } = useApp()
  const [modal, setModal] = useState(null)
  const [date, setDate] = useState(a.preferred_date || '')
  const [time, setTime] = useState(a.preferred_time || 'morning')
  const [reason, setReason] = useState('')
  const [err, setErr] = useState(null)
  const hosp = lang === 'ar' ? a.hospital.name_ar : a.hospital.name_en
  const active = ['requested', 'confirmed', 'reschedule_requested'].includes(a.status) && a.attendance === 'unknown'

  const act = async (fn, msg) => {
    setErr(null)
    try { const o = await fn(); onChanged(o); setModal(null); if (msg) notify(msg) } catch (e) { setErr(e) }
  }

  return (
    <div className="panel stack">
      <div className="hosp-top">
        <div>
          <div className="small muted">{t('apptTitle')}</div>
          <div className="hosp-name">{hosp}</div>
          <div className="muted small">{t('service_' + a.service)}</div>
        </div>
        <ApptStatus a={a} />
      </div>
      {a.status === 'confirmed' && a.confirmed_at && a.attendance === 'unknown' && (
        <div className="note"><strong>{t('confirmedFor')}:</strong> {fmtDate(a.confirmed_at, lang, true)}</div>
      )}
      {['requested', 'reschedule_requested'].includes(a.status) && <div className="note warn">{t('notBookedYet')}. {t('na_provider_confirmation')}</div>}
      {a.attendance_source === 'self_report' && !a.attendance_verified && <div className="note warn">{t('selfReported')}</div>}
      {a.findings?.length > 0 && <FindingCard f={a.findings[a.findings.length - 1]} />}
      {active && (
        <div className="btn-row">
          <button className="btn btn-secondary btn-sm" onClick={() => setModal('reschedule')}>{t('reschedule')}</button>
          <Link className="btn btn-secondary btn-sm" to={`/me/hospitals?replace=${a.id}`}>{t('changeHospital')}</Link>
          <button className="btn btn-danger btn-sm" onClick={() => setModal('cancel')}>{t('cancelAppt')}</button>
          {a.status === 'confirmed' && !a.attendance_source && (
            <button className="btn btn-ghost btn-sm" onClick={() => act(() => post(`/api/me/appointments/${a.id}/self-report`, { attended: true }))}>{t('iWent')}</button>
          )}
        </div>
      )}
      {modal === 'reschedule' && (
        <Modal title={t('reschedule')} onClose={() => setModal(null)}>
          <div className="stack">
            <label className="field">{t('preferredDate')}<input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>
            <label className="field">{t('preferredTime')}
              <select value={time} onChange={(e) => setTime(e.target.value)}>{['morning', 'afternoon', 'any'].map((v) => <option key={v} value={v}>{t('time_' + v)}</option>)}</select>
            </label>
            <ErrorBox error={err} />
            <button className="btn btn-primary" onClick={() => act(() => post(`/api/me/appointments/${a.id}/reschedule`, { preferred_date: date || null, preferred_time: time }), t('requestSent'))}>{t('sendRequest')}</button>
          </div>
        </Modal>
      )}
      {modal === 'cancel' && (
        <Modal title={t('cancelAppt')} onClose={() => setModal(null)}>
          <div className="stack">
            <label className="field">{t('cancelReason')}<input type="text" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={200} /></label>
            <ErrorBox error={err} />
            <button className="btn btn-danger" onClick={() => act(() => post(`/api/me/appointments/${a.id}/cancel`, { reason }))}>{t('cancelAppt')}</button>
          </div>
        </Modal>
      )}
    </div>
  )
}

function FindingCard({ f }) {
  const { t, lang } = useApp()
  const tone = f.state === 'negative_benign' ? '' : f.state === 'pending' ? 'warn' : 'rose'
  return (
    <div className={`note ${tone}`}>
      <strong>{t('fd_title')}</strong>
      <p className="mb0">{t('fd_' + f.state)}</p>
      {f.state !== 'pending' && f.state !== 'care_team_will_contact' && <p className="mb0">{t('nextStep')}: {t('ns_' + f.next_step)}</p>}
      {f.next_review_date && f.state === 'negative_benign' && <p className="mb0"><strong>{t('nextReview')}:</strong> {fmtDate(f.next_review_date, lang)}</p>}
    </div>
  )
}

function HelpModal({ onClose, onDone }) {
  const { t, notify } = useApp()
  const [topic, setTopic] = useState('booking')
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState(null)
  return (
    <Modal title={t('helpTitle')} onClose={onClose}>
      <div className="stack">
        <p className="muted mb0">{t('helpLead')}</p>
        <div className="opts" role="radiogroup" aria-label={t('helpTopic')}>
          {['survey', 'booking', 'transport', 'cost', 'worry', 'other'].map((x) => (
            <button key={x} type="button" className="opt" role="radio" aria-checked={topic === x} onClick={() => setTopic(x)}><span className="ind" />{t('ht_' + x)}</button>
          ))}
        </div>
        <label className="field">{t('helpMessage')}<textarea value={msg} onChange={(e) => setMsg(e.target.value)} maxLength={1000} /></label>
        <ErrorBox error={err} />
        <button className="btn btn-primary" onClick={async () => {
          try { const o = await post('/api/me/help', { topic, message: msg }); onDone(o); notify(t('helpSent')); onClose() } catch (e) { setErr(e) }
        }}>{t('sendHelp')}</button>
      </div>
    </Modal>
  )
}

function SettingsModal({ p, onClose, onDone }) {
  const { t, setLang } = useApp()
  const [err, setErr] = useState(null)
  const upd = async (body) => {
    try { const o = await put('/api/me/contact', body); onDone(o); if (body.language) setLang(body.language) } catch (e) { setErr(e) }
  }
  return (
    <Modal title={t('settings')} onClose={onClose}>
      <div className="stack">
        <label className="field">{t('language')}
          <select value={p.language} onChange={(e) => upd({ language: e.target.value })}><option value="ar">العربية</option><option value="en">English</option></select>
        </label>
        <div className="opts" role="radiogroup" aria-label={t('contactTitle')}>
          {['sms', 'call', 'none'].map((c) => (
            <button key={c} type="button" className="opt" role="radio" aria-checked={p.contact_channel === c} onClick={() => upd({ channel: c })}><span className="ind" />{t('channel_' + c)}</button>
          ))}
        </div>
        <label className="field">{t('timeLabel')}
          <select value={p.contact_time} onChange={(e) => upd({ time: e.target.value })}>{['any', 'morning', 'afternoon', 'evening'].map((v) => <option key={v} value={v}>{t('time_' + v)}</option>)}</select>
        </label>
        <label className="check"><input type="checkbox" checked={p.discreet_messages} onChange={(e) => upd({ discreet_messages: e.target.checked })} /><span>{t('discreet')}</span></label>
        <hr className="divider" />
        {p.opted_out ? (
          <>
            <div className="note warn">{t('optOutOn')}</div>
            <button className="btn btn-secondary" onClick={() => upd({ opted_out: false })}>{t('optIn')}</button>
          </>
        ) : (
          <button className="btn btn-danger" onClick={() => upd({ opted_out: true })}>{t('optOut')}</button>
        )}
        <ErrorBox error={err} />
      </div>
    </Modal>
  )
}

export default function ParticipantHome() {
  const { t } = useApp()
  const { data: o, error, setData, reload } = useLoad('/api/me/overview')
  const pending = o?.risk_profile?.status === 'pending'
  useEffect(() => {
    if (!pending) return undefined
    const id = setTimeout(reload, 3000)   // the profile is generated in the background
    return () => clearTimeout(id)
  }, [pending, o, reload])
  const [modal, setModal] = useState(null)
  const navigate = useNavigate()
  const loc = useLocation()

  useEffect(() => {
    if (o && loc.hash === '#next-step') document.getElementById('next-step')?.scrollIntoView({ block: 'start' })
  }, [o, loc.hash])

  if (!o) return <Shell narrow>{error ? <ErrorBox error={error} /> : <Loading />}</Shell>
  const p = o.participant
  const appts = o.appointments.filter((a) => !['cancelled', 'declined'].includes(a.status) || o.appointments.length === 1)
  const draftInProgress = o.draft && (o.latest_assessment || Object.keys(o.draft.answers || {}).length)

  return (
    <Shell narrow>
      <div className="stack-l">
        <div>
          <div className="row">
            <h1 className="mb0">{t('hello')} <bdi>{p.display_name}</bdi></h1>
            <span className="spacer" />
            <span className="badge t-outline plain ltr">{p.code}</span>
          </div>
          {p.opted_out && <div className="note warn mt">{t('na_no_contact_opted_out')}</div>}
        </div>

        <section className="panel">
          <h3>{t('yourJourney')}</h3>
          <JourneyRail journey={o.journey} />
        </section>

        {draftInProgress && o.latest_assessment && (
          <div className="note blue row"><span>{t('tl_assessment_draft')}</span><span className="spacer" />
            <button className="btn btn-secondary btn-sm" onClick={() => navigate('/me/assessment')}>{t('continueAssessment')}</button></div>
        )}

        <NextStep o={o} />
        <Estimate pred={o.prediction} />
        <RiskProfileCard rp={o.risk_profile} />

        {appts.map((a) => <Appointment key={a.id} a={a} onChanged={setData} />)}

        <div className="btn-row">
          <button className="btn btn-secondary" onClick={() => setModal('help')}>{t('getHelp')}</button>
          <button className="btn btn-secondary" onClick={() => setModal('settings')}>{t('settings')}</button>
          {o.latest_assessment && !o.draft && (
            <button className="btn btn-ghost" onClick={async () => { await post('/api/me/assessment/new'); navigate('/me/assessment') }}>{t('startNew')}</button>
          )}
        </div>

        <section className="panel">
          <h3>{t('timeline')}</h3>
          <Timeline items={[...o.timeline].reverse()} />
        </section>
      </div>
      {modal === 'help' && <HelpModal onClose={() => setModal(null)} onDone={setData} />}
      {modal === 'settings' && <SettingsModal p={p} onClose={() => setModal(null)} onDone={setData} />}
    </Shell>
  )
}
