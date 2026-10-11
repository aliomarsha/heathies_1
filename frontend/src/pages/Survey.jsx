import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { get, post, put } from '../api.js'
import { ErrorBox, Loading, Shell } from '../components.jsx'
import { useApp } from '../state.jsx'

export function isVisible(q, answers) {
  const c = q.show_if
  if (!c) return true
  const v = answers[c.question]
  const vals = Array.isArray(v) ? v : [v]
  if (c.any_of) return vals.some((x) => c.any_of.includes(x))
  if (c.none_of) return !vals.some((x) => c.none_of.includes(x))
  return true
}

export function answerLabel(q, value, lang, t) {
  if (value === undefined || value === null) return t('unanswered')
  if (q.type === 'number') return value === 'unknown' ? (q.unknown_label?.[lang] || t('notSure')) : `${value} ${t('years')}`
  const vals = Array.isArray(value) ? value : [value]
  return vals.map((v) => q.options.find((o) => o.value === v)?.label[lang] || v).join('، ')
}

function Question({ q, value, onChange, lang, t, showError }) {
  const title = q.title[lang]
  const help = q.help?.[lang]
  const id = `q-${q.id}`
  return (
    <fieldset className="q" aria-describedby={help ? id + '-h' : undefined}>
      <legend className="q-title">{title}</legend>
      {help && <div className="q-help" id={id + '-h'}>{help}</div>}
      {q.type === 'number' && (
        <div className="stack">
          <div className="num-row">
            <input type="number" inputMode="numeric" min={q.min} max={q.max} aria-label={title}
              value={value === 'unknown' || value === undefined ? '' : value}
              disabled={value === 'unknown'}
              onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))} />
            <span className="muted">{t('years')}</span>
          </div>
          <button type="button" className="opt unknown multi" role="checkbox" aria-checked={value === 'unknown'}
            onClick={() => onChange(value === 'unknown' ? null : 'unknown')}>
            <span className="ind" /> {q.unknown_label?.[lang] || t('notSure')}
          </button>
        </div>
      )}
      {q.type === 'single' && (
        <div className="opts" role="radiogroup" aria-label={title}>
          {q.options.map((o) => (
            <button type="button" key={o.value} role="radio" aria-checked={value === o.value}
              className={`opt ${o.value === 'unknown' ? 'unknown' : ''}`} onClick={() => onChange(o.value)}>
              <span className="ind" /> {o.label[lang]}
            </button>
          ))}
        </div>
      )}
      {q.type === 'multi' && (
        <div className="opts" role="group" aria-label={title}>
          {q.options.map((o) => {
            const cur = Array.isArray(value) ? value : []
            const on = cur.includes(o.value)
            const toggle = () => {
              let next
              if (o.exclusive) next = on ? [] : [o.value]
              else {
                const exclusive = q.options.filter((x) => x.exclusive).map((x) => x.value)
                next = on ? cur.filter((v) => v !== o.value) : [...cur.filter((v) => !exclusive.includes(v)), o.value]
              }
              onChange(next.length ? next : null)
            }
            return (
              <button type="button" key={o.value} role="checkbox" aria-checked={on}
                className={`opt multi ${o.exclusive ? 'unknown' : ''}`} onClick={toggle}>
                <span className="ind" /> {o.label[lang]}
              </button>
            )
          })}
        </div>
      )}
      {showError && <div className="q-error" role="alert">{t('required')}</div>}
    </fieldset>
  )
}

function validAnswer(q, v) {
  if (v === undefined || v === null || (Array.isArray(v) && !v.length)) return false
  if (q.type === 'number' && v !== 'unknown') return Number.isFinite(v) && v >= (q.min ?? -Infinity) && v <= (q.max ?? Infinity)
  return true
}

export default function Survey() {
  const { t, lang, notify, bump } = useApp()
  const navigate = useNavigate()
  const [survey, setSurvey] = useState(null)
  const [answers, setAnswers] = useState({})
  const [freeText, setFreeText] = useState('')
  const [step, setStep] = useState(0)
  const [saveState, setSaveState] = useState('')
  const [err, setErr] = useState(null)
  const [tried, setTried] = useState(false)
  const [busy, setBusy] = useState(false)
  const timer = useRef(null)
  const pending = useRef({})

  useEffect(() => {
    Promise.all([get('/api/survey'), get('/api/me/assessment')]).then(([s, a]) => {
      setSurvey(s)
      if (!a.draft) { navigate('/me', { replace: true }); return }
      setAnswers(a.draft.answers || {})
      setFreeText(a.draft.free_text || '')
      setStep(Math.min(a.draft.current_step || 0, s.sections.length + 1))
    }).catch(setErr)
  }, [navigate])

  const flush = useCallback(async (extra = {}) => {
    clearTimeout(timer.current)
    const body = { answers: pending.current, ...extra }
    pending.current = {}
    setSaveState('saving')
    try { await put('/api/me/assessment', body); setSaveState('saved') } catch (e) { setSaveState(''); setErr(e) }
  }, [])

  const setAnswer = (qid, v) => {
    setAnswers((a) => {
      const next = { ...a }
      if (v === null) delete next[qid]; else next[qid] = v
      return next
    })
    pending.current[qid] = v
    clearTimeout(timer.current)
    timer.current = setTimeout(() => flush(), 700)
  }

  const sections = survey?.sections || []
  const totalSteps = sections.length + 2 // + free text + review
  const visibleQs = (sec) => sec.questions.filter((q) => isVisible(q, answers))
  const missingIn = (sec) => visibleQs(sec).filter((q) => q.required && !validAnswer(q, answers[q.id]))

  const go = async (to) => {
    if (to > step && step < sections.length && missingIn(sections[step]).length) { setTried(true); return }
    setTried(false)
    setStep(to)
    window.scrollTo({ top: 0 })
    await flush({ current_step: to, ...(step === sections.length ? { free_text: freeText } : {}) })
  }

  const submit = async () => {
    const firstMissing = sections.findIndex((s) => missingIn(s).length)
    if (firstMissing >= 0) { setStep(firstMissing); setTried(true); return }
    setBusy(true)
    setErr(null)
    try {
      await flush({ free_text: freeText, current_step: step })
      await post('/api/me/assessment/submit')
      bump()
      navigate('/me#next-step')
    } catch (e) {
      setErr(e)
      if (e.detail?.missing) notify(t('required'), 'err')
    } finally { setBusy(false) }
  }

  const progress = useMemo(() => Math.round((step / (totalSteps - 1)) * 100), [step, totalSteps])

  if (!survey) return <Shell narrow>{err ? <ErrorBox error={err} /> : <Loading />}</Shell>

  const sec = sections[step]
  return (
    <Shell narrow>
      <div className="stack">
        <div className="row">
          <strong>{t('surveyTitle')}</strong>
          <span className="muted small">{t('stepOf', step + 1, totalSteps)}</span>
          <span className="spacer" />
          <span className="save-state" aria-live="polite">{saveState === 'saving' ? t('saving') : saveState === 'saved' ? t('savedDraft') : ''}</span>
        </div>
        <div className="progress" aria-hidden="true"><span style={{ width: `${progress}%` }} /></div>

        <div className="panel panel-l">
          {sec && (
            <>
              <h1 style={{ fontSize: '1.625rem' }}>{sec.title[lang]}</h1>
              {sec.intro && <p className="muted">{sec.intro[lang]}</p>}
              <div className="mt">
                {visibleQs(sec).map((q) => (
                  <Question key={q.id} q={q} value={answers[q.id]} lang={lang} t={t}
                    onChange={(v) => setAnswer(q.id, v)} showError={tried && q.required && !validAnswer(q, answers[q.id])} />
                ))}
              </div>
            </>
          )}
          {step === sections.length && (
            <>
              <h1 style={{ fontSize: '1.625rem' }}>{survey.free_text.title[lang]}</h1>
              <p className="muted">{survey.free_text.help[lang]}</p>
              <label className="field"><span className="sr-only">{survey.free_text.title[lang]}</span>
                <textarea value={freeText} maxLength={2000} onChange={(e) => setFreeText(e.target.value)} rows={5} />
              </label>
            </>
          )}
          {step === sections.length + 1 && (
            <>
              <h1 style={{ fontSize: '1.625rem' }}>{t('reviewTitle')}</h1>
              <p className="muted">{t('reviewLead')}</p>
              {sections.map((s, si) => (
                <div key={s.id} className="mt">
                  <div className="row"><h3 className="mb0">{s.title[lang]}</h3><span className="spacer" />
                    <button className="btn btn-ghost btn-sm" onClick={() => go(si)}>{t('edit')}</button></div>
                  {visibleQs(s).map((q) => (
                    <div className="review-row" key={q.id}>
                      <div className="review-q">{q.title[lang]}</div>
                      <div className={`review-a ${answers[q.id] === undefined ? 'muted' : ''}`}>{answerLabel(q, answers[q.id], lang, t)}</div>
                    </div>
                  ))}
                </div>
              ))}
              {freeText && <div className="note mt">{freeText}</div>}
            </>
          )}
        </div>

        <ErrorBox error={err} />
        <div className="btn-row">
          {step > 0 && <button className="btn btn-secondary" onClick={() => go(step - 1)}>{t('back')}</button>}
          <span className="spacer" />
          {step < totalSteps - 1
            ? <button className="btn btn-primary" onClick={() => go(step + 1)}>{t('next')}</button>
            : <button className="btn btn-primary" onClick={submit} disabled={busy}>{busy ? t('submitting') : t('submit')}</button>}
        </div>
        <p className="muted small">{t('provisional')}</p>
      </div>
    </Shell>
  )
}
