import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { post } from '../api.js'
import { ErrorBox, Shell } from '../components.jsx'
import { useApp } from '../state.jsx'

export function Landing() {
  const { t, user } = useApp()
  const home = user ? (user.role === 'participant' ? '/me' : user.role === 'provider' ? '/provider' : '/programme') : null
  return (
    <Shell>
      <section className="hero">
        <div>
          <h1>{t('landingTitle')}</h1>
          <p className="lead">{t('landingLead')}</p>
          <div className="btn-row mt">
            {home ? (
              <Link className="btn btn-primary" to={home}>{t('continueAssessment')}</Link>
            ) : (
              <>
                <Link className="btn btn-primary" to="/start">{t('startAssessment')}</Link>
                <Link className="btn btn-secondary" to="/resume">{t('resume')}</Link>
              </>
            )}
          </div>
          <p className="muted small mt">{t('helpLine')}</p>
        </div>
        <div className="panel panel-l">
          <h2 className="mb">{t('howItWorks')}</h2>
          <div className="pathway">
            {[1, 2, 3, 4].map((n) => (
              <div className="pathway-step" key={n}>
                <span className="pathway-num">{n}</span>
                <div>
                  <h3>{t('how' + n + 't')}</h3>
                  <p>{t('how' + n)}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>
      <section className="entry-grid">
        <div className="panel">
          <h3>{t('staffEntry')}</h3>
          <p className="muted">{t('staffEntryLead')}</p>
          <Link className="btn btn-secondary btn-sm" to="/staff">{t('signIn')}</Link>
        </div>
        <div className="note warn">{t('notEmergency')}</div>
      </section>
    </Shell>
  )
}

export function Enrol() {
  const { t, lang, setLang, signIn } = useApp()
  const navigate = useNavigate()
  const [consent, setConsent] = useState(false)
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [channel, setChannel] = useState('sms')
  const [time, setTime] = useState('any')
  const [discreet, setDiscreet] = useState(true)
  const [voicemail, setVoicemail] = useState(false)
  const [pin, setPin] = useState('')
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [code, setCode] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    setErr(null)
    if (!consent) return setErr({ message: t('consentCheck') })
    if (!/^\d{4,8}$/.test(pin)) return setErr({ message: t('pinTitle') })
    setBusy(true)
    try {
      const r = await post('/api/auth/enroll', {
        language: lang, display_name: name, consent: true,
        contact: { channel, time, discreet_messages: discreet, safe_to_leave_message: voicemail, phone }, pin,
      })
      signIn(r.token, r.user)
      setCode(r.code)
    } catch (ex) { setErr(ex) } finally { setBusy(false) }
  }

  if (code) {
    return (
      <Shell narrow>
        <div className="panel panel-l stack">
          <h1>{t('yourCode')}</h1>
          <div className="code-big">{code}</div>
          <p>{t('yourCodeHelp')}</p>
          <button className="btn btn-primary" onClick={() => navigate('/me/assessment')}>{t('gotIt')}</button>
        </div>
      </Shell>
    )
  }

  return (
    <Shell narrow>
      <form className="stack-l" onSubmit={submit}>
        <h1>{t('enrolTitle')}</h1>
        <section className="panel stack">
          <h2>{t('chooseLanguage')}</h2>
          <div className="seg" role="group">
            <button type="button" aria-pressed={lang === 'ar'} onClick={() => setLang('ar')} lang="ar">العربية</button>
            <button type="button" aria-pressed={lang === 'en'} onClick={() => setLang('en')} lang="en">English</button>
          </div>
        </section>
        <section className="panel stack">
          <h2>{t('consentTitle')}</h2>
          <p className="ink2 mb0">{t('consentBody')}</p>
          <label className="check"><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} /> <span>{t('consentCheck')}</span></label>
        </section>
        <section className="panel stack">
          <h2>{t('contactTitle')}</h2>
          <p className="muted mb0">{t('contactLead')}</p>
          <label className="field">{t('nameLabel')}<span className="field-help">{t('nameHelp')}</span>
            <input type="text" value={name} onChange={(e) => setName(e.target.value)} autoComplete="off" maxLength={60} />
          </label>
          <div className="opts" role="radiogroup" aria-label={t('contactTitle')}>
            {['sms', 'call', 'none'].map((c) => (
              <button type="button" key={c} className="opt" role="radio" aria-checked={channel === c} onClick={() => setChannel(c)}>
                <span className="ind" /> {t('channel_' + c)}
              </button>
            ))}
          </div>
          {channel !== 'none' && (
            <>
              <label className="field">{t('phoneLabel')}<span className="field-help">{t('phoneHelp')}</span>
                <input type="tel" className="ltr" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+961 70 000 000" />
              </label>
              <label className="field">{t('timeLabel')}
                <select value={time} onChange={(e) => setTime(e.target.value)}>
                  {['any', 'morning', 'afternoon', 'evening'].map((v) => <option key={v} value={v}>{t('time_' + v)}</option>)}
                </select>
              </label>
              <label className="check"><input type="checkbox" checked={discreet} onChange={(e) => setDiscreet(e.target.checked)} /> <span>{t('discreet')}</span></label>
              {channel === 'call' && <label className="check"><input type="checkbox" checked={voicemail} onChange={(e) => setVoicemail(e.target.checked)} /> <span>{t('leaveMessage')}</span></label>}
            </>
          )}
        </section>
        <section className="panel stack">
          <h2>{t('pinTitle')}</h2>
          <p className="muted mb0">{t('pinHelp')}</p>
          <label className="field">{t('pinLabel')}
            <input type="password" inputMode="numeric" className="ltr" value={pin} maxLength={8} onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))} style={{ maxWidth: 180 }} />
          </label>
        </section>
        <ErrorBox error={err} />
        <button className="btn btn-primary" disabled={busy}>{t('createAccount')}</button>
      </form>
    </Shell>
  )
}

export function Resume() {
  const { t, signIn } = useApp()
  const navigate = useNavigate()
  const [code, setCode] = useState('')
  const [pin, setPin] = useState('')
  const [err, setErr] = useState(null)
  const submit = async (e) => {
    e.preventDefault()
    setErr(null)
    try {
      const r = await post('/api/auth/participant-login', { code, pin })
      signIn(r.token, r.user)
      navigate('/me')
    } catch (ex) { setErr(ex) }
  }
  return (
    <Shell narrow>
      <form className="panel panel-l stack" onSubmit={submit}>
        <h1>{t('resumeTitle')}</h1>
        <label className="field">{t('codeLabel')}
          <input type="text" className="ltr" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="HL-0000" autoComplete="username" />
        </label>
        <label className="field">{t('pinLabel')}
          <input type="password" inputMode="numeric" className="ltr" value={pin} onChange={(e) => setPin(e.target.value)} autoComplete="current-password" />
        </label>
        <ErrorBox error={err} />
        <button className="btn btn-primary">{t('signIn')}</button>
        <p className="muted small mb0">{t('demoHint')}</p>
      </form>
    </Shell>
  )
}

export function StaffLogin() {
  const { t, signIn } = useApp()
  const navigate = useNavigate()
  const [u, setU] = useState('')
  const [p, setP] = useState('')
  const [err, setErr] = useState(null)
  const submit = async (e) => {
    e.preventDefault()
    setErr(null)
    try {
      const r = await post('/api/auth/login', { username: u, password: p })
      signIn(r.token, r.user)
      navigate(r.user.role === 'provider' ? '/provider' : '/programme')
    } catch (ex) { setErr(ex) }
  }
  return (
    <Shell narrow>
      <form className="panel panel-l stack" onSubmit={submit}>
        <h1>{t('staffTitle')}</h1>
        <label className="field">{t('username')}<input type="text" className="ltr" value={u} onChange={(e) => setU(e.target.value)} autoComplete="username" /></label>
        <label className="field">{t('password')}<input type="password" className="ltr" value={p} onChange={(e) => setP(e.target.value)} autoComplete="current-password" /></label>
        <ErrorBox error={err} />
        <button className="btn btn-primary">{t('signIn')}</button>
        <p className="muted small mb0 ltr">{t('staffDemo')}</p>
      </form>
    </Shell>
  )
}
