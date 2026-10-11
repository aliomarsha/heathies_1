import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { post } from '../api.js'
import { ApptStatus, BandBadge, ErrorBox, Flag, JourneyRail, Loading, MiniRail, Modal, NoteTriage, Priority, RiskProfileCard, Shell, Timeline } from '../components.jsx'
import { fmtDate } from '../i18n.js'
import { useApp, useLoad } from '../state.jsx'
import { answerLabel, isVisible } from './Survey.jsx'

export function useGovNav() {
  const { t } = useApp()
  return [
    { to: '/programme', label: t('nav_dashboard'), end: true },
    { to: '/programme/worklist', label: t('nav_worklist') },
    { to: '/programme/tasks', label: t('nav_tasks') },
    { to: '/programme/outreach', label: t('nav_outreach') },
  ]
}

function Kpi({ v, d, label, sub }) {
  return (
    <div className="kpi">
      <div className="kpi-v">{v}{d !== undefined && <span className="kpi-d"> / {d}</span>}</div>
      <div className="kpi-l">{label}</div>
      {sub && <div className="kpi-d">{sub}</div>}
    </div>
  )
}

function Bars({ data, labelFn }) {
  const entries = Object.entries(data || {}).sort((a, b) => b[1] - a[1])
  const max = Math.max(1, ...entries.map((e) => e[1]))
  if (!entries.length) return <div className="muted small">—</div>
  return (
    <div className="bars">
      {entries.map(([k, v]) => (
        <div className="bar-row" key={k}><span>{labelFn(k)}</span><span className="bar"><span style={{ width: `${(v / max) * 100}%` }} /></span><span className="num">{v}</span></div>
      ))}
    </div>
  )
}

export function Dashboard() {
  const { t, lang } = useApp()
  const nav = useGovNav()
  const { data: m, error } = useLoad('/api/gov/metrics')
  if (!m) return <Shell nav={nav}>{error ? <ErrorBox error={error} /> : <Loading />}</Shell>
  const r = m.rates
  return (
    <Shell nav={nav}>
      <div className="stack-l">
        <div className="row">
          <h1 className="mb0">{t('govTitle')}</h1><span className="spacer" />
          <span className="muted small">{t('asOf')}: {fmtDate(m.as_of, lang, true)}</span>
        </div>
        {m.demo_data && <div className="note warn">{t('prototypeStrip')} {r.fixture_results.n > 0 && t('fixtureNote')}</div>}

        <section className="panel panel-l">
          <div className="panel-head"><h2>{t('funnelTitle')}</h2><span className="muted small">{t('funnelNote')}</span></div>
          <div className="funnel">
            {m.funnel.map((f, i) => {
              const drop = f.pct !== null && f.pct < 60 && i > 0
              return (
                <div className="funnel-row" key={f.key}>
                  <span className="funnel-label">{t('fn_' + f.key)}</span>
                  <span className={`funnel-bar ${drop ? 'drop' : ''}`}><span style={{ width: `${f.pct ?? 0}%` }} /></span>
                  <span className="funnel-val">{f.n} / {f.d}{f.pct !== null ? ` (${f.pct}%)` : ''}</span>
                </div>
              )
            })}
          </div>
        </section>

        <div className="kpis">
          <Kpi v={m.follow_up_open} label={t('kpi_followup')} />
          <Kpi v={r.symptom_cases_seen.n} d={r.symptom_cases_seen.d} label={t('kpi_symptom')} />
          <Kpi v={m.tasks.open} label={t('kpi_tasks')} sub={`${m.tasks.overdue} ${t('kpi_overdue')}`} />
          <Kpi v={r.missed_any.n} d={r.missed_any.d} label={t('kpi_missed')} />
          <Kpi v={r.model_result_available.n} d={r.model_result_available.d} label={t('kpi_model')} />
          <Kpi v={r.opted_out.n} d={r.opted_out.d} label={t('kpi_optout')} />
        </div>

        <div className="dash-3">
          <section className="panel"><h3>{t('barriersTitle')}</h3>
            <Bars data={m.barriers} labelFn={(k) => t('br_' + k)} /></section>
          <section className="panel"><h3>{t('actionsTitle')}</h3><Bars data={m.actions} labelFn={(k) => t('pa_' + k)} /></section>
          <section className="panel"><h3>{t('bandsTitle')}</h3><Bars data={m.bands} labelFn={(k) => (k === 'pending' ? t('modelPending') : t('band_' + k))} />
            {r.fixture_results.n > 0 && <p className="muted small mt mb0">{t('fixtureNote')}</p>}</section>
        </div>
        <div className="row"><Link className="btn btn-primary" to="/programme/worklist">{t('nav_worklist')}</Link></div>
      </div>
    </Shell>
  )
}

export function Worklist() {
  const { t, lang, user, notify } = useApp()
  const nav = useGovNav()
  const navigate = useNavigate()
  const { data, error, reload } = useLoad('/api/gov/worklist')
  const [filter, setFilter] = useState('stuck')
  const [q, setQ] = useState('')
  const rows = useMemo(() => (data || []).filter((r) => {
    if (q && !(`${r.code} ${r.display_name}`.toLowerCase().includes(q.toLowerCase()))) return false
    if (filter === 'stuck') return r.journey.priority !== 'normal' || r.journey.open_tasks > 0
    if (filter === 'open') return r.journey.flags.includes('follow_up_open')
    return true
  }), [data, filter, q])
  if (!data) return <Shell nav={nav}>{error ? <ErrorBox error={error} /> : <Loading />}</Shell>
  return (
    <Shell nav={nav}>
      <div className="stack">
        <h1 className="mb0">{t('worklistTitle')}</h1>
        <p className="muted mb0">{t('worklistLead')}</p>
        <div className="toolbar">
          <div className="seg" role="group">
            {[['stuck', t('filterStuck')], ['open', t('filterOpen')], ['all', t('filterAll')]].map(([k, l]) => (
              <button key={k} aria-pressed={filter === k} onClick={() => setFilter(k)}>{l}</button>
            ))}
          </div>
          <input type="text" placeholder={t('search')} value={q} onChange={(e) => setQ(e.target.value)} aria-label={t('search')} />
          <span className="spacer" />
          <span className="muted small">{rows.length} / {data.length}</span>
        </div>
        <div className="table-wrap">
          <table className="tbl">
            <thead><tr>
              <th>{t('col_participant')}</th><th>{t('col_journey')}</th><th>{t('col_action')}</th><th>{t('col_band')}</th>
              <th>{t('col_appointment')}</th><th>{t('col_contact')}</th><th>{t('col_owner')}</th><th>{t('col_priority')}</th>
            </tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className={`click pr-${r.journey.priority}`} onClick={() => navigate(`/programme/p/${r.id}`)}>
                  <td><div className="cell-strong">{r.display_name}</div><div className="cell-sub ltr">{r.code}</div></td>
                  <td><MiniRail journey={r.journey} /><div className="cell-sub">{t('st_' + r.journey.stage)}</div>
                    <div className="chips" style={{ marginTop: 4 }}>{r.journey.flags.filter((f) => f !== 'clinician_review').map((f) => <Flag key={f} f={f} />)}</div></td>
                  <td><div className="cell-strong">{t('pn_' + r.journey.next_action)}</div>
                    {r.action && <div className="cell-sub">{t('pa_' + r.action)}{r.clinician_review ? ` + ${t('fl_clinician_review')}` : ''}</div>}</td>
                  <td><BandBadge model={r.model} /></td>
                  <td>{r.appointment ? <><ApptStatus a={r.appointment} /><div className="cell-sub">{lang === 'ar' ? r.appointment.hospital_ar : r.appointment.hospital_en}</div></> : <span className="muted">—</span>}
                    {r.next_review_date && <div className="cell-sub">{t('followUpDate')}: {fmtDate(r.next_review_date, lang)}</div>}</td>
                  <td><span className="small">{t('cs_' + r.contact_state)}</span><div className="cell-sub">{t('channel_' + r.contact_channel)}</div></td>
                  <td onClick={(e) => e.stopPropagation()}>
                    {r.owner ? <span className="small">{r.owner}</span> : (
                      <button className="btn btn-ghost btn-sm" onClick={async () => { await post(`/api/gov/participants/${r.id}/owner`, { owner: user.username }); notify(t('assignToMe')); reload() }}>{t('assignToMe')}</button>
                    )}
                  </td>
                  <td><Priority p={r.journey.priority} />{r.journey.open_tasks > 0 && <div className="cell-sub">{t('nTasks', r.journey.open_tasks, r.journey.overdue_tasks)}</div>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted small">* {t('fixtureNote')}</p>
      </div>
    </Shell>
  )
}

function TaskCard({ task, onChanged }) {
  const { t, lang, notify } = useApp()
  const [res, setRes] = useState('')
  const [err, setErr] = useState(null)
  const today = new Date().toISOString().slice(0, 10)
  const closed = task.status !== 'open'
  const providerOwned = task.kind === 'clinical_follow_up' && task.owner_role === 'provider'
  return (
    <div className={`task ${closed ? 'closed' : ''}`}>
      <div className="row">
        <span className={`badge ${closed ? 't-grey' : task.kind === 'clinical_follow_up' ? 't-rose' : 't-blue'}`}>{t('tk_' + task.kind)}</span>
        {task.participant_code && <Link to={`/programme/p/${task.participant_id}`} className="small ltr">{task.participant_code}</Link>}
        <span className="spacer" />
        <span className="small muted">{closed ? t(task.status) : task.due_date ? `${t('due')} ${fmtDate(task.due_date, lang)}` : ''}</span>
        {!closed && task.due_date && task.due_date < today && <span className="badge t-red">{t('overdue')}</span>}
      </div>
      <div className="small">{task.note}</div>
      <div className="small muted">{task.owner ? task.owner : t('unassigned')}{task.resolution ? ` · ${task.resolution}` : ''}</div>
      {!closed && !providerOwned && (
        <div className="row">
          <input type="text" placeholder={t('resolution')} value={res} onChange={(e) => setRes(e.target.value)} style={{ flex: 1, minHeight: 36, padding: '6px 10px' }} />
          {!task.owner && <button className="btn btn-ghost btn-sm" onClick={async () => { await post(`/api/gov/tasks/${task.id}/claim`); onChanged() }}>{t('claim')}</button>}
          <button className="btn btn-secondary btn-sm" onClick={async () => {
            setErr(null)
            try { await post(`/api/gov/tasks/${task.id}/close`, { resolution: res || 'Done', status: 'done' }); notify(t('closeTask')); onChanged() } catch (e) { setErr(e) }
          }}>{t('closeTask')}</button>
        </div>
      )}
      {providerOwned && !closed && <div className="small muted">{t('clinicalNotesHidden')}</div>}
      <ErrorBox error={err} />
    </div>
  )
}

export function Tasks() {
  const { t } = useApp()
  const nav = useGovNav()
  const { data, error, reload } = useLoad('/api/gov/tasks')
  const [show, setShow] = useState('open')
  if (!data) return <Shell nav={nav}>{error ? <ErrorBox error={error} /> : <Loading />}</Shell>
  const rows = data.filter((x) => (show === 'open' ? x.status === 'open' : true))
  return (
    <Shell nav={nav}>
      <div className="stack">
        <h1 className="mb0">{t('tasksTitle')}</h1>
        <div className="seg" role="group" style={{ justifySelf: 'start' }}>
          <button aria-pressed={show === 'open'} onClick={() => setShow('open')}>{t('open')}<span className="count">{data.filter((x) => x.status === 'open').length}</span></button>
          <button aria-pressed={show === 'all'} onClick={() => setShow('all')}>{t('filterAll')}<span className="count">{data.length}</span></button>
        </div>
        <div className="stack">{rows.map((task) => <TaskCard key={task.id} task={task} onChanged={reload} />)}</div>
        {!rows.length && <div className="empty">—</div>}
      </div>
    </Shell>
  )
}

function OutreachEvent({ e }) {
  const { t, lang } = useApp()
  return (
    <div className={`sms ${e.state}`}>
      <div className="row">
        <span className="badge t-grey plain">{t('tp_' + e.template)}</span>
        {e.participant_code && <Link className="small ltr" to={`/programme/p/${e.participant_id}`}>{e.participant_code}</Link>}
        <span className="spacer" />
        <span className={`badge ${e.state === 'simulated_sent' ? 't-green' : e.state === 'scheduled' ? 't-blue' : 't-grey'}`}>{t('ev_' + e.state)}</span>
      </div>
      <div className="sms-bubble" lang={e.language} dir={e.language === 'ar' ? 'rtl' : 'ltr'}>{e.body_preview}</div>
      <div className="row small muted">
        <span className="sim-tag">{e.channel === 'staff_call' ? t('callTaskBadge') : t('simulatedBadge')}</span>
        <span>{fmtDate(e.scheduled_at, lang, true)}</span>
        {e.cancellation_reason && <span>· {e.cancellation_reason}</span>}
      </div>
    </div>
  )
}

export function Outreach() {
  const { t, lang } = useApp()
  const nav = useGovNav()
  const { data, error } = useLoad('/api/gov/outreach')
  const [state, setState] = useState('all')
  if (!data) return <Shell nav={nav}>{error ? <ErrorBox error={error} /> : <Loading />}</Shell>
  const ev = data.events.filter((e) => state === 'all' || e.state === state)
  const tpl = data.templates
  return (
    <Shell nav={nav}>
      <div className="stack-l">
        <div>
          <h1 className="mb0">{t('nav_outreach')}</h1>
          <div className="note warn mt">{t('outreachLead')}</div>
        </div>
        <div className="dash-grid">
          <section className="stack">
            <div className="row"><h2 className="mb0">{t('outboxTitle')}</h2><span className="spacer" /><span className="muted small">{t('asOf')}: {fmtDate(data.now, lang, true)}</span></div>
            <div className="seg" role="group" style={{ justifySelf: 'start' }}>
              {['all', 'scheduled', 'simulated_sent', 'cancelled', 'suppressed'].map((s) => (
                <button key={s} aria-pressed={state === s} onClick={() => setState(s)}>{s === 'all' ? t('filterAll') : t('ev_' + s)}<span className="count">{s === 'all' ? data.events.length : data.events.filter((e) => e.state === s).length}</span></button>
              ))}
            </div>
            <div className="sms-list">{ev.map((e) => <OutreachEvent key={e.id} e={e} />)}</div>
          </section>
          <aside className="stack">
            <section className="panel"><h3>{t('sequenceTitle')}</h3><p className="small ink2 mb0">{t('seqText', tpl.sequence)}</p></section>
            <section className="panel stack"><h3 className="mb0">{t('templatesTitle')}</h3>
              {Object.entries(tpl.templates).map(([k, v]) => (
                <div key={k}><div className="small cell-strong">{t('tp_' + k)}</div><div className="sms-bubble small" dir={lang === 'ar' ? 'rtl' : 'ltr'}>{v[lang]}</div></div>
              ))}
            </section>
            <section className="panel stack"><h3 className="mb0">{t('callbacksTitle')}</h3>
              {data.callback_tasks.length ? data.callback_tasks.map((c) => (
                <div key={c.id} className="small"><Link className="ltr" to={`/programme/p/${c.participant_id}`}>{c.participant_code}</Link> · {t(c.status)} · {fmtDate(c.created_at, lang)}</div>
              )) : <div className="muted small">—</div>}
            </section>
          </aside>
        </div>
      </div>
    </Shell>
  )
}

function BarrierModal({ p, onClose, onDone }) {
  const { t, lang } = useApp()
  const { data: hospitals } = useLoad(`/api/hospitals?governorate=${p.governorate || ''}`)
  const [barrier, setBarrier] = useState('transport')
  const [note, setNote] = useState('')
  const [hid, setHid] = useState('')
  const [err, setErr] = useState(null)
  return (
    <Modal title={t('barrierTitle')} onClose={onClose}>
      <div className="stack">
        <label className="field">{t('barrierLabel')}
          <select value={barrier} onChange={(e) => setBarrier(e.target.value)}>
            {['transport', 'cost', 'worry', 'time', 'where', 'companion', 'other'].map((b) => <option key={b} value={b}>{t('br_' + b)}</option>)}
          </select>
        </label>
        <label className="field">{t('taskNote')}<input type="text" value={note} onChange={(e) => setNote(e.target.value)} /></label>
        <label className="field">{t('closerProvider')}
          <select value={hid} onChange={(e) => setHid(e.target.value)}>
            <option value="">—</option>
            {(hospitals || []).map((h) => <option key={h.id} value={h.id}>{h.near ? '★ ' : ''}{lang === 'ar' ? h.name_ar : h.name_en}</option>)}
          </select>
        </label>
        <ErrorBox error={err} />
        <button className="btn btn-primary" onClick={async () => {
          try { await post(`/api/gov/participants/${p.id}/barrier`, { barrier, note, new_hospital_id: hid ? Number(hid) : null }); onDone() } catch (e) { setErr(e) }
        }}>{t('saveBarrier')}</button>
      </div>
    </Modal>
  )
}

export function Record() {
  const { id } = useParams()
  const { t, lang, notify } = useApp()
  const nav = useGovNav()
  const { data: d, error, reload } = useLoad(`/api/gov/participants/${id}`)
  const { data: survey } = useLoad('/api/survey')
  const [modal, setModal] = useState(null)
  const [taskKind, setTaskKind] = useState('callback')
  const [taskNote, setTaskNote] = useState('')
  const riskPending = d?.risk_profile?.status === 'pending'
  useEffect(() => {
    if (!riskPending) return undefined
    const tm = setTimeout(reload, 3000)
    return () => clearTimeout(tm)
  }, [riskPending, d, reload])
  if (!d) return <Shell nav={nav}>{error ? <ErrorBox error={error} /> : <Loading />}</Shell>
  const p = d.participant
  const act = async (fn, msg) => { try { await fn(); reload(); if (msg) notify(msg) } catch (e) { notify(e.message, 'err') } }
  const qs = (survey?.sections || []).flatMap((s) => s.questions)

  return (
    <Shell nav={nav}>
      <div className="stack-l">
        <div className="row">
          <div>
            <div className="muted small">{t('recordTitle')}</div>
            <h1 className="mb0">{p.display_name} <span className="muted ltr" style={{ fontWeight: 400, fontSize: '1.1rem' }}>{p.code}</span></h1>
          </div>
          <span className="spacer" />
          <Priority p={d.journey.priority} />
          {d.journey.flags.map((f) => <Flag key={f} f={f} />)}
        </div>
        <section className="panel"><JourneyRail journey={d.journey} />
          <div className="mt"><strong>{t('col_action')}:</strong> {t('pn_' + d.journey.next_action)}</div></section>

        <div className="record-grid">
          <div className="stack">
            {d.recommendation && (
              <section className="panel">
                <div className="panel-head"><h3>{t('policyTitle')}</h3><span className="badge t-grey plain">{t('staffOnly')}</span></div>
                <dl className="kv">
                  <dt>{t('col_action')}</dt><dd>{t('pa_' + d.recommendation.action)} ({t('service_' + d.recommendation.service)})</dd>
                  <dt>{t('col_priority')}</dt><dd><Priority p={d.recommendation.priority} /></dd>
                  <dt>{t('reasonCodes')}</dt><dd className="ltr small">{d.recommendation.reason_codes.join(', ')}</dd>
                  <dt>{t('policyVersion')}</dt><dd className="ltr small">{d.recommendation.policy_version}</dd>
                </dl>
              </section>
            )}
            {d.prediction && (
              <section className="panel">
                <div className="panel-head"><h3>{t('modelTitle')}</h3><BandBadge model={d.prediction} /></div>
                {d.prediction.is_fixture && <div className="note warn small mb">{t('fixtureNote')}</div>}
                <dl className="kv ltr">
                  <dt>status</dt><dd>{d.prediction.status}</dd>
                  <dt>{t('score')}</dt><dd>{d.prediction.score ?? '—'}</dd>
                  <dt>{t('modelVersion')}</dt><dd>{d.prediction.model_version ?? '—'}</dd>
                  <dt>{t('target')}</dt><dd>{d.prediction.target_definition ?? '—'}</dd>
                  <dt>{t('thresholds')}</dt><dd>{d.prediction.threshold_version ?? '—'}</dd>
                  <dt>{t('backendLbl')}</dt><dd>{d.prediction.backend}</dd>
                  <dt>{t('reasonCodes')}</dt><dd>{(d.prediction.reason_codes || []).join(', ') || '—'}</dd>
                  {d.prediction.error_message && <><dt>error</dt><dd>{d.prediction.error_message}</dd></>}
                </dl>
              </section>
            )}
            <RiskProfileCard rp={d.risk_profile} staff
              onRegenerate={d.assessment ? () => act(() => post(`/api/gov/participants/${p.id}/risk-profile`), t('rp_pending')) : undefined} />
            {d.assessment && (
              <section className="panel">
                <h3>{t('answersTitle')}</h3>
                <div className="small muted ltr mb">{d.assessment.public_id} · {d.assessment.schema_version}</div>
                {qs.filter((q) => isVisible(q, d.assessment.answers)).map((q) => (
                  <div className="review-row" key={q.id}>
                    <div className="review-q">{q.title[lang]} <span className="badge t-outline plain" style={{ fontSize: '.7rem' }}>{q.group}</span></div>
                    <div className="review-a">{answerLabel(q, d.assessment.answers[q.id], lang, t)}</div>
                  </div>
                ))}
                {d.assessment.free_text && <div className="note rose mt"><strong>{t('freeText')}</strong><br />{d.assessment.free_text}</div>}
                {d.note_triage && <div className="mt"><NoteTriage tr={d.note_triage} /></div>}
              </section>
            )}
            {d.appointments.map((a) => (
              <section className="panel stack" key={a.id}>
                <div className="hosp-top"><div><div className="hosp-name">{lang === 'ar' ? a.hospital.name_ar : a.hospital.name_en}</div><div className="muted small">{t('service_' + a.service)}</div></div><ApptStatus a={a} /></div>
                <dl className="kv">
                  <dt>{t('requestedOn')}</dt><dd>{fmtDate(a.created_at, lang, true)}</dd>
                  {a.confirmed_at && <><dt>{t('confirmedFor')}</dt><dd>{fmtDate(a.confirmed_at, lang, true)} ({a.confirmed_by})</dd></>}
                  {a.attendance !== 'unknown' && <><dt>{t('recordedBy')}</dt><dd>{a.attendance_by}{a.missed_reason ? ` · ${t('mr_' + a.missed_reason)}` : ''}</dd></>}
                  {a.cancel_reason && <><dt>{t('cancelReason')}</dt><dd>{a.cancel_reason}</dd></>}
                </dl>
                {a.findings.map((f) => (
                  <div key={f.id} className={`note ${f.state === 'negative_benign' ? '' : 'rose'} small`}>
                    <strong>{t('fs_' + f.state)}</strong> · {t('ns_' + f.next_step)}{f.next_review_date ? ` · ${fmtDate(f.next_review_date, lang)}` : ''}
                    <div className="muted">{f.clinician_name} · {t('recordedBy')} {f.entered_by}</div>
                    <div className="muted">{t('clinicalNotesHidden')}</div>
                  </div>
                ))}
              </section>
            ))}
          </div>

          <div className="stack">
            <section className="panel stack">
              <h3 className="mb0">{t('col_contact')}</h3>
              <dl className="kv">
                <dt>{t('col_contact')}</dt><dd>{t('cs_' + p.contact_state)}</dd>
                <dt>{t('contactTitle')}</dt><dd>{t('channel_' + p.contact_channel)}, {t('time_' + p.contact_time)}</dd>
                <dt>{t('phoneLabel')}</dt><dd className="ltr">{p.phone || '—'}</dd>
                <dt>{t('discreet')}</dt><dd>{p.discreet_messages ? t('yes') : t('no')}</dd>
                <dt>{t('consentTitle')}</dt><dd>{p.consent_given ? `${p.consent_version}, ${fmtDate(p.consent_at, lang)}` : '—'}</dd>
                <dt>{t('col_owner')}</dt><dd>{p.owner || t('unassigned')}</dd>
              </dl>
              {!p.opted_out && (
                <div className="btn-row">
                  <button className="btn btn-secondary btn-sm" onClick={() => act(() => post(`/api/gov/participants/${p.id}/contact`, { state: 'reached' }), t('reached'))}>{t('reached')}</button>
                  <button className="btn btn-secondary btn-sm" onClick={() => act(() => post(`/api/gov/participants/${p.id}/contact`, { state: 'unreachable' }), t('unreachable'))}>{t('unreachable')}</button>
                  <button className="btn btn-secondary btn-sm" onClick={() => setModal('barrier')}>{t('barrierTitle')}</button>
                </div>
              )}
              <button className="btn btn-ghost btn-sm" style={{ justifySelf: 'start' }}
                onClick={() => act(() => post(`/api/gov/participants/${p.id}/opt-out`, { opted_out: !p.opted_out }))}>
                {p.opted_out ? t('undoOptOut') : t('recordOptOut')}
              </button>
            </section>

            <section className="panel stack">
              <h3 className="mb0">{t('tasksTitle')}</h3>
              {d.tasks.map((task) => <TaskCard key={task.id} task={task} onChanged={reload} />)}
              <div className="row">
                <select value={taskKind} onChange={(e) => setTaskKind(e.target.value)} style={{ width: 'auto' }}>
                  {['callback', 'barrier_support', 'clarification', 'staff_review', 'reschedule'].map((k) => <option key={k} value={k}>{t('tk_' + k)}</option>)}
                </select>
                <input type="text" placeholder={t('taskNote')} value={taskNote} onChange={(e) => setTaskNote(e.target.value)} style={{ flex: 1 }} />
                <button className="btn btn-secondary btn-sm" onClick={() => act(() => post(`/api/gov/participants/${p.id}/tasks`, { kind: taskKind, note: taskNote || t('tk_' + taskKind) }), t('addTask')).then(() => setTaskNote(''))}>{t('addTask')}</button>
              </div>
            </section>

            {d.help_requests.length > 0 && (
              <section className="panel"><h3>{t('helpRequests')}</h3>
                {d.help_requests.map((h) => <div key={h.id} className="small mb"><strong>{t('ht_' + h.topic)}</strong> · {fmtDate(h.created_at, lang, true)} · {h.status}{h.message && <div className="ink2">{h.message}</div>}</div>)}
              </section>
            )}

            <section className="panel stack"><h3 className="mb0">{t('outreachTitle')}</h3>
              {d.outreach.length ? d.outreach.map((e) => <OutreachEvent key={e.id} e={e} />) : <div className="muted small">—</div>}
            </section>
            <section className="panel"><h3>{t('timeline')}</h3><Timeline items={[...d.timeline].reverse()} /></section>
            <section className="panel"><h3>{t('auditTitle')}</h3>
              <div className="stack" style={{ gap: 6 }}>
                {d.audit.map((l, i) => <div key={i} className="small"><span className="muted">{fmtDate(l.at, lang, true)}</span> · <strong>{l.actor}</strong> ({l.role}) · <span className="ltr">{l.action}</span></div>)}
              </div>
            </section>
          </div>
        </div>
      </div>
      {modal === 'barrier' && <BarrierModal p={p} onClose={() => setModal(null)} onDone={() => { setModal(null); reload(); notify(t('saveBarrier')) }} />}
    </Shell>
  )
}
