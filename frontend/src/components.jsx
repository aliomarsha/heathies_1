import { useEffect, useState } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { post } from './api.js'
import { fmtDate } from './i18n.js'
import { useApp } from './state.jsx'

export const STAGES = ['enrolled', 'assessment_started', 'assessment_submitted', 'appointment_requested', 'appointment_confirmed', 'attended', 'next_step_recorded']

export function BrandMark() {
  // Original mark: a protective arc around a ribbon loop. Partner emblems can be added beside it once approved.
  return (
    <svg className="brand-mark" viewBox="0 0 40 40" aria-hidden="true">
      <rect width="40" height="40" rx="10" fill="#0f5a47" />
      <path d="M20 9c-4.2 0-6.6 3.3-5.3 7.4 1 3 3.2 6.1 5.3 8.9 2.1-2.8 4.3-5.9 5.3-8.9C26.6 12.3 24.2 9 20 9Z" fill="none" stroke="#f3c6d4" strokeWidth="2.6" strokeLinejoin="round" />
      <path d="M15.6 18.2 10.5 30.5M24.4 18.2l5.1 12.3" stroke="#f3c6d4" strokeWidth="2.6" strokeLinecap="round" />
      <path d="M8 30.5h24" stroke="#ffffff" strokeOpacity=".55" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  )
}

export function Header({ nav }) {
  const { t, lang, setLang, user, signOut } = useApp()
  const navigate = useNavigate()
  return (
    <>
      <div className="strip">{t('prototypeStrip')}</div>
      <header className="header">
        <div className="header-in">
          <Link to="/" className="brand" aria-label={t('appName')}>
            <BrandMark />
            <div>
              <div className="brand-name">{t('appName')}</div>
              <div className="brand-sub">{t('programme')}</div>
            </div>
          </Link>
          <div className="header-tools">
            <button className="btn btn-ghost btn-sm" onClick={() => setLang(lang === 'ar' ? 'en' : 'ar')} lang={lang === 'ar' ? 'en' : 'ar'}>
              {t('langSwitch')}
            </button>
            {user && (
              <>
                <span className="who">{user.role === 'participant' ? <span className="ltr">{user.participant_code}</span> : user.display_name}</span>
                <button className="btn btn-secondary btn-sm" onClick={async () => { await signOut(); navigate('/') }}>{t('signOut')}</button>
              </>
            )}
          </div>
        </div>
        {nav && (
          <nav className="nav" aria-label="Sections">
            {nav.map((n) => <NavLink key={n.to} to={n.to} end={n.end}>{n.label}</NavLink>)}
          </nav>
        )}
      </header>
    </>
  )
}

export function Footer() {
  const { t } = useApp()
  return (
    <footer className="footer">
      <div className="footer-in">
        <div>{t('notEmergency')}</div>
        <div>{t('helpLine')}</div>
        <div>Team Healthies, AUB health hackathon prototype, version 0.1</div>
      </div>
    </footer>
  )
}

export function Shell({ nav, children, narrow }) {
  return (
    <>
      <Header nav={nav} />
      <main>
        <div className={narrow ? 'page-narrow' : 'page'}>{children}</div>
      </main>
      <Footer />
    </>
  )
}

export function JourneyRail({ journey }) {
  const { t } = useApp()
  const idx = journey?.stage_index ?? 0
  const stuck = (journey?.flags || []).some((f) => ['missed_appointment', 'follow_up_open', 'result_pending', 'finding_pending'].includes(f))
  return (
    <div className="rail" role="list" aria-label={t('yourJourney')}>
      {STAGES.map((s, i) => {
        const cls = i < idx ? 'done' : i === idx ? (stuck ? 'stuck' : (i === STAGES.length - 1 ? 'done' : 'current')) : ''
        return (
          <div key={s} role="listitem" className={`rail-step ${cls}`} aria-current={i === idx ? 'step' : undefined}>
            <span className="rail-dot" />
            {t('st_' + s)}
          </div>
        )
      })}
    </div>
  )
}

export function MiniRail({ journey }) {
  const { t } = useApp()
  const idx = journey.stage_index
  const stuck = journey.flags.some((f) => ['missed_appointment', 'follow_up_open', 'result_pending', 'finding_pending'].includes(f))
  return (
    <span className="mini-rail" title={t('st_' + journey.stage)} aria-label={t('st_' + journey.stage)}>
      {STAGES.map((s, i) => <i key={s} className={i < idx ? 'd' : i === idx ? (stuck ? 's' : i === 6 ? 'd' : 'c') : ''} />)}
    </span>
  )
}

const FLAG_TONE = {
  opted_out: 't-grey', missed_appointment: 't-amber', result_pending: 't-amber', follow_up_open: 't-rose',
  finding_pending: 't-amber', clinician_review: 't-blue', self_report_unverified: 't-amber',
}
export function Flag({ f }) {
  const { t } = useApp()
  return <span className={`badge ${FLAG_TONE[f] || 't-grey'}`}>{t('fl_' + f)}</span>
}

export function Priority({ p }) {
  const { t } = useApp()
  const tone = p === 'high' ? 't-rose' : p === 'medium' ? 't-amber' : 't-grey'
  return <span className={`badge ${tone}`}>{t('pr_' + p)}</span>
}

export function BandBadge({ model }) {
  const { t } = useApp()
  if (!model) return <span className="muted">—</span>
  if (model.status !== 'ok') return <span className="badge t-amber">{t('modelPending')}</span>
  const tone = model.band === 'higher' ? 't-rose' : model.band === 'intermediate' ? 't-blue' : 't-grey'
  return <span className={`badge ${tone}`}>{t('band_' + model.band)}{model.is_fixture ? ' *' : ''}</span>
}

const AP_TONE = { requested: 't-amber', reschedule_requested: 't-amber', confirmed: 't-green', cancelled: 't-grey', declined: 't-red', closed: 't-grey' }
export function ApptStatus({ a }) {
  const { t } = useApp()
  if (a.attendance === 'attended') return <span className="badge t-green">{t('att_attended')}</span>
  if (a.attendance === 'missed') return <span className="badge t-amber">{t('att_missed')}</span>
  return <span className={`badge ${AP_TONE[a.status] || 't-grey'}`}>{t('ap_' + a.status)}</span>
}

export function Modal({ title, onClose, children }) {
  useEffect(() => {
    const h = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])
  return (
    <div className="modal-back" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="panel-head"><h2>{title}</h2><button className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Close">✕</button></div>
        {children}
      </div>
    </div>
  )
}

export function Toast() {
  const { toast } = useApp()
  if (!toast) return null
  return <div className={`toast ${toast.kind === 'err' ? 'err' : ''}`} role="status">{toast.msg}</div>
}

export function Timeline({ items }) {
  const { t, lang, user } = useApp()
  const staff = user && user.role !== 'participant'
  return (
    <ol className="tl">
      {items.map((e, i) => (
        <li key={i}>
          <span className={`tl-dot ${e.status}`} />
          <div>
            <div className="tl-title">
              {t('tl_' + e.kind)}
              {e.kind === 'recommendation' && e.action ? ` · ${t('pa_' + e.action)}` : ''}
              {staff && e.kind === 'finding' && e.state ? ` · ${t('fs_' + e.state)}` : ''}
            </div>
            <div className="tl-meta">
              {fmtDate(e.at, lang, true)}
              {e.hospital ? ` · ${lang === 'ar' ? e.hospital.name_ar : e.hospital.name_en}` : ''}
              {e.when ? ` · ${fmtDate(e.when, lang, true)}` : ''}
              {e.by ? ` · ${e.by}` : ''}
              {e.reason ? ` · ${t('mr_' + e.reason) !== 'mr_' + e.reason ? t('mr_' + e.reason) : e.reason}` : ''}
            </div>
          </div>
        </li>
      ))}
    </ol>
  )
}

export function Loading() {
  const { t } = useApp()
  return <div className="empty">{t('loading')}</div>
}

export function ErrorBox({ error }) {
  const { t } = useApp()
  if (!error) return null
  const msg = error.status === 0 || !error.message ? t('errorGeneric') : error.message
  return <div className="note red" role="alert">{msg}</div>
}

// Demo controls (bottom corner). Clearly a demo affordance; remove for a real pilot.
export function DemoDock() {
  const { t, meta, refreshMeta, bump, notify, signIn, user } = useApp()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const navigate = useNavigate()
  const run = async (fn, msg) => {
    setBusy(true)
    try { await fn(); await refreshMeta(); bump(); if (msg) notify(msg) } catch (e) { notify(e.message || t('errorGeneric'), 'err') } finally { setBusy(false) }
  }
  const quick = async (username, to) => {
    const r = await post('/api/auth/login', { username, password: 'demo1234' })
    signIn(r.token, r.user)
    navigate(to)
  }
  const quickP = async (code) => {
    const r = await post('/api/auth/participant-login', { code, pin: '1234' })
    signIn(r.token, r.user)
    navigate('/me')
  }
  return (
    <div className="demo-dock">
      {open && (
        <div className="demo-panel" role="dialog" aria-label={t('demoPanel')}>
          <div className="row"><strong>{t('demoPanel')}</strong><span className="spacer" /><button className="btn btn-ghost btn-sm" onClick={() => setOpen(false)}>✕</button></div>
          {meta && (
            <div className="small">
              <div>{t('asOf')}: <strong>{fmtDate(meta.sim_now, 'en', true)}</strong> {meta.sim_offset_days ? `(+${Math.round(meta.sim_offset_days * 10) / 10}d)` : ''}</div>
              <div>{t('modelBackend')}: <strong>{meta.model_backend}</strong>{meta.model_is_fixture ? ` — ${t('fixtureMode')}` : ''}</div>
            </div>
          )}
          <h4>Time</h4>
          <div className="btn-row">
            {[1, 3, 7].map((d) => (
              <button key={d} disabled={busy} className="btn btn-secondary btn-sm" onClick={() => run(() => post('/api/demo/advance', { days: d }))}>{t('advance' + d)}</button>
            ))}
          </div>
          <label className="check">
            <input type="checkbox" checked={!!meta?.demo_model_failure} disabled={busy}
              onChange={(e) => run(() => post('/api/demo/model-failure', { enabled: e.target.checked }))} />
            <span>{t('modelFail')}</span>
          </label>
          <h4>{t('quickLogin')}</h4>
          <div className="btn-row">
            <button className="btn btn-secondary btn-sm" onClick={() => quick('programme', '/programme')}>Programme</button>
            <button className="btn btn-secondary btn-sm" onClick={() => quick('rhuh.desk', '/provider')}>Hospital (RHUH)</button>
            <button className="btn btn-secondary btn-sm" onClick={() => quick('baabda.desk', '/provider')}>Hospital (Baabda)</button>
            <button className="btn btn-secondary btn-sm" onClick={() => quickP('HL-1001')}>HL-1001</button>
            <button className="btn btn-secondary btn-sm" onClick={() => quickP('HL-1010')}>HL-1010</button>
          </div>
          <button className="btn btn-danger btn-sm" disabled={busy}
            onClick={() => run(async () => { await post('/api/demo/reset'); if (user) { await quickRelogin(user, signIn) } }, t('demoResetDone'))}>
            {t('demoReset')}
          </button>
        </div>
      )}
      <button className="demo-toggle" onClick={() => setOpen((o) => !o)} aria-expanded={open}>{t('demoPanel')}</button>
    </div>
  )
}

async function quickRelogin(user, signIn) {
  // After a reset all sessions are gone; sign the same demo user back in when possible.
  try {
    if (user.role === 'participant') {
      const r = await post('/api/auth/participant-login', { code: user.participant_code, pin: '1234' })
      signIn(r.token, r.user)
    } else {
      const r = await post('/api/auth/login', { username: user.username, password: 'demo1234' })
      signIn(r.token, r.user)
    }
  } catch { /* new participant accounts disappear on reset */ }
}

const TIERS = ['Low', 'Average', 'Moderate', 'High']

// Educational long-term risk profile (LLM). Visually separate from the next step and the model band.
export function RiskProfileCard({ rp, staff = false, onRegenerate }) {
  const { t } = useApp()
  if (!rp) return null
  const List = ({ title, items }) => (
    <div>
      <h4 className="mb0" style={{ fontSize: '.9375rem' }}>{title}</h4>
      {items?.length ? <ul className="reasons" style={{ marginTop: 6 }}>{items.map((x, i) => <li key={i}>{x}</li>)}</ul>
        : <div className="muted small">{t('rp_none')}</div>}
    </div>
  )
  return (
    <section className="panel stack" aria-live="polite">
      <div className="panel-head mb0">
        <h3>{staff ? t('rp_title_staff') : t('rp_title')}</h3>
        {rp.status === 'ok' && <RiskSourceBadge rp={rp} />}
      </div>
      {rp.status === 'pending' && <div className="muted">{t('rp_pending')}</div>}
      {!['ok', 'pending'].includes(rp.status) && <div className="note warn small">{t('rp_unavailable')}{staff && rp.error ? ` (${rp.status}: ${rp.error})` : ''}</div>}
      {rp.status === 'ok' && (
        <>
          <div className="band-scale" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
            {TIERS.map((x) => <span key={x} className={rp.estimated_risk_tier === x ? 'on' : ''}>{t('rp_tier_' + x)}</span>)}
          </div>
          <div dir={rp.language === 'ar' ? 'rtl' : 'ltr'} lang={rp.language} className="stack">
            <List title={t('rp_nonmod')} items={rp.non_modifiable_historical_factors} />
            <List title={t('rp_mod')} items={rp.modifiable_lifestyle_factors} />
            <List title={t('rp_recs')} items={rp.clinical_screening_recommendations} />
          </div>
        </>
      )}
      <p className="muted small mb0">{staff ? t('rp_note_staff') : t('rp_note')}</p>
      {staff && (
        <>
          <dl className="kv ltr small">
            <dt>backend</dt><dd>{rp.backend}</dd>
            <dt>model</dt><dd>{rp.model || '—'}</dd>
            <dt>mode</dt><dd>{rp.mode || '—'}</dd>
            <dt>prompt</dt><dd>{rp.prompt_version}</dd>
          </dl>
          {rp.decision && (
            <div className="small">
              <strong>{t('rp_decision')}:</strong>{' '}
              <span className="ltr">tier={rp.decision.tier} (by {rp.decision.source}; rules={rp.decision.rules_tier}
                {rp.decision.jev_tier ? `; jev=${rp.decision.jev_tier}` : ''}{rp.decision.confidence != null ? `; conf=${rp.decision.confidence}` : ''}); text={rp.decision.text_by}</span>
              {rp.from_cache && <div className="muted">{t('rp_cache')}</div>}
              {rp.notes?.map((n, i) => <div key={i} className="muted">{n}</div>)}
            </div>
          )}
          {rp.dropped_items?.length > 0 && <div className="note warn small"><strong>{t('rp_dropped')}:</strong> {rp.dropped_items.join(' | ')}</div>}
          {rp.sent_payload && (
            <details className="small"><summary>{t('rp_sent')}</summary>
              <pre className="ltr" style={{ whiteSpace: 'pre-wrap', fontSize: '.75rem', background: '#f7f9f8', padding: 10, borderRadius: 6 }}>{JSON.stringify(rp.sent_payload, null, 2)}</pre>
            </details>
          )}
          {onRegenerate && <div><button className="btn btn-secondary btn-sm" onClick={onRegenerate}>{t('rp_regen')}</button></div>}
        </>
      )}
    </section>
  )
}

function RiskSourceBadge({ rp }) {
  const { t } = useApp()
  if (rp.is_fixture) return <span className="sim-tag">{t('rp_demo')}</span>
  if (rp.backend !== 'hybrid') return <span className="badge t-blue plain">{t('rp_ai')}</span>
  const jevTier = rp.tier_by === 'jev' || rp.tier_by === 'rules_floor'
  const llm = rp.text_by && rp.text_by !== 'templates'
  const label = jevTier && llm ? t('rp_hybrid_ai') : jevTier ? t('rp_jev') : llm ? t('rp_medgemma') : t('rp_rules')
  return <span className={`badge plain ${jevTier || llm ? 't-blue' : 't-grey'}`}>{label}</span>
}

export function NoteTriage({ tr }) {
  const { t } = useApp()
  if (!tr) return null
  return (
    <div className={`note small ${tr.flag_breast_change ? 'rose' : ''}`}>
      <strong>{t('triage_title')}</strong> <span className="muted ltr">({tr.source}{tr.probability != null ? `, p=${tr.probability.toFixed(2)}` : ''}{tr.barrier ? `, barrier=${tr.barrier}` : ''})</span>
      <div>{tr.flag_breast_change ? t('triage_flag') : t('triage_ok')}</div>
    </div>
  )
}
