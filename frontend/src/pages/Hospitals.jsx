import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { post } from '../api.js'
import { ErrorBox, Loading, Shell } from '../components.jsx'
import { useApp, useLoad } from '../state.jsx'

function RequestForm({ h, replaceId, onDone }) {
  const { t } = useApp()
  const [date, setDate] = useState('')
  const [time, setTime] = useState('morning')
  const [note, setNote] = useState('')
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const send = async () => {
    setBusy(true); setErr(null)
    try {
      if (replaceId) await post(`/api/me/appointments/${replaceId}/reschedule`, { hospital_id: h.id, preferred_date: date || null, preferred_time: time, note })
      else await post('/api/me/appointments', { hospital_id: h.id, preferred_date: date || null, preferred_time: time, note })
      onDone()
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }
  return (
    <div className="stack" style={{ borderTop: '1px solid var(--line-2)', paddingTop: 14 }}>
      <div className="grid-2">
        <label className="field">{t('preferredDate')}<input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>
        <label className="field">{t('preferredTime')}
          <select value={time} onChange={(e) => setTime(e.target.value)}>{['morning', 'afternoon', 'any'].map((v) => <option key={v} value={v}>{t('time_' + v)}</option>)}</select>
        </label>
      </div>
      <label className="field">{t('noteToHospital')} <span className="field-help">{t('optional')}</span>
        <input type="text" value={note} onChange={(e) => setNote(e.target.value)} maxLength={300} />
      </label>
      <ErrorBox error={err} />
      <div><button className="btn btn-primary" onClick={send} disabled={busy}>{t('sendRequest')}</button></div>
    </div>
  )
}

export default function Hospitals() {
  const { t, lang, notify, bump } = useApp()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const replaceId = params.get('replace')
  const { data: o } = useLoad('/api/me/overview')
  const gov = o?.latest_assessment?.answers?.q_governorate || o?.participant?.governorate || ''
  const service = o?.recommendation?.service
  const { data: list, error } = useLoad(o ? `/api/hospitals?governorate=${gov}` : null, [gov])
  const [open, setOpen] = useState(null)

  if (!o || !list) return <Shell narrow>{error ? <ErrorBox error={error} /> : <Loading />}</Shell>
  const needed = service && !['none', 'clarification_call'].includes(service) ? service : 'screening_mammogram'

  return (
    <Shell narrow>
      <div className="stack">
        <button className="btn btn-ghost btn-sm" style={{ justifySelf: 'start' }} onClick={() => navigate('/me')}>{t('back')}</button>
        <h1>{t('hospitalsTitle')}</h1>
        <p className="muted">{t('hospitalsLead')}</p>
        <div className="note"><strong>{t('serviceLabel')}:</strong> {t('service_' + needed)}</div>
        {list.map((h) => {
          const offers = h.services.includes(needed)
          return (
            <article className="panel hosp" key={h.id} style={!offers ? { opacity: .6 } : undefined}>
              <div className="hosp-top">
                <div>
                  <div className="hosp-name">{lang === 'ar' ? h.name_ar : h.name_en}</div>
                  <div className="muted small">{t('sector_' + h.sector)}{h.district ? `, ${h.district}` : ''}</div>
                </div>
                <div className="chips">
                  {h.near && <span className="badge t-green">{t('near')}</span>}
                  {!h.info_verified && <span className="badge t-outline plain">{t('infoUnverified')}</span>}
                </div>
              </div>
              <div className="chips">{h.services.map((s) => <span key={s} className={`badge plain ${s === needed ? 't-green' : 't-grey'}`}>{t('service_' + s)}</span>)}</div>
              <div className="small ink2">{t('cost_' + h.cost_status)}</div>
              {h.demo_slots?.length > 0 && (
                <div className="row small"><span className="sim-tag">{t('simulatedSlots')}</span>
                  <div className="slots ltr">{h.demo_slots.map((s) => <span className="slot" key={s}>{s}</span>)}</div></div>
              )}
              {offers ? (
                open === h.id
                  ? <RequestForm h={h} replaceId={replaceId} onDone={() => { notify(t('requestSent')); bump(); navigate('/me') }} />
                  : <div><button className="btn btn-secondary" onClick={() => setOpen(h.id)}>{t('requestHere')}</button></div>
              ) : <div className="muted small">{t('notOffered')}</div>}
            </article>
          )
        })}
      </div>
    </Shell>
  )
}
