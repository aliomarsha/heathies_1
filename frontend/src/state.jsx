import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { get, post, session } from './api.js'
import { translator } from './i18n.js'

const Ctx = createContext(null)

function initialLang() {
  try { return localStorage.getItem('healthies.lang') || 'ar' } catch { return 'ar' }
}

export function AppProvider({ children }) {
  const [lang, setLangState] = useState(initialLang)
  const [user, setUser] = useState(session.user)
  const [meta, setMeta] = useState(null)
  const [toast, setToast] = useState(null)
  const [dataVersion, setDataVersion] = useState(0)

  const setLang = useCallback((l) => {
    setLangState(l)
    try { localStorage.setItem('healthies.lang', l) } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    document.documentElement.lang = lang
    document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr'
  }, [lang])

  const refreshMeta = useCallback(() => get('/api/meta').then(setMeta).catch(() => {}), [])
  useEffect(() => { refreshMeta() }, [refreshMeta, dataVersion])

  useEffect(() => {
    const h = () => setUser(null)
    window.addEventListener('healthies:signedout', h)
    return () => window.removeEventListener('healthies:signedout', h)
  }, [])

  const signIn = useCallback((token, u) => {
    session.set(token, u)
    setUser(u)
    if (u.language) setLang(u.language)
  }, [setLang])

  const signOut = useCallback(async () => {
    try { await post('/api/auth/logout') } catch { /* ignore */ }
    session.clear()
    setUser(null)
  }, [])

  const notify = useCallback((msg, kind = 'ok') => {
    setToast({ msg, kind, id: Date.now() })
    setTimeout(() => setToast((t) => (t && Date.now() - t.id > 3500 ? null : t)), 4000)
  }, [])

  const bump = useCallback(() => setDataVersion((v) => v + 1), [])

  const value = useMemo(() => ({
    lang, setLang, t: translator(lang), user, signIn, signOut, meta, refreshMeta, toast, notify, dataVersion, bump,
  }), [lang, setLang, user, signIn, signOut, meta, refreshMeta, toast, notify, dataVersion, bump])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export const useApp = () => useContext(Ctx)

// Load data from the API and reload whenever demo data changes.
export function useLoad(path, deps = []) {
  const { dataVersion } = useApp()
  const [state, setState] = useState({ data: null, error: null, loading: true })
  const load = useCallback(() => {
    if (!path) return
    setState((s) => ({ ...s, loading: true }))
    get(path).then((data) => setState({ data, error: null, loading: false }))
      .catch((error) => setState({ data: null, error, loading: false }))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, dataVersion, ...deps])
  useEffect(() => { load() }, [load])
  return { ...state, reload: load, setData: (data) => setState((s) => ({ ...s, data })) }
}
