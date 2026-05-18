import { useState, useEffect, useRef, useCallback } from "react"

const translations = {
  fr: {
    journal: "Journal",
    settings: "Paramètres",
    stats: "Statistiques",
    digest: "Digest",
    dreamMap: "Carte des rêves",
    noEntries: "Aucun rêve enregistré",
    loading: "Chargement...",
    transcribing: "Transcription en cours...",
    fuzzy: "Transcription approximative",
    raw: "Brut",
    corrected: "Corrigé",
    correct: "Corriger",
    notTranscribed: "En attente de transcription",
    error: "Erreur de connexion à Sandman",
    retry: "Réessayer",
    sandmanStatus: "Sandman",
    connected: "Connecté",
    disconnected: "Déconnecté",
    vocabulary: "Vocabulaire",
    vocabularyHint: "Noms, lieux, mots récurrents séparés par des virgules",
    save: "Sauvegarder",
    saved: "Sauvegardé",
    language: "Langue",
    tags: "Tags",
    addTag: "Ajouter un tag",
    tagPlaceholder: "lucide, cauchemar, récurrent...",
    totalEntries: "Rêves enregistrés",
    avgLength: "Longueur moyenne",
    avgPerMonth: "Rêves par mois",
    topTags: "Tags les plus utilisés",
    topTags30: "Tags des 30 derniers jours",
    topWords: "Mots récurrents",
    monthlyChart: "Entrées par mois",
    noStats: "Pas encore assez de données",
    weeklyDigest: "Digest hebdo",
    noDigest: "Pas assez de rêves sur la période",
    nightmareEntries: "Cauchemars",
    tensionLevel: "Niveau de tension",
    highlights: "Extraits récents",
    previousWeek: "Semaine précédente",
    nextWeek: "Semaine suivante",
    currentWeek: "Semaine en cours",
    askSummary: "Demander un résumé",
    forceSummary: "Forcer la réinterprétation",
    confirmForceSummary: "Cela va regénérer le résumé de la semaine. Continuer ?",
    cancelGeneration: "Annuler la génération",
    pendingLongHint: "Toujours en cours ({seconds}s).",
    generatedIn: "généré en",
    summaryTitle: "Résumé Mistral",
    summaryLoading: "Mistral réfléchit…",
    summaryWeekNotReady: "La semaine n'est pas terminée. Reviens plus tard.",
    noMapData: "Pas assez de données pour la carte",
    semanticGroups: "Groupes sémantiques",
    zoomIn: "Zoom +",
    zoomOut: "Zoom -",
    resetView: "Recentrer",
    resetDreamMap: "Réinitialiser la carte",
    confirmResetDreamMap: "Cela va vider les groupes sémantiques et reclasser tous les mots-clés. Continuer ?",
    resettingDreamMap: "Réinitialisation…",
    thinking: "analyse…",
    ungrouped: "hors groupe",
    noTags: "Aucun tag utilisé",
    interpret: "Interpréter",
    forceInterpret: "Forcer la réinterprétation",
    confirmForceInterpret: "Cela va regénérer cette interprétation. Continuer ?",
    interpreting: "Interprétation en cours…",
    interpretations: "Interprétations",
    chooseInterpreter: "Choisir un interprète",
    dreamDate: "Date du rêve",
    dreamDateHint: "Quand ce rêve a eu lieu",
    editDate: "Modifier la date",
    saveDate: "Enregistrer la date",
    cancel: "Annuler",
    theme: "Thème",
    auto: "Auto",
    light: "Clair",
    dark: "Sombre",
    help: "Aide",
    openHelp: "Ouvrir l'aide",
    close: "Fermer",
    userProfile: "Profil utilisateur",
    firstName: "Prénom",
    lastName: "Nom",
    pronouns: "Pronoms",
    birthday: "Date de naissance",
    pet: "Animal de compagnie",
    closestRelative: "Proche le plus important",
    relativeStatus: "Statut de ce proche",
    otherNotes: "Autres informations utiles",
    pronounsHint: "ex: elle, il, iel, they/them",
    profileHint: "Ces informations guident Mistral pour les interprétations et digest.",
  },
  en: {
    journal: "Journal",
    settings: "Settings",
    stats: "Statistics",
    digest: "Digest",
    dreamMap: "Dream map",
    noEntries: "No dreams recorded yet",
    loading: "Loading...",
    transcribing: "Transcribing...",
    fuzzy: "Approximate transcription",
    raw: "Raw",
    corrected: "Corrected",
    correct: "Correct",
    notTranscribed: "Awaiting transcription",
    error: "Cannot connect to Sandman",
    retry: "Retry",
    sandmanStatus: "Sandman",
    connected: "Connected",
    disconnected: "Disconnected",
    vocabulary: "Vocabulary",
    vocabularyHint: "Names, places, recurring words separated by commas",
    save: "Save",
    saved: "Saved",
    language: "Language",
    tags: "Tags",
    addTag: "Add tag",
    tagPlaceholder: "lucid, nightmare, recurring...",
    totalEntries: "Dreams recorded",
    avgLength: "Average length",
    avgPerMonth: "Dreams per month",
    topTags: "Most used tags",
    topTags30: "Tags last 30 days",
    topWords: "Recurring words",
    monthlyChart: "Entries per month",
    noStats: "Not enough data yet",
    weeklyDigest: "Weekly digest",
    noDigest: "Not enough dreams in this period",
    nightmareEntries: "Nightmares",
    tensionLevel: "Tension level",
    highlights: "Recent highlights",
    previousWeek: "Previous week",
    nextWeek: "Next week",
    currentWeek: "Current week",
    askSummary: "Ask for summary",
    forceSummary: "Force reinterpretation",
    confirmForceSummary: "This will regenerate the weekly summary. Continue?",
    cancelGeneration: "Cancel generation",
    pendingLongHint: "Still running ({seconds}s).",
    generatedIn: "generated in",
    summaryTitle: "Mistral summary",
    summaryLoading: "Mistral is thinking…",
    summaryWeekNotReady: "The week is not over yet. Come back later.",
    noMapData: "Not enough data for the map",
    semanticGroups: "Semantic groups",
    zoomIn: "Zoom +",
    zoomOut: "Zoom -",
    resetView: "Reset view",
    resetDreamMap: "Reset dream map",
    confirmResetDreamMap: "This will clear semantic groups and re-sort all keywords. Continue?",
    resettingDreamMap: "Resetting…",
    thinking: "thinking…",
    ungrouped: "ungrouped",
    noTags: "No tags used yet",
    interpret: "Interpret",
    forceInterpret: "Force reinterpretation",
    confirmForceInterpret: "This will regenerate this interpretation. Continue?",
    interpreting: "Interpreting…",
    interpretations: "Interpretations",
    chooseInterpreter: "Choose an interpreter",
    dreamDate: "Dream date",
    dreamDateHint: "When this dream happened",
    editDate: "Edit date",
    saveDate: "Save date",
    cancel: "Cancel",
    theme: "Theme",
    auto: "Auto",
    light: "Light",
    dark: "Dark",
    help: "Help",
    openHelp: "Open help",
    close: "Close",
    userProfile: "User profile",
    firstName: "First name",
    lastName: "Last name",
    pronouns: "Pronouns",
    birthday: "Birthday",
    pet: "Pet",
    closestRelative: "Closest relative",
    relativeStatus: "Relative status",
    otherNotes: "Other relevant notes",
    pronounsHint: "e.g. she/her, he/him, they/them",
    profileHint: "This information is used by Mistral for interpretations and digest.",
  }
}

const INTERPRETERS = {
  fool:      { emoji: "🃏", name: { fr: "Le Fou",    en: "The Fool"   }, style: { fr: "humouristique, moqueur", en: "humorous, teasing"   } },
  freud:     { emoji: "🔬", name: { fr: "Sigmund",   en: "Sigmund"    }, style: { fr: "sérieux, analytique",    en: "serious, analytical" } },
  cassandra: { emoji: "🌙", name: { fr: "Cassandre", en: "Cassandra"  }, style: { fr: "mystique, symbolisme",   en: "mystic, symbolic"    } },
  oracle:    { emoji: "🌿", name: { fr: "L'Oracle",  en: "The Oracle" }, style: { fr: "bienveillant, poétique", en: "warm, poetic"         } },
}

const API_BASE = `https://${window.location.hostname}:8765`
const DEFAULT_API_KEY = "dream"

function getApiKey() {
  const raw = (localStorage.getItem("api_key") || "").trim()
  if (!raw) return DEFAULT_API_KEY
  const lowered = raw.toLowerCase()
  if (lowered === "null" || lowered === "undefined" || lowered === "none") {
    return DEFAULT_API_KEY
  }
  return raw
}

async function apiFetch(path, options = {}) {
  const requestOptions = {
    ...options,
    headers: {
      "X-API-Key": getApiKey(),
      "Content-Type": "application/json",
      ...options.headers,
    }
  }

  let res = await fetch(`${API_BASE}${path}`, requestOptions)

  // Some iOS/PWA storage contexts intermittently return stale API key values.
  // If we get 403, retry once with the known default key and heal localStorage.
  if (res.status === 403 && getApiKey() !== DEFAULT_API_KEY) {
    res = await fetch(`${API_BASE}${path}`, {
      ...requestOptions,
      headers: {
        ...requestOptions.headers,
        "X-API-Key": DEFAULT_API_KEY,
      }
    })
    if (res.ok) {
      localStorage.setItem("api_key", DEFAULT_API_KEY)
    }
  }

  if (!res.ok) {
    if (res.status === 403) throw new Error("AUTH_403")
    throw new Error(`API error ${res.status}`)
  }
  return res.json()
}

function formatTimestamp(ts) {
  if (!ts) return {}
  const [date, time] = ts.split("_")
  if (!date || !time) return { date: ts, month: 0, time: "" }
  const [y, m, d] = date.split("-")
  return { date: `${d}`, month: parseInt(m) - 1, time: time.replace("h", ":") }
}

function toDateTimeLocalValue(date = new Date()) {
  const pad = n => String(n).padStart(2, "0")
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function entryDateToInputValue(entry) {
  const source = entry?.dream_date || entry?.received_at || null
  if (source) {
    const dt = new Date(source)
    if (!Number.isNaN(dt.getTime())) return toDateTimeLocalValue(dt)
  }

  const ts = entry?.timestamp || ""
  const m = ts.match(/^(\d{4})-(\d{2})-(\d{2})_(\d{2})h(\d{2})$/)
  if (m) return `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}`

  return toDateTimeLocalValue()
}

function formatEntryDate(entry) {
  const source = entry?.dream_date || entry?.received_at || null
  if (source) {
    const dt = new Date(source)
    if (!Number.isNaN(dt.getTime())) {
      const pad = n => String(n).padStart(2, "0")
      return {
        date: String(dt.getDate()),
        month: dt.getMonth(),
        time: `${pad(dt.getHours())}:${pad(dt.getMinutes())}`,
      }
    }
  }
  return formatTimestamp(entry?.timestamp)
}

function formatDuration(seconds) {
  if (!seconds) return null
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return m > 0 ? `${m}m ${s}s` : `${s}s`
}

function StatusDot({ online }) {
  return (
    <span className={`inline-block w-2 h-2 rounded-full mr-2 ${online ? "bg-emerald-400" : "bg-red-400"}`}
      style={{ boxShadow: online ? "0 0 6px #34d399" : "0 0 6px #f87171" }} />
  )
}

// ── EntryCard ─────────────────────────────────────────────────────────────────
function EntryCard({ entry, onClick, lang }) {
  const t = translations[lang]
  const ts = formatEntryDate(entry)
  const monthNames = {
    fr: ["jan","fév","mar","avr","mai","jun","jul","aoû","sep","oct","nov","déc"],
    en: ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"]
  }
  const preview = entry.transcript_preview || null
  const previewText = preview ? preview.slice(0, 120) + (preview.length > 120 ? "…" : "") : null

  return (
    <button onClick={onClick} className="w-full text-left group">
      <div className="flex gap-4 py-5 border-b border-white/5 hover:border-white/10 transition-colors">
        <div className="flex-shrink-0 w-12 text-center">
          <div className="text-2xl font-light leading-none" style={{ fontFamily: "'Playfair Display', Georgia, serif", color: "var(--accent)" }}>{ts.date}</div>
          <div className="text-xs uppercase tracking-widest mt-1 opacity-40">{monthNames[lang]?.[ts.month]}</div>
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className="text-sm opacity-50">{ts.time}</span>
            {entry.fuzzy && <span className="text-xs px-2 py-0.5 rounded-full bg-amber-400/10 text-amber-400">⚠ {t.fuzzy}</span>}
            {!entry.transcribed && <span className="text-xs px-2 py-0.5 rounded-full bg-blue-400/10 text-blue-400 animate-pulse">◌ {t.transcribing}</span>}
            {entry.interpretation_pending && <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-400/10 text-emerald-300 animate-pulse">◌ {t.interpreting}</span>}
            {entry.tags && entry.tags.slice(0, 3).map(tag => (
              <span key={tag} className="text-xs px-2 py-0.5 rounded-full border border-white/10 opacity-50">{tag}</span>
            ))}
          </div>
          {previewText ? (
            <p className="text-sm leading-relaxed opacity-70 line-clamp-2 group-hover:opacity-90 transition-opacity">{previewText}</p>
          ) : !entry.transcribed ? (
            <p className="text-sm opacity-30 italic">{t.notTranscribed}</p>
          ) : null}
          {entry.duration_seconds > 0 && <div className="text-xs opacity-30 mt-2">{formatDuration(entry.duration_seconds)}</div>}
        </div>
        <div className="flex-shrink-0 opacity-20 group-hover:opacity-50 transition-opacity self-center">→</div>
      </div>
    </button>
  )
}

// ── TagEditor ─────────────────────────────────────────────────────────────────
const PRESET_TAGS = {
  fr: ["lucide", "cauchemar", "récurrent", "étrange", "positif", "négatif", "vol", "chute", "eau", "personnes"],
  en: ["lucid", "nightmare", "recurring", "strange", "positive", "negative", "flying", "falling", "water", "people"]
}

function TagEditor({ entry, lang }) {
  const t = translations[lang]
  const [tags, setTags] = useState(entry.tags || [])
  const [adding, setAdding] = useState(false)
  const [input, setInput] = useState("")

  async function saveTags(newTags) {
    setTags(newTags)
    await apiFetch(`/entries/${entry.timestamp}/tags`, { method: "POST", body: JSON.stringify({ tags: newTags }) })
  }

  function toggleTag(tag) {
    saveTags(tags.includes(tag) ? tags.filter(t => t !== tag) : [...tags, tag])
  }

  async function addCustomTag() {
    const tag = input.trim().toLowerCase()
    if (!tag || tags.includes(tag)) { setInput(""); setAdding(false); return }
    await saveTags([...tags, tag])
    setInput(""); setAdding(false)
  }

  return (
    <div className="mt-6 px-6 pb-4">
      <div className="text-xs uppercase tracking-widest opacity-40 mb-3">{t.tags}</div>
      <div className="flex flex-wrap gap-2">
        {PRESET_TAGS[lang].map(tag => (
          <button key={tag} onClick={() => toggleTag(tag)}
            className={`px-3 py-1 rounded-full text-xs border transition-colors ${tags.includes(tag) ? "border-[var(--accent)] text-[var(--accent)] bg-[var(--accent)]/10" : "border-white/10 opacity-50 hover:opacity-80"}`}>
            {tag}
          </button>
        ))}
        {tags.filter(tag => !PRESET_TAGS[lang].includes(tag)).map(tag => (
          <button key={tag} onClick={() => toggleTag(tag)}
            className="px-3 py-1 rounded-full text-xs border border-[var(--accent)] text-[var(--accent)] bg-[var(--accent)]/10">
            {tag} ×
          </button>
        ))}
        {adding ? (
          <div className="flex gap-1">
            <input autoFocus value={input} onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter") addCustomTag() }}
              className="bg-white/5 border border-white/10 rounded-full px-3 py-1 text-xs focus:outline-none focus:border-white/20 w-28"
              placeholder={t.tagPlaceholder.split(",")[0].trim() + "..."} />
            <button onClick={addCustomTag} className="px-3 py-1 rounded-full text-xs border border-white/20">+</button>
          </div>
        ) : (
          <button onClick={() => setAdding(true)}
            className="px-3 py-1 rounded-full text-xs border border-white/10 opacity-40 hover:opacity-80 transition-opacity">
            + {t.addTag}
          </button>
        )}
      </div>
    </div>
  )
}

// ── InterpretationPanel ───────────────────────────────────────────────────────
function InterpretationPanel({ entry, lang }) {
  const t = translations[lang]
  const [interpretations, setInterpretations] = useState({})
  const [pending, setPending] = useState({})
  const [pendingSeconds, setPendingSeconds] = useState({})
  const [errorMsg, setErrorMsg] = useState("")
  const [showPicker, setShowPicker] = useState(false)

  const hasPending = Object.values(pending).some(Boolean)

  function formatGenerationSeconds(seconds) {
    const n = Number(seconds)
    if (!Number.isFinite(n) || n < 0) return ""
    if (n < 1) return `${Math.round(n * 1000)} ms`
    return `${n.toFixed(1)} s`
  }

  const refreshInterpretationState = useCallback(async (focusKey = null) => {
    const [interps, status] = await Promise.all([
      apiFetch(`/entries/${entry.timestamp}/interpretations`),
      apiFetch(`/entries/${entry.timestamp}/interpret-status`),
    ])

    setInterpretations(interps || {})

    const nextPending = {}
    const nextPendingSeconds = {}
    let statusError = ""
    Object.entries(status || {}).forEach(([key, value]) => {
      nextPending[key] = !!value?.pending
      nextPendingSeconds[key] = Number(value?.pending_seconds)
      if (value?.error && (!focusKey || key === focusKey)) {
        statusError = value.error
      }
    })
    setPending(nextPending)
    setPendingSeconds(nextPendingSeconds)
    if (statusError) setErrorMsg(statusError)
  }, [entry.timestamp])

  useEffect(() => {
    setErrorMsg("")
    setInterpretations({})
    setPending({})
    setPendingSeconds({})
    refreshInterpretationState().catch(() => {})
  }, [entry.timestamp, refreshInterpretationState])

  async function cancelInterpretation(key) {
    try {
      await apiFetch(`/entries/${entry.timestamp}/interpret/cancel`, {
        method: "POST",
        body: JSON.stringify({ interpreter: key })
      })
      setPending(prev => ({ ...prev, [key]: false }))
      setPendingSeconds(prev => ({ ...prev, [key]: 0 }))
      await refreshInterpretationState(key)
    } catch {
      setErrorMsg(lang === "fr" ? "Impossible d'annuler la génération." : "Unable to cancel generation.")
    }
  }

  useEffect(() => {
    if (!hasPending) return
    const timer = setInterval(() => {
      refreshInterpretationState().catch(() => {})
    }, 3000)
    return () => clearInterval(timer)
  }, [hasPending, refreshInterpretationState])

  async function requestInterpretation(key) {
    if (pending[key]) return
    const hasExisting = !!interpretations[key]
    if (hasExisting && !window.confirm(t.confirmForceInterpret)) return
    setShowPicker(false)
    setErrorMsg("")
    setPending(prev => ({ ...prev, [key]: true }))
    try {
      const res = await apiFetch(`/entries/${entry.timestamp}/interpret`, {
        method: "POST",
        body: JSON.stringify({ interpreter: key, force: hasExisting })
      })

      if (res.status === "ok") {
        setInterpretations(prev => ({
          ...prev,
          [key]: {
            name: res.interpreter,
            text: res.interpretation,
            source: res.source || "mistral",
            generation_seconds: res.generation_seconds,
          }
        }))
        setPending(prev => ({ ...prev, [key]: false }))
        return
      }

      await refreshInterpretationState(key)

    } catch(e) {
      console.error("Interpretation error:", e)
      setErrorMsg(lang === "fr" ? "Impossible de demander l'interprétation." : "Unable to request interpretation.")
      setPending(prev => ({ ...prev, [key]: false }))
    }
  }

  return (
    <div className="mt-6 px-6 pb-4">
      <div className="flex items-center justify-between mb-4">
        <div className="text-xs uppercase tracking-widest opacity-40">{t.interpretations}</div>
        <button onClick={() => setShowPicker(true)}
          className="text-xs px-3 py-1 rounded-full border border-white/10 hover:border-white/20 transition-colors opacity-60 hover:opacity-100">
          {hasPending ? "…" : `+ ${t.interpret}`}
        </button>
      </div>

      {Object.entries(interpretations).map(([key, interp]) => {
        const meta = INTERPRETERS[key]
        return (
          <div key={key} className="mb-4 p-4 rounded-xl" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
            <div className="flex items-center gap-2 mb-2">
              <span>{meta?.emoji}</span>
              <span className="text-xs font-medium opacity-70">{meta?.name[lang] || interp.name}</span>
              <span className="text-xs opacity-30">· {meta?.style[lang]}</span>
              <button
                onClick={() => requestInterpretation(key)}
                disabled={!!pending[key]}
                className="ml-auto px-2.5 py-1 rounded-lg text-[11px] border border-white/10 hover:border-white/20 transition-colors disabled:opacity-40"
              >
                {pending[key] ? t.interpreting : t.forceInterpret}
              </button>
            </div>
            <p className="text-sm leading-relaxed opacity-80" style={{ fontFamily: "'Lora', Georgia, serif" }}>{interp.text}</p>
            {(interp.source || interp.generation_seconds !== undefined) && (
              <div className="text-[11px] opacity-35 mt-2">
                {interp.source ? `source: ${interp.source}` : ""}
                {interp.source && formatGenerationSeconds(interp.generation_seconds) ? " • " : ""}
                {formatGenerationSeconds(interp.generation_seconds) ? `${t.generatedIn} ${formatGenerationSeconds(interp.generation_seconds)}` : ""}
              </div>
            )}
          </div>
        )
      })}

      {Object.entries(pending)
        .filter(([key, isPending]) => isPending && !interpretations[key])
        .map(([key]) => (
          <div key={key} className="mb-4 p-4 rounded-xl animate-pulse" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
            <div className="flex items-center gap-2 mb-3">
              <span>{INTERPRETERS[key]?.emoji}</span>
              <span className="text-xs opacity-40">{t.interpreting}</span>
            </div>
            <div className="h-3 bg-white/5 rounded w-3/4 mb-2" />
            <div className="h-3 bg-white/5 rounded w-1/2" />
            {Number.isFinite(Number(pendingSeconds[key])) && Number(pendingSeconds[key]) >= 20 && (
              <div className="mt-3 flex items-center justify-between gap-3">
                <div className="text-[11px] opacity-45">
                  {t.pendingLongHint.replace("{seconds}", String(Math.round(Number(pendingSeconds[key]))))}
                </div>
                <button
                  onClick={() => cancelInterpretation(key)}
                  className="px-2.5 py-1 rounded-lg text-[11px] border border-white/10 hover:border-white/20 transition-colors"
                >
                  {t.cancelGeneration}
                </button>
              </div>
            )}
          </div>
        ))}

      {errorMsg && (
        <div className="mb-4 p-4 rounded-xl text-sm" style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.25)", color: "#fca5a5" }}>
          {errorMsg}
        </div>
      )}

      {showPicker && (
        <div className="fixed inset-0 z-50 flex items-end justify-center"
          style={{ background: "rgba(0,0,0,0.5)", backdropFilter: "blur(4px)", paddingBottom: "80px" }}
          onClick={() => setShowPicker(false)}>
          <div className="w-full max-w-lg p-6 rounded-t-2xl"
            style={{ background: "var(--surface)", borderTop: "1px solid var(--border)" }}
            onClick={e => e.stopPropagation()}>
            <div className="text-xs uppercase tracking-widest opacity-40 mb-4">{t.chooseInterpreter}</div>
            <div className="space-y-2">
              {Object.entries(INTERPRETERS).map(([key, interp]) => (
                <button key={key} onClick={() => requestInterpretation(key)}
                  disabled={!!pending[key]}
                  className="w-full flex items-center gap-4 p-4 rounded-xl border border-white/10 hover:border-white/20 transition-colors disabled:opacity-30 text-left">
                  <span className="text-2xl">{interp.emoji}</span>
                  <div>
                    <div className="text-sm font-medium">{interp.name[lang]}</div>
                    <div className="text-xs opacity-40">{interp.style[lang]}</div>
                  </div>
                  {interpretations[key] && !pending[key] && <span className="ml-auto text-xs opacity-40">{t.forceInterpret}</span>}
                  {!interpretations[key] && pending[key] && <span className="ml-auto text-xs opacity-40">◌</span>}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── TappableTranscript ────────────────────────────────────────────────────────
function TappableTranscript({ text, timestamp, lang }) {
  const [words, setWords] = useState(text.split(/(\s+|(?<=[^\s])[.,;:!?'"«»…()—–]|[.,;:!?'"«»…()—–](?=[^\s]))/))
  const [editing, setEditing] = useState(null)
  const [editValue, setEditValue] = useState("")
  const [showVocab, setShowVocab] = useState(null)
  const [savedMsg, setSavedMsg] = useState(false)

  function startEdit(i) {
    if (words[i].trim() === "") return
    setEditing(i); setEditValue(words[i])
  }

  async function confirmEdit() {
    const original = words[editing]
    const corrected = editValue.trim()
    if (!corrected || corrected === original) { setEditing(null); return }
    const newWords = [...words]
    newWords[editing] = corrected
    setWords(newWords); setEditing(null)
    await apiFetch(`/entries/${timestamp}/save-transcript`, { method: "POST", body: JSON.stringify({ text: newWords.join("") }) })
    if (corrected[0] === corrected[0].toUpperCase() && corrected[0] !== corrected[0].toLowerCase()) {
      setShowVocab({ original, corrected })
    }
  }

  async function addToVocabulary() {
    await apiFetch("/vocabulary/add", { method: "POST", body: JSON.stringify({ word: showVocab.corrected }) })
    setShowVocab(null); setSavedMsg(true)
    setTimeout(() => setSavedMsg(false), 2000)
  }

  return (
    <div>
      <p className="text-base leading-8" style={{ fontFamily: "'Lora', Georgia, serif" }}>
        {words.map((word, i) =>
          word.trim() === "" ? <span key={i}>{word}</span> : (
            <span key={i} onClick={() => startEdit(i)} className="cursor-pointer hover:bg-white/10 rounded px-0.5 transition-colors">{word}</span>
          )
        )}
      </p>
      {savedMsg && <div className="text-xs text-emerald-400 mt-2">✓ {lang === "fr" ? "Ajouté au vocabulaire" : "Added to vocabulary"}</div>}

      {editing !== null && (
        <div className="fixed inset-0 z-50 flex items-end justify-center"
          style={{ background: "rgba(0,0,0,0.5)", backdropFilter: "blur(4px)", paddingBottom: "80px" }}
          onClick={() => setEditing(null)}>
          <div className="w-full max-w-lg p-6 rounded-t-2xl" style={{ background: "var(--surface)", borderTop: "1px solid var(--border)" }} onClick={e => e.stopPropagation()}>
            <div className="text-xs opacity-40 mb-2 uppercase tracking-widest">{lang === "fr" ? "Corriger le mot" : "Correct word"}</div>
            <input autoFocus value={editValue} onChange={e => setEditValue(e.target.value)} onKeyDown={e => { if (e.key === "Enter") confirmEdit() }}
              className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-base focus:outline-none focus:border-white/20 mb-4"
              style={{ fontFamily: "'Lora', Georgia, serif" }} />
            <div className="flex gap-3">
              <button onClick={() => setEditing(null)} className="flex-1 py-3 rounded-xl text-sm border border-white/10 opacity-50">{lang === "fr" ? "Annuler" : "Cancel"}</button>
              <button onClick={confirmEdit} className="flex-1 py-3 rounded-xl text-sm border border-white/20">{lang === "fr" ? "Confirmer" : "Confirm"}</button>
            </div>
          </div>
        </div>
      )}

      {showVocab && (
        <div className="fixed inset-0 z-50 flex items-end justify-center"
          style={{ background: "rgba(0,0,0,0.5)", backdropFilter: "blur(4px)", paddingBottom: "80px" }}
          onClick={() => setShowVocab(null)}>
          <div className="w-full max-w-lg p-6 rounded-t-2xl" style={{ background: "var(--surface)", borderTop: "1px solid var(--border)" }} onClick={e => e.stopPropagation()}>
            <div className="text-sm opacity-70 mb-2">{lang === "fr" ? `Ajouter « ${showVocab.corrected} » au vocabulaire ?` : `Add "${showVocab.corrected}" to vocabulary?`}</div>
            <div className="text-xs opacity-30 mb-4">{lang === "fr" ? "Ce mot sera mieux reconnu dans les prochaines transcriptions." : "This word will be better recognized in future transcriptions."}</div>
            <div className="flex gap-3">
              <button onClick={() => setShowVocab(null)} className="flex-1 py-3 rounded-xl text-sm border border-white/10 opacity-50">{lang === "fr" ? "Non" : "No"}</button>
              <button onClick={addToVocabulary} className="flex-1 py-3 rounded-xl text-sm border border-white/20">{lang === "fr" ? "Ajouter" : "Add"}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── EntryDetail ───────────────────────────────────────────────────────────────
function EntryDetail({ entry, onBack, lang, onRefresh }) {
  const t = translations[lang]
  const [view, setView] = useState(entry.transcript_user ? "user" : entry.transcript_corrected ? "corrected" : "raw")
  const [correcting, setCorrecting] = useState(false)
  const [playing, setPlaying] = useState(false)
  const [editingDate, setEditingDate] = useState(false)
  const [dateInput, setDateInput] = useState(entryDateToInputValue(entry))
  const [savingDate, setSavingDate] = useState(false)
  const audioRef = useRef(null)
  const ts = formatEntryDate(entry)

  useEffect(() => { return () => { if (audioRef.current) { audioRef.current.pause(); audioRef.current = null } } }, [])
  useEffect(() => { setDateInput(entryDateToInputValue(entry)); setEditingDate(false) }, [entry.timestamp, entry.dream_date, entry.received_at])

  async function triggerCorrection() {
    setCorrecting(true)
    try { await apiFetch(`/entries/${entry.timestamp}/correct`, { method: "POST" }); setTimeout(() => { onRefresh(); setCorrecting(false) }, 5000) }
    catch { setCorrecting(false) }
  }

  async function toggleAudio() {
    if (!audioRef.current) {
      const res = await fetch(`${API_BASE}/entries/${entry.timestamp}/audio`, { headers: { "X-API-Key": localStorage.getItem("api_key") || "" } })
      audioRef.current = new Audio(URL.createObjectURL(await res.blob()))
      audioRef.current.onended = () => setPlaying(false)
    }
    if (playing) { audioRef.current.pause(); setPlaying(false) }
    else { audioRef.current.play(); setPlaying(true) }
  }

  async function saveDreamDate() {
    if (!dateInput) return
    setSavingDate(true)
    try {
      await apiFetch(`/entries/${entry.timestamp}/dream-date`, {
        method: "POST",
        body: JSON.stringify({ dream_date: new Date(dateInput).toISOString() })
      })
      setEditingDate(false)
      onRefresh()
    } catch {
    } finally {
      setSavingDate(false)
    }
  }

  const text = view === "user" ? entry.transcript_user : view === "corrected" ? entry.transcript_corrected : entry.transcript_raw

  return (
    <div className="min-h-screen flex flex-col">
      <div className="flex items-center gap-4 px-6 py-5 border-b border-white/5">
        <button onClick={onBack} className="opacity-40 hover:opacity-100 transition-opacity text-lg">←</button>
        <div>
          <div className="text-xs opacity-50">{ts.time}</div>
          <div className="font-medium" style={{ fontFamily: "'Playfair Display', Georgia, serif" }}>{ts.date}</div>
        </div>
        <button
          onClick={() => setEditingDate(v => !v)}
          className="ml-auto text-xs px-3 py-1.5 rounded-lg border border-white/10 hover:border-white/20 transition-colors opacity-70"
        >
          {t.editDate}
        </button>
        {entry.fuzzy && <span className="ml-auto text-xs px-2 py-0.5 rounded-full bg-amber-400/10 text-amber-400">⚠</span>}
      </div>

      {editingDate && (
        <div className="px-6 pt-4 pb-2 border-b border-white/5">
          <div className="text-xs uppercase tracking-widest opacity-40 mb-2">{t.dreamDate}</div>
          <input
            type="datetime-local"
            value={dateInput}
            onChange={e => setDateInput(e.target.value)}
            className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-white/20 transition-colors"
          />
          <div className="flex gap-2 mt-3">
            <button onClick={() => setEditingDate(false)} className="flex-1 py-2 rounded-lg text-sm border border-white/10 opacity-70">{t.cancel}</button>
            <button onClick={saveDreamDate} disabled={!dateInput || savingDate} className="flex-1 py-2 rounded-lg text-sm border border-white/20 disabled:opacity-40">{savingDate ? "…" : t.saveDate}</button>
          </div>
        </div>
      )}

      {entry.transcript_raw && (
        <div className="flex gap-1 mx-6 mt-4 p-1 rounded-lg bg-white/5">
          <button onClick={() => setView("raw")} className={`flex-1 py-1.5 text-xs rounded-md transition-colors ${view === "raw" ? "bg-white/10 text-white" : "text-white/40 hover:text-white/60"}`}>{t.raw}</button>
          {entry.transcript_corrected && <button onClick={() => setView("corrected")} className={`flex-1 py-1.5 text-xs rounded-md transition-colors ${view === "corrected" ? "bg-white/10 text-white" : "text-white/40 hover:text-white/60"}`}>{t.corrected}</button>}
          {entry.transcript_user && <button onClick={() => setView("user")} className={`flex-1 py-1.5 text-xs rounded-md transition-colors ${view === "user" ? "bg-white/10 text-white" : "text-white/40 hover:text-white/60"}`}>✎</button>}
        </div>
      )}

      <div className="flex-1 px-6 py-6">
        {text ? (
          <div className="opacity-85"><TappableTranscript text={text} timestamp={entry.timestamp} lang={lang} /></div>
        ) : !entry.transcribed ? (
          <div className="flex items-center gap-2 opacity-50"><span className="animate-spin">◌</span><span className="text-sm">{t.transcribing}</span></div>
        ) : null}
      </div>

      <TagEditor entry={entry} lang={lang} />
      {entry.transcribed && text && <InterpretationPanel entry={entry} lang={lang} />}

      <div className="px-6 pb-8 flex gap-3 flex-wrap">
        <button onClick={toggleAudio} className="py-3 px-4 rounded-xl text-sm border border-white/10 hover:border-white/20 transition-colors">{playing ? "⏸" : "▶"}</button>
        {entry.transcribed && !entry.transcript_corrected && (
          <button onClick={triggerCorrection} disabled={correcting} className="flex-1 py-3 rounded-xl text-sm border border-white/10 hover:border-white/20 transition-colors disabled:opacity-40">{correcting ? "…" : t.correct}</button>
        )}
        {(entry.transcript_raw || entry.transcript_corrected || entry.transcript_user) && (
          <button onClick={() => { const txt = entry.transcript_user || entry.transcript_corrected || entry.transcript_raw; if (navigator.share) navigator.share({ title: "🌙 Rêve", text: txt }); else { navigator.clipboard.writeText(txt); alert("Copié dans le presse-papiers") } }}
            className="py-3 px-4 rounded-xl text-sm border border-white/10 hover:border-white/20 transition-colors">↗</button>
        )}
        <button onClick={async () => { if (!confirm(lang === "fr" ? "Supprimer ce rêve ?" : "Delete this dream?")) return; await apiFetch(`/entries/${entry.timestamp}`, { method: "DELETE" }); onBack() }}
          className="py-3 px-4 rounded-xl text-sm border border-red-400/20 text-red-400/60 hover:border-red-400/40 hover:text-red-400 transition-colors">✕</button>
        {entry.duration_seconds > 0 && <div className="text-xs opacity-30 self-center ml-auto">{formatDuration(entry.duration_seconds)}</div>}
      </div>
    </div>
  )
}

// ── StatsScreen ───────────────────────────────────────────────────────────────
function StatsScreen({ lang }) {
  const t = translations[lang]
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiFetch("/stats").then(setStats).catch(() => {}).finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="px-6 py-6 text-sm opacity-40 animate-pulse">{t.loading}</div>
  if (!stats || stats.total_entries === 0) return (
    <div className="px-6 py-6">
      <h1 className="text-2xl mb-8 font-light" style={{ fontFamily: "'Playfair Display', Georgia, serif" }}>{t.stats}</h1>
      <div className="text-sm opacity-30 italic">{t.noStats}</div>
    </div>
  )

  const maxMonthly = Math.max(...(stats.monthly || []).map(([, v]) => v), 1)
  const maxWordCount = stats.top_words?.[0]?.[1] || 1
  const monthLabels = {
    fr: ["jan","fév","mar","avr","mai","jun","jul","aoû","sep","oct","nov","déc"],
    en: ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"]
  }

  return (
    <div className="px-6 py-6 pb-24">
      <h1 className="text-2xl mb-8 font-light" style={{ fontFamily: "'Playfair Display', Georgia, serif" }}>{t.stats}</h1>

      <div className="grid grid-cols-3 gap-3 mb-10">
        {[
          { label: t.totalEntries, value: stats.total_entries },
          { label: t.avgPerMonth, value: stats.avg_per_month },
          { label: t.avgLength, value: `${stats.avg_length}` },
        ].map(({ label, value }) => (
          <div key={label} className="rounded-xl p-4 text-center" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
            <div className="text-2xl font-light mb-1" style={{ fontFamily: "'Playfair Display', Georgia, serif", color: "var(--accent)" }}>{value}</div>
            <div className="text-xs opacity-40 leading-tight">{label}</div>
          </div>
        ))}
      </div>

      {stats.monthly && stats.monthly.length > 0 && (
        <div className="mb-10">
          <div className="text-xs uppercase tracking-widest opacity-40 mb-4">{t.monthlyChart}</div>
          <div className="flex items-end gap-2 h-32">
            {stats.monthly.map(([month, count]) => {
              const [y, m] = month.split("-")
              const label = monthLabels[lang][parseInt(m) - 1]
              const height = Math.round((count / maxMonthly) * 100)
              return (
                <div key={month} className="flex-1 flex flex-col items-center gap-1">
                  <div className="text-xs opacity-50">{count}</div>
                  <div className="w-full rounded-t-sm" style={{ height: `${Math.max(height, 4)}%`, background: "var(--accent)", opacity: 0.8 }} />
                  <div className="text-xs opacity-30">{label}</div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {stats.top_words && stats.top_words.length > 0 && (
        <div className="mb-10">
          <div className="text-xs uppercase tracking-widest opacity-40 mb-4">{t.topWords}</div>
          <div className="space-y-2">
            {stats.top_words.slice(0, 15).map(([word, count]) => (
              <div key={word} className="flex items-center gap-3">
                <div className="text-sm w-28 opacity-80 truncate">{word}</div>
                <div className="flex-1 h-1.5 rounded-full bg-white/5 overflow-hidden">
                  <div className="h-full rounded-full" style={{ width: `${Math.round((count / maxWordCount) * 100)}%`, background: "var(--accent)", opacity: 0.7 }} />
                </div>
                <div className="text-xs opacity-30 w-4 text-right">{count}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {stats.top_tags && stats.top_tags.length > 0 && (
        <div className="mb-10">
          <div className="text-xs uppercase tracking-widest opacity-40 mb-4">{t.topTags}</div>
          <div className="flex flex-wrap gap-2">
            {stats.top_tags.map(([tag, count]) => (
              <div key={tag} className="flex items-center gap-1.5 px-3 py-1 rounded-full border border-white/10">
                <span className="text-xs">{tag}</span>
                <span className="text-xs opacity-40">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {stats.top_tags_30 && stats.top_tags_30.length > 0 && (
        <div className="mb-10">
          <div className="text-xs uppercase tracking-widest opacity-40 mb-4">{t.topTags30}</div>
          <div className="flex flex-wrap gap-2">
            {stats.top_tags_30.map(([tag, count]) => (
              <div key={tag} className="flex items-center gap-1.5 px-3 py-1 rounded-full border" style={{ borderColor: "var(--accent)" }}>
                <span className="text-xs" style={{ color: "var(--accent)" }}>{tag} {count}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── DigestScreen ──────────────────────────────────────────────────────────────
function DigestScreen({ lang }) {
  const t = translations[lang]
  const [digest, setDigest] = useState(null)
  const [loading, setLoading] = useState(true)
  const [weeksAgo, setWeeksAgo] = useState(0)
  const [summaryByWeek, setSummaryByWeek] = useState({})
  const [summaryStatusByWeek, setSummaryStatusByWeek] = useState({})
  const [summaryPendingSecondsByWeek, setSummaryPendingSecondsByWeek] = useState({})

  const weekKey = `w${weeksAgo}`
  const currentSummary = summaryByWeek[weekKey] || { text: "", source: "", generation_seconds: null }
  const weekSummaryStatus = summaryStatusByWeek[weekKey] || "idle"
  const summary = currentSummary.text || ""
  const summarySource = currentSummary.source || ""
  const generationSecondsRaw = Number(currentSummary.generation_seconds)
  const hasGenerationSeconds = Number.isFinite(generationSecondsRaw) && generationSecondsRaw >= 0
  const generationSeconds = hasGenerationSeconds ? generationSecondsRaw : null
  const summaryLoading = weekSummaryStatus === "pending"
  const summaryPendingSeconds = Number(summaryPendingSecondsByWeek[weekKey])
  const canAskSummary = !!digest?.week_complete
  const hasSummary = !!summary

  function statusBadge(status) {
    const labels = {
      fr: { idle: "prêt", pending: "analyse…", done: "résumé prêt", error: "erreur" },
      en: { idle: "ready", pending: "thinking…", done: "summary ready", error: "error" },
    }
    const palette = {
      idle: "border-white/15 text-white/45",
      pending: "border-emerald-400/40 text-emerald-300 animate-pulse",
      done: "border-sky-400/40 text-sky-300",
      error: "border-red-400/40 text-red-300",
    }
    const l = labels[lang] || labels.en
    return (
      <span className={`ml-2 px-2 py-0.5 rounded-full border text-[10px] ${palette[status] || palette.idle}`}>
        {l[status] || l.idle}
      </span>
    )
  }

  function setWeekSummary(week, payload) {
    const key = `w${week}`
    setSummaryByWeek((prev) => ({
      ...prev,
      [key]: {
        text: payload?.summary || "",
        source: payload?.source || "",
        generation_seconds: payload?.generation_seconds,
      },
    }))
  }

  function formatGenerationSeconds(seconds) {
    if (!Number.isFinite(seconds) || seconds < 0) return ""
    if (seconds < 1) return `${Math.round(seconds * 1000)} ms`
    return `${seconds.toFixed(1)} s`
  }

  function setWeekSummaryStatus(week, status) {
    const key = `w${week}`
    setSummaryStatusByWeek((prev) => ({ ...prev, [key]: status }))
  }

  function setWeekSummaryPendingSeconds(week, seconds) {
    const key = `w${week}`
    setSummaryPendingSecondsByWeek((prev) => ({ ...prev, [key]: Number(seconds) }))
  }

  function fmtDate(isoLike) {
    if (!isoLike) return ""
    const d = new Date(isoLike)
    if (Number.isNaN(d.getTime())) return String(isoLike).slice(0, 10)
    return d.toLocaleDateString(lang === "fr" ? "fr-FR" : "en-US", { day: "2-digit", month: "short" })
  }

  function tensionLabel(level) {
    if (lang === "fr") {
      if (level === "high") return "élevé"
      if (level === "medium") return "modéré"
      return "faible"
    }
    if (level === "high") return "high"
    if (level === "medium") return "medium"
    return "low"
  }

  function monthLabel(year, month) {
    const d = new Date(year, Math.max(0, month - 1), 1)
    return d.toLocaleDateString(lang === "fr" ? "fr-FR" : "en-US", {
      month: "long",
      year: "numeric",
    })
  }

  useEffect(() => {
    setLoading(true)
    apiFetch(`/digest/weekly?days=7&weeks_ago=${weeksAgo}`)
      .then(setDigest)
      .catch(() => setDigest(null))
      .finally(() => setLoading(false))
  }, [weeksAgo])

  useEffect(() => {
    let alive = true
    async function refreshSummaryState() {
      try {
        const st = await apiFetch(`/digest/weekly/summary-status?days=7&weeks_ago=${weeksAgo}`)
        if (!alive) return

        if (st?.status === "ok") {
          setWeekSummary(weeksAgo, st)
          setWeekSummaryStatus(weeksAgo, "done")
          setWeekSummaryPendingSeconds(weeksAgo, 0)
          if (st?.digest) setDigest(st.digest)
          return
        }
        if (st?.status === "pending") {
          setWeekSummaryStatus(weeksAgo, "pending")
          setWeekSummaryPendingSeconds(weeksAgo, st?.pending_seconds || 0)
          return
        }
        if (st?.status === "error") {
          setWeekSummaryStatus(weeksAgo, "error")
          setWeekSummaryPendingSeconds(weeksAgo, 0)
          return
        }
        setWeekSummaryStatus(weeksAgo, "idle")
        setWeekSummaryPendingSeconds(weeksAgo, 0)
      } catch {
        if (alive) {
          setWeekSummaryStatus(weeksAgo, "idle")
          setWeekSummaryPendingSeconds(weeksAgo, 0)
        }
      }
    }

    refreshSummaryState()
    return () => { alive = false }
  }, [weeksAgo])

  useEffect(() => {
    if (!summaryLoading) return
    let alive = true
    const intervalId = setInterval(async () => {
      try {
        const st = await apiFetch(`/digest/weekly/summary-status?days=7&weeks_ago=${weeksAgo}`)
        if (!alive) return
        if (st?.status === "ok") {
          setWeekSummary(weeksAgo, st)
          setWeekSummaryStatus(weeksAgo, "done")
          setWeekSummaryPendingSeconds(weeksAgo, 0)
          if (st?.digest) setDigest(st.digest)
        } else if (st?.status === "error") {
          setWeekSummaryStatus(weeksAgo, "error")
          setWeekSummaryPendingSeconds(weeksAgo, 0)
        } else if (st?.status === "idle") {
          setWeekSummaryStatus(weeksAgo, "idle")
          setWeekSummaryPendingSeconds(weeksAgo, 0)
        } else if (st?.status === "pending") {
          setWeekSummaryStatus(weeksAgo, "pending")
          setWeekSummaryPendingSeconds(weeksAgo, st?.pending_seconds || 0)
        }
      } catch {
        // Keep pending state; next poll can recover when server is reachable.
      }
    }, 1400)

    return () => {
      alive = false
      clearInterval(intervalId)
    }
  }, [weeksAgo, summaryLoading])

  async function askSummary() {
    const forceRequested = hasSummary
    if (forceRequested && !window.confirm(t.confirmForceSummary)) return
    setWeekSummaryStatus(weeksAgo, "pending")
    try {
      const res = await apiFetch("/digest/weekly/summary", {
        method: "POST",
        body: JSON.stringify({ days: 7, weeks_ago: weeksAgo, force: forceRequested }),
      })

      if (res?.status === "ok") {
        setWeekSummary(weeksAgo, res)
        setWeekSummaryStatus(weeksAgo, "done")
        setWeekSummaryPendingSeconds(weeksAgo, 0)
        if (res?.digest) setDigest(res.digest)
      } else {
        setWeekSummaryStatus(weeksAgo, "pending")
        setWeekSummaryPendingSeconds(weeksAgo, 0)
      }
    } catch {
      setWeekSummaryStatus(weeksAgo, "error")
      setWeekSummaryPendingSeconds(weeksAgo, 0)
    }
  }

  async function cancelSummaryGeneration() {
    try {
      await apiFetch("/digest/weekly/summary/cancel", {
        method: "POST",
        body: JSON.stringify({ days: 7, weeks_ago: weeksAgo }),
      })
      setWeekSummaryStatus(weeksAgo, "idle")
      setWeekSummaryPendingSeconds(weeksAgo, 0)
    } catch {
      setWeekSummaryStatus(weeksAgo, "error")
    }
  }

  function WeekSwitcher() {
    return (
      <div className="mb-5 flex gap-2 items-center">
        <button
          onClick={() => {
            setWeeksAgo((w) => w + 1)
          }}
          className="px-3 py-1.5 rounded-lg text-xs border border-white/10 hover:border-white/20 transition-colors"
        >
          {t.previousWeek}
        </button>
        <button
          onClick={() => {
            setWeeksAgo((w) => Math.max(0, w - 1))
          }}
          disabled={weeksAgo === 0}
          className="px-3 py-1.5 rounded-lg text-xs border border-white/10 hover:border-white/20 transition-colors disabled:opacity-40"
        >
          {t.nextWeek}
        </button>
        <div className="ml-auto text-xs opacity-50 flex items-center">
          <span>{weeksAgo === 0 ? t.currentWeek : `${t.previousWeek} (${weeksAgo})`}</span>
          {statusBadge(weekSummaryStatus)}
        </div>
      </div>
    )
  }

  function SummaryPanel() {
    return (
      <>
        <div className="mb-6">
          <button
            onClick={askSummary}
            disabled={summaryLoading || !canAskSummary}
            className="px-4 py-2 rounded-lg text-sm border border-white/10 hover:border-white/20 transition-colors disabled:opacity-40"
          >
            {summaryLoading ? t.summaryLoading : (hasSummary ? t.forceSummary : t.askSummary)}
          </button>
        </div>
        {!canAskSummary && (
          <div className="mb-5 text-xs opacity-45 italic">{t.summaryWeekNotReady}</div>
        )}
        {(summaryLoading || summary) && (
          <div className="mb-8 rounded-xl p-4" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
            <div className="text-xs uppercase tracking-widest opacity-40 mb-2">{t.summaryTitle}</div>
            {summaryLoading ? (
              <div>
                <div className="text-sm opacity-50 animate-pulse">{t.summaryLoading}</div>
                {Number.isFinite(summaryPendingSeconds) && summaryPendingSeconds >= 20 && (
                  <div className="mt-3 flex items-center justify-between gap-3">
                    <div className="text-[11px] opacity-45">
                      {t.pendingLongHint.replace("{seconds}", String(Math.round(summaryPendingSeconds)))}
                    </div>
                    <button
                      onClick={cancelSummaryGeneration}
                      className="px-2.5 py-1 rounded-lg text-[11px] border border-white/10 hover:border-white/20 transition-colors"
                    >
                      {t.cancelGeneration}
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <>
                <div className="text-sm leading-relaxed opacity-85">{summary}</div>
                {(summarySource || generationSeconds !== null) && (
                  <div className="text-[11px] opacity-35 mt-2">
                    {summarySource ? `source: ${summarySource}` : ""}
                    {summarySource && generationSeconds !== null ? " • " : ""}
                    {generationSeconds !== null ? `${t.generatedIn} ${formatGenerationSeconds(generationSeconds)}` : ""}
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </>
    )
  }

  if (loading) return <div className="px-6 py-6 text-sm opacity-40 animate-pulse">{t.loading}</div>
  if (!digest || (digest.total_entries || 0) === 0) {
    return (
      <div className="px-6 py-6 pb-24">
        <h1 className="text-2xl mb-8 font-light" style={{ fontFamily: "'Playfair Display', Georgia, serif" }}>{t.weeklyDigest}</h1>
        <WeekSwitcher />
        <SummaryPanel />
        <div className="text-sm opacity-30 italic">{t.noDigest}</div>
      </div>
    )
  }

  const maxDaily = Math.max(...(digest.daily || []).map(d => d.count), 1)
  const dreamNightMap = new Map((digest.calendar?.dream_nights || []).map((n) => [n.day, n.count]))

  return (
    <div className="px-6 py-6 pb-24">
      <h1 className="text-2xl mb-8 font-light" style={{ fontFamily: "'Playfair Display', Georgia, serif" }}>{t.weeklyDigest}</h1>
      <WeekSwitcher />
      <SummaryPanel />

      <div className="grid grid-cols-3 gap-3 mb-8">
        {[
          { label: t.totalEntries, value: digest.total_entries },
          { label: t.nightmareEntries, value: digest.nightmare_entries },
          { label: t.tensionLevel, value: tensionLabel(digest.tension_level) },
        ].map(({ label, value }) => (
          <div key={label} className="rounded-xl p-4 text-center" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
            <div className="text-xl font-light mb-1" style={{ fontFamily: "'Playfair Display', Georgia, serif", color: "var(--accent)" }}>{value}</div>
            <div className="text-xs opacity-40 leading-tight">{label}</div>
          </div>
        ))}
      </div>

      {digest.top_tags && digest.top_tags.length > 0 && (
        <div className="mb-8">
          <div className="text-xs uppercase tracking-widest opacity-40 mb-3">{t.topTags}</div>
          <div className="flex flex-wrap gap-2">
            {digest.top_tags.map(([tag, count]) => (
              <div key={tag} className="px-3 py-1 rounded-full border border-white/10 text-xs">
                {tag} <span className="opacity-40">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {digest.calendar && (
        <div className="mb-2">
          <div className="text-xs uppercase tracking-widest opacity-40 mb-3">{monthLabel(digest.calendar.year, digest.calendar.month)}</div>
          <div className="rounded-xl p-3" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
            <div className="grid grid-cols-7 gap-1 mb-2">
              {(lang === "fr" ? ["L", "M", "M", "J", "V", "S", "D"] : ["M", "T", "W", "T", "F", "S", "S"]).map((d, i) => (
                <div key={`${d}-${i}`} className="text-[10px] text-center opacity-40">{d}</div>
              ))}
            </div>
            <div className="grid grid-cols-7 gap-1">
              {Array.from({ length: digest.calendar.first_weekday }).map((_, i) => (
                <div key={`pad-${i}`} className="h-9" />
              ))}
              {Array.from({ length: digest.calendar.days_in_month }).map((_, idx) => {
                const day = idx + 1
                const marker = dreamNightMap.get(day)
                return (
                  <div key={day} className="h-9 rounded-lg border border-white/10 flex items-center justify-center text-xs relative">
                    <span className={marker ? "opacity-95" : "opacity-50"}>{day}</span>
                    {marker && (
                      <span className="absolute -top-1 right-1 text-[11px]" style={{ color: "var(--accent)" }}>
                        ✦
                      </span>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── DreamMapScreen ────────────────────────────────────────────────────────────
function DreamMapScreen({ lang }) {
  const t = translations[lang]
  const [nodes, setNodes] = useState([])
  const [groups, setGroups] = useState([])
  const [loading, setLoading] = useState(true)
  const [resetting, setResetting] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)
  const svgRef = useRef(null)
  const dragRef = useRef(null)
  const pinchRef = useRef(null)
  const pointersRef = useRef(new Map())
  const initialView = { x: 0, y: 0, w: 1200, h: 860 }
  const [view, setView] = useState(initialView)

  function clamp(v, min, max) {
    return Math.max(min, Math.min(max, v))
  }

  function zoomAt(clientX, clientY, factor) {
    if (!svgRef.current) return
    const rect = svgRef.current.getBoundingClientRect()
    const mx = view.x + ((clientX - rect.left) / rect.width) * view.w
    const my = view.y + ((clientY - rect.top) / rect.height) * view.h
    const nextW = clamp(view.w * factor, 320, 3000)
    const nextH = clamp(view.h * factor, 240, 2200)
    const nextX = mx - ((mx - view.x) * (nextW / view.w))
    const nextY = my - ((my - view.y) * (nextH / view.h))
    setView({ x: nextX, y: nextY, w: nextW, h: nextH })
  }

  function zoomCenter(factor) {
    if (!svgRef.current) return
    const rect = svgRef.current.getBoundingClientRect()
    zoomAt(rect.left + rect.width / 2, rect.top + rect.height / 2, factor)
  }

  useEffect(() => {
    let alive = true
    async function loadMap() {
      setLoading(true)
      try {
        const data = await apiFetch("/dream-map")
        const rawNodes = data?.nodes || []
        const groupList = data?.groups || []

        if (rawNodes.length === 0) {
          if (alive) {
            setNodes([])
            setGroups([])
          }
          return
        }

        const groupedNodes = rawNodes.filter(n => !!n.cluster)
        const ungroupedNodes = rawNodes.filter(n => !n.cluster)
        const clusterNames = [...new Set(groupedNodes.map(n => n.cluster))]
        const centerX = 600
        const centerY = 430
        const groupRadius = 240
        const clusterCenters = {}
        clusterNames.forEach((name, idx) => {
          const angle = (idx / Math.max(clusterNames.length, 1)) * Math.PI * 2
          clusterCenters[name] = {
            x: centerX + Math.cos(angle) * groupRadius,
            y: centerY + Math.sin(angle) * groupRadius,
          }
        })

        const maxV = Math.max(...rawNodes.map(n => n.value || 1), 1)
        const byCluster = new Map()
        for (const node of groupedNodes) {
          const c = node.cluster
          if (!byCluster.has(c)) byCluster.set(c, [])
          byCluster.get(c).push(node)
        }

        const positioned = []
        for (const [clusterName, clusterNodes] of byCluster.entries()) {
          const c = clusterCenters[clusterName]
          clusterNodes.forEach((n, i) => {
            const a = (i / Math.max(clusterNodes.length, 1)) * Math.PI * 2
            const ring = 48 + Math.floor(i / 6) * 36
            positioned.push({
              ...n,
              x: c.x + Math.cos(a) * ring,
              y: c.y + Math.sin(a) * ring,
              r: 12 + Math.round(((n.value || 1) / maxV) * 16),
            })
          })
        }

        // Ungrouped nodes stay outside clusters while semantic classification is pending.
        const outerRadius = 420
        ungroupedNodes.forEach((n, i) => {
          const a = (i / Math.max(ungroupedNodes.length, 1)) * Math.PI * 2
          const ring = outerRadius + Math.floor(i / 8) * 34
          positioned.push({
            ...n,
            x: centerX + Math.cos(a) * ring,
            y: centerY + Math.sin(a) * ring,
            r: 10 + Math.round(((n.value || 1) / maxV) * 14),
            cluster: null,
          })
        })

        if (alive) {
          setNodes(positioned)
          setGroups(groupList)
          setView(initialView)
        }
      } catch {
        if (alive) {
          setNodes([])
          setGroups([])
        }
      } finally {
        if (alive) setLoading(false)
      }
    }

    loadMap()
    return () => { alive = false }
  }, [reloadKey])

  async function resetDreamMap() {
    if (resetting) return
    if (!window.confirm(t.confirmResetDreamMap)) return
    setResetting(true)
    try {
      await apiFetch("/dream-map/reset", { method: "POST" })
      setReloadKey(key => key + 1)
    } catch {
    } finally {
      setResetting(false)
    }
  }

  if (loading) return <div className="px-6 py-6 text-sm opacity-40 animate-pulse">{t.loading}</div>

  function onPointerDown(e) {
    if (!svgRef.current) return
    svgRef.current.setPointerCapture?.(e.pointerId)

    pointersRef.current.set(e.pointerId, { x: e.clientX, y: e.clientY })

    if (pointersRef.current.size === 2) {
      const pts = [...pointersRef.current.values()]
      const dx = pts[1].x - pts[0].x
      const dy = pts[1].y - pts[0].y
      const dist = Math.hypot(dx, dy)
      const cx = (pts[0].x + pts[1].x) / 2
      const cy = (pts[0].y + pts[1].y) / 2
      pinchRef.current = {
        startDist: Math.max(dist, 1),
        startView: { ...view },
        centerX: cx,
        centerY: cy,
      }
      dragRef.current = null
      return
    }

    if (pointersRef.current.size > 1) return

    dragRef.current = {
      pointerId: e.pointerId,
      startX: e.clientX,
      startY: e.clientY,
      base: { ...view },
    }
  }

  function onPointerMove(e) {
    if (!svgRef.current) return
    if (pointersRef.current.has(e.pointerId)) {
      pointersRef.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
    }

    if (pinchRef.current && pointersRef.current.size >= 2) {
      const pts = [...pointersRef.current.values()].slice(0, 2)
      const dx = pts[1].x - pts[0].x
      const dy = pts[1].y - pts[0].y
      const dist = Math.max(Math.hypot(dx, dy), 1)
      const ratio = dist / pinchRef.current.startDist
      const factor = 1 / ratio

      const rect = svgRef.current.getBoundingClientRect()
      const mx = pinchRef.current.startView.x + ((pinchRef.current.centerX - rect.left) / rect.width) * pinchRef.current.startView.w
      const my = pinchRef.current.startView.y + ((pinchRef.current.centerY - rect.top) / rect.height) * pinchRef.current.startView.h

      const nextW = clamp(pinchRef.current.startView.w * factor, 320, 3000)
      const nextH = clamp(pinchRef.current.startView.h * factor, 240, 2200)
      const nextX = mx - ((mx - pinchRef.current.startView.x) * (nextW / pinchRef.current.startView.w))
      const nextY = my - ((my - pinchRef.current.startView.y) * (nextH / pinchRef.current.startView.h))
      setView({ x: nextX, y: nextY, w: nextW, h: nextH })
      return
    }

    if (!dragRef.current || dragRef.current.pointerId !== e.pointerId) return
    const rect = svgRef.current.getBoundingClientRect()
    const dx = (e.clientX - dragRef.current.startX) * (dragRef.current.base.w / rect.width)
    const dy = (e.clientY - dragRef.current.startY) * (dragRef.current.base.h / rect.height)
    setView({
      ...dragRef.current.base,
      x: dragRef.current.base.x - dx,
      y: dragRef.current.base.y - dy,
    })
  }

  function onPointerUp(e) {
    if (!svgRef.current) return
    try { svgRef.current.releasePointerCapture?.(e.pointerId) } catch {}

    pointersRef.current.delete(e.pointerId)
    if (pointersRef.current.size < 2) pinchRef.current = null

    if (pointersRef.current.size === 1) {
      const [[id, p]] = pointersRef.current.entries()
      dragRef.current = {
        pointerId: id,
        startX: p.x,
        startY: p.y,
        base: { ...view },
      }
      return
    }

    dragRef.current = null
  }

  function onWheel(e) {
    e.preventDefault()
    zoomAt(e.clientX, e.clientY, e.deltaY > 0 ? 1.12 : 0.88)
  }

  return (
    <div className="px-6 py-6 pb-24">
      <h1 className="text-2xl mb-2 font-light" style={{ fontFamily: "'Playfair Display', Georgia, serif" }}>{t.dreamMap}</h1>
      <p className="text-xs opacity-40 mb-3">{lang === "fr" ? "Constellation des thèmes et mots dominants" : "Constellation of dominant themes and words"}</p>

      <div className="flex gap-2 mb-4">
        <button onClick={() => zoomCenter(0.88)} className="px-3 py-1.5 rounded-lg text-xs border border-white/10 hover:border-white/20 transition-colors">{t.zoomIn}</button>
        <button onClick={() => zoomCenter(1.12)} className="px-3 py-1.5 rounded-lg text-xs border border-white/10 hover:border-white/20 transition-colors">{t.zoomOut}</button>
        <button onClick={() => setView(initialView)} className="px-3 py-1.5 rounded-lg text-xs border border-white/10 hover:border-white/20 transition-colors">{t.resetView}</button>
        <button onClick={resetDreamMap} disabled={resetting} className="px-3 py-1.5 rounded-lg text-xs border border-white/10 hover:border-white/20 transition-colors disabled:opacity-40">{resetting ? t.resettingDreamMap : t.resetDreamMap}</button>
      </div>

      {nodes.length === 0 ? (
        <div className="text-sm opacity-30 italic">{t.noMapData}</div>
      ) : (
        <>
          <div className="rounded-2xl p-3" style={{ background: "linear-gradient(180deg, rgba(201,169,110,0.08), rgba(255,255,255,0.02))", border: "1px solid var(--border)" }}>
            <svg
              ref={svgRef}
              viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
              className="w-full h-[58vh] rounded-xl"
              style={{ touchAction: "none", cursor: dragRef.current ? "grabbing" : "grab" }}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onPointerLeave={onPointerUp}
              onWheel={onWheel}
            >
              {nodes.map((node, i) => {
                if (!node.cluster) return null
                const cNodes = nodes.filter(n => n.cluster === node.cluster)
                if (cNodes.length === 0) return null
                const cx = cNodes.reduce((a, n) => a + n.x, 0) / cNodes.length
                const cy = cNodes.reduce((a, n) => a + n.y, 0) / cNodes.length
                return (
                  <line
                    key={`line-${node.label}-${i}`}
                    x1={cx}
                    y1={cy}
                    x2={node.x}
                    y2={node.y}
                    stroke="var(--border)"
                    strokeOpacity="0.35"
                  />
                )
              })}

              {Array.from(new Set(nodes.filter(n => n.cluster).map(n => n.cluster))).map((clusterName, i) => {
                const cNodes = nodes.filter(n => n.cluster === clusterName)
                const cx = cNodes.reduce((a, n) => a + n.x, 0) / cNodes.length
                const cy = cNodes.reduce((a, n) => a + n.y, 0) / cNodes.length
                return (
                  <g key={`cluster-${clusterName}-${i}`}>
                    <circle cx={cx} cy={cy} r="24" fill="var(--accent)" fillOpacity="0.08" stroke="var(--accent)" strokeOpacity="0.5" />
                    <text x={cx} y={cy + 4} textAnchor="middle" fontSize="10" style={{ fill: "var(--accent)", opacity: 0.9 }}>
                      {String(clusterName).slice(0, 16)}
                    </text>
                  </g>
                )
              })}

              {nodes.map((node, i) => (
                <g key={`${node.kind}-${node.label}-${i}`}>
                  <circle
                    cx={node.x}
                    cy={node.y}
                    r={node.r}
                    fill={node.kind === "tag" ? "var(--accent)" : "var(--text)"}
                    fillOpacity={node.pending ? "0.09" : node.kind === "tag" ? "0.23" : "0.12"}
                    stroke={node.kind === "tag" ? "var(--accent)" : "var(--text)"}
                    strokeOpacity="0.55"
                  />
                  {node.pending && (
                    <>
                      <circle
                        cx={node.x}
                        cy={node.y}
                        r={Math.max(8, node.r + 4)}
                        fill="none"
                        stroke="var(--accent)"
                        strokeOpacity="0.45"
                        strokeDasharray="4 5"
                        className="dm-orbit"
                      />
                      <circle
                        cx={node.x + Math.max(7, node.r * 0.7)}
                        cy={node.y - Math.max(7, node.r * 0.7)}
                        r="3.2"
                        className="dm-thinking-dot"
                        fill="var(--accent)"
                      />
                      <g transform={`translate(${node.x + Math.max(6, node.r * 0.65)}, ${node.y + Math.max(6, node.r * 0.65)})`}>
                        <circle r="7.4" fill="var(--surface)" fillOpacity="0.95" stroke="var(--accent)" strokeOpacity="0.8" />
                        <text textAnchor="middle" y="2.9" fontSize="7.5" style={{ fill: "var(--accent)", opacity: 0.95 }}>
                          🧠
                        </text>
                      </g>
                    </>
                  )}
                  <text x={node.x} y={node.y + 3} textAnchor="middle" fontSize="9" style={{ fill: "var(--text)", opacity: 0.9 }}>
                    {String(node.label).slice(0, 11)}
                  </text>
                </g>
              ))}
            </svg>
          </div>

          <div className="mt-4">
            <div className="text-xs uppercase tracking-widest opacity-40 mb-2">{t.semanticGroups}</div>
            <div className="flex flex-wrap gap-2 mb-3">
              {groups.map((g, i) => (
                <span key={`group-${g.name}-${i}`} className="text-xs px-2.5 py-1 rounded-full border" style={{ borderColor: "var(--accent)", color: "var(--accent)", opacity: 0.9 }}>
                  {g.name} · {g.count}
                </span>
              ))}
            </div>
          </div>

          <div className="mt-1 flex flex-wrap gap-2">
            {nodes.slice(0, 18).map((n, i) => (
              <span
                key={`${n.kind}-chip-${n.label}-${i}`}
                className="text-xs px-2.5 py-1 rounded-full border"
                style={{
                  borderColor: n.kind === "tag" ? "var(--accent)" : "var(--border)",
                  color: n.kind === "tag" ? "var(--accent)" : "var(--text)",
                  opacity: 0.9,
                }}
              >
                {n.label} · {n.value} · {n.cluster || t.ungrouped}{n.pending ? ` · ${t.thinking}` : ""}
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

// ── JournalScreen ─────────────────────────────────────────────────────────────
function JournalScreen({ lang }) {
  const t = translations[lang]
  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selected, setSelected] = useState(null)
  const [selectedFull, setSelectedFull] = useState(null)
  const [query, setQuery] = useState("")
  const [searchResults, setSearchResults] = useState(null)

  async function load() {
    setLoading(true); setError(null)
    try { setEntries(await apiFetch("/entries")) }
    catch(e) { setError(e.message) }
    finally { setLoading(false) }
  }

  async function doSearch(q) {
    if (!q.trim() || q.trim().length < 2) { setSearchResults(null); return }
    try { setSearchResults(await apiFetch(`/search?q=${encodeURIComponent(q)}`)) }
    catch {}
  }

  async function openEntry(entry) {
    try { const full = await apiFetch(`/entries/${entry.timestamp}`); setSelectedFull(full); setSelected(entry.timestamp) }
    catch {}
  }

  useEffect(() => { load() }, [])
  useEffect(() => { const i = setInterval(load, 30000); return () => clearInterval(i) }, [])
  useEffect(() => { const timer = setTimeout(() => doSearch(query), 400); return () => clearTimeout(timer) }, [query])

  if (selected && selectedFull) {
    return <EntryDetail entry={selectedFull} lang={lang} onBack={() => { setSelected(null); setSelectedFull(null) }} onRefresh={() => openEntry({ timestamp: selected })} />
  }

  const displayEntries = searchResults !== null ? searchResults : entries

  return (
    <div className="px-6 py-6">
      <h1 className="text-2xl mb-6 font-light" style={{ fontFamily: "'Playfair Display', Georgia, serif" }}>{t.journal}</h1>
      <div className="relative mb-6">
        <input value={query} onChange={e => setQuery(e.target.value)}
          placeholder={lang === "fr" ? "Rechercher…" : "Search…"}
          className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-white/20 transition-colors pr-8" />
        {query && <button onClick={() => { setQuery(""); setSearchResults(null) }} className="absolute right-3 top-1/2 -translate-y-1/2 opacity-40 hover:opacity-100">×</button>}
      </div>
      {searchResults !== null && (
        <div className="text-xs opacity-40 mb-4">
          {searchResults.length === 0 ? (lang === "fr" ? "Aucun résultat" : "No results") : `${searchResults.length} résultat${searchResults.length > 1 ? "s" : ""}`}
        </div>
      )}
      {loading && !searchResults && <div className="text-sm opacity-40 animate-pulse">{t.loading}</div>}
      {error && (
        <div className="text-sm text-red-400">
          {error === "AUTH_403"
            ? (lang === "fr" ? "Clé API invalide (403). Vérifie les paramètres." : "Invalid API key (403). Check settings.")
            : t.error}
          <button onClick={load} className="ml-3 underline opacity-60">{t.retry}</button>
        </div>
      )}
      {!loading && !error && displayEntries.length === 0 && !searchResults && <div className="text-sm opacity-30 italic">{t.noEntries}</div>}
      {displayEntries.map(entry => (
        <div key={entry.timestamp}>
          <EntryCard entry={entry} lang={lang} onClick={() => openEntry(entry)} />
          {entry.search_excerpt && <div className="text-xs opacity-40 italic px-1 pb-3 -mt-2 leading-relaxed">{entry.search_excerpt}</div>}
        </div>
      ))}
    </div>
  )
}

// ── PushSubscription ──────────────────────────────────────────────────────────
function PushSubscription({ lang }) {
  const [status, setStatus] = useState("idle")
  useEffect(() => {
    if (!("Notification" in window) || !("serviceWorker" in navigator)) { setStatus("unsupported"); return }
    if (Notification.permission === "granted") setStatus("subscribed")
  }, [])

  async function subscribe() {
    setStatus("requesting")
    try {
      const permission = await Notification.requestPermission()
      if (permission !== "granted") { setStatus("idle"); return }
      const reg = await navigator.serviceWorker.ready
      const { public_key } = await apiFetch("/push/key")
      const key = public_key.replace(/-/g, "+").replace(/_/g, "/")
      const raw = atob(key); const uint8 = new Uint8Array(raw.length)
      for (let i = 0; i < raw.length; i++) uint8[i] = raw.charCodeAt(i)
      const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: uint8 })
      await apiFetch("/push/subscribe", { method: "POST", body: JSON.stringify(sub.toJSON()) })
      setStatus("subscribed")
    } catch(e) { console.error("Push error:", e); setStatus("error") }
  }

  if (status === "unsupported") return <div className="text-xs opacity-30">{lang === "fr" ? "Non supporté sur cet appareil" : "Not supported on this device"}</div>
  if (status === "subscribed") return <div className="flex items-center text-sm"><StatusDot online={true} />{lang === "fr" ? "Activées" : "Enabled"}</div>
  return (
    <button onClick={subscribe} disabled={status === "requesting"}
      className="px-4 py-2 rounded-lg text-sm border border-white/10 hover:border-white/20 transition-colors disabled:opacity-40">
      {status === "requesting" ? "…" : status === "error" ? (lang === "fr" ? "Réessayer" : "Retry") : (lang === "fr" ? "Activer les notifications" : "Enable notifications")}
    </button>
  )
}

// ── SettingsScreen ────────────────────────────────────────────────────────────
function SettingsScreen({ lang, setLang, theme, setTheme }) {
  const t = translations[lang]
  const [health, setHealth] = useState(null)
  const [vocab, setVocab] = useState("")
  const [profile, setProfile] = useState({
    first_name: "",
    last_name: "",
    pronouns: "",
    birthday: "",
    pet: "",
    closest_relative: "",
    closest_relative_status: "",
    other_notes: "",
  })
  const [vocabSaved, setVocabSaved] = useState(false)
  const [profileSaved, setProfileSaved] = useState(false)
  const [showHelp, setShowHelp] = useState(false)

  useEffect(() => {
    apiFetch("/health").then(setHealth).catch(() => setHealth(null))
    apiFetch("/vocabulary").then(d => setVocab(d.vocabulary || "")).catch(() => {})
    apiFetch("/profile").then((p) => setProfile({
      first_name: p?.first_name || "",
      last_name: p?.last_name || "",
      pronouns: p?.pronouns || "",
      birthday: p?.birthday || "",
      pet: p?.pet || "",
      closest_relative: p?.closest_relative || "",
      closest_relative_status: p?.closest_relative_status || "",
      other_notes: p?.other_notes || "",
    })).catch(() => {})
  }, [])

  async function saveVocab() {
    try { await apiFetch("/vocabulary/update", { method: "POST", body: JSON.stringify({ vocabulary: vocab }) }); setVocabSaved(true); setTimeout(() => setVocabSaved(false), 2000) }
    catch {}
  }

  async function saveProfile() {
    try {
      await apiFetch("/profile/update", { method: "POST", body: JSON.stringify(profile) })
      setProfileSaved(true)
      setTimeout(() => setProfileSaved(false), 2000)
    } catch {}
  }

  return (
    <div className="px-6 py-6">
      <h1 className="text-2xl mb-8 font-light" style={{ fontFamily: "'Playfair Display', Georgia, serif" }}>{t.settings}</h1>
      <div className="mb-8">
        <div className="text-xs uppercase tracking-widest opacity-40 mb-3">Notifications</div>
        <PushSubscription lang={lang} />
      </div>
      <div className="mb-8">
        <div className="text-xs uppercase tracking-widest opacity-40 mb-3">{t.sandmanStatus}</div>
        <div className="flex items-center text-sm">
          <StatusDot online={!!health} />
          {health ? t.connected : t.disconnected}
          {health?.transcribing && <span className="ml-3 text-xs text-blue-400 animate-pulse">◌ {t.transcribing}</span>}
        </div>
      </div>
      <div className="mb-8">
        <div className="text-xs uppercase tracking-widest opacity-40 mb-3">{t.language}</div>
        <div className="flex gap-2">
          {["fr", "en"].map(l => (
            <button key={l} onClick={() => { setLang(l); localStorage.setItem("lang", l) }}
              className={`px-4 py-2 rounded-lg text-sm border transition-colors ${lang === l ? "border-white/30 bg-white/10" : "border-white/10 hover:border-white/20"}`}>
              {l === "fr" ? "Français" : "English"}
            </button>
          ))}
        </div>
      </div>
      <div className="mb-8">
        <div className="text-xs uppercase tracking-widest opacity-40 mb-3">{t.theme}</div>
        <div className="flex gap-2">
          {["auto", "light", "dark"].map(v => (
            <button
              key={v}
              onClick={() => {
                setTheme(v)
                localStorage.setItem("theme", v)
              }}
              className={`px-4 py-2 rounded-lg text-sm border transition-colors ${theme === v ? "border-white/30 bg-white/10" : "border-white/10 hover:border-white/20"}`}
            >
              {v === "auto" ? t.auto : v === "light" ? t.light : t.dark}
            </button>
          ))}
        </div>
      </div>
      <div className="mb-8">
        <div className="text-xs uppercase tracking-widest opacity-40 mb-3">{t.help}</div>
        <button
          onClick={() => setShowHelp(true)}
          className="px-4 py-2 rounded-lg text-sm border border-white/10 hover:border-white/20 transition-colors"
        >
          {t.openHelp}
        </button>
      </div>
      <div className="mb-8">
        <div className="text-xs uppercase tracking-widest opacity-40 mb-1">{t.vocabulary}</div>
        <div className="text-xs opacity-30 mb-3">{t.vocabularyHint}</div>
        <textarea value={vocab} onChange={e => setVocab(e.target.value)} rows={4}
          className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm resize-none focus:outline-none focus:border-white/20 transition-colors"
          placeholder="Lucas, Vincennes, Mont d'Or..." />
        <button onClick={saveVocab} className="mt-2 px-4 py-2 rounded-lg text-sm border border-white/10 hover:border-white/20 transition-colors">
          {vocabSaved ? `✓ ${t.saved}` : t.save}
        </button>
      </div>
      <div className="mb-8">
        <div className="text-xs uppercase tracking-widest opacity-40 mb-1">{t.userProfile}</div>
        <div className="text-xs opacity-30 mb-3">{t.profileHint}</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <input
            value={profile.first_name}
            onChange={e => setProfile(prev => ({ ...prev, first_name: e.target.value }))}
            className="bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-white/20 transition-colors"
            placeholder={t.firstName}
          />
          <input
            value={profile.last_name}
            onChange={e => setProfile(prev => ({ ...prev, last_name: e.target.value }))}
            className="bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-white/20 transition-colors"
            placeholder={t.lastName}
          />
          <input
            value={profile.pronouns}
            onChange={e => setProfile(prev => ({ ...prev, pronouns: e.target.value }))}
            className="bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-white/20 transition-colors"
            placeholder={`${t.pronouns} (${t.pronounsHint})`}
          />
          <input
            type="date"
            value={profile.birthday}
            onChange={e => setProfile(prev => ({ ...prev, birthday: e.target.value }))}
            className="bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-white/20 transition-colors"
          />
          <input
            value={profile.pet}
            onChange={e => setProfile(prev => ({ ...prev, pet: e.target.value }))}
            className="bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-white/20 transition-colors md:col-span-2"
            placeholder={t.pet}
          />
          <input
            value={profile.closest_relative}
            onChange={e => setProfile(prev => ({ ...prev, closest_relative: e.target.value }))}
            className="bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-white/20 transition-colors"
            placeholder={t.closestRelative}
          />
          <input
            value={profile.closest_relative_status}
            onChange={e => setProfile(prev => ({ ...prev, closest_relative_status: e.target.value }))}
            className="bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-white/20 transition-colors"
            placeholder={t.relativeStatus}
          />
          <textarea
            value={profile.other_notes}
            onChange={e => setProfile(prev => ({ ...prev, other_notes: e.target.value }))}
            rows={3}
            className="bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm resize-none focus:outline-none focus:border-white/20 transition-colors md:col-span-2"
            placeholder={t.otherNotes}
          />
        </div>
        <button onClick={saveProfile} className="mt-2 px-4 py-2 rounded-lg text-sm border border-white/10 hover:border-white/20 transition-colors">
          {profileSaved ? `✓ ${t.saved}` : t.save}
        </button>
      </div>
      <div className="mb-8">
        <div className="text-xs uppercase tracking-widest opacity-40 mb-3">API Key</div>
        <input type="password" defaultValue={getApiKey()} onChange={e => localStorage.setItem("api_key", e.target.value)}
          className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-white/20 transition-colors" placeholder="••••••••••••••••" />
      </div>

      {showHelp && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center"
          style={{ background: "rgba(0,0,0,0.55)", backdropFilter: "blur(4px)", paddingBottom: "80px" }}
          onClick={() => setShowHelp(false)}
        >
          <div
            className="w-full max-w-lg p-6 rounded-t-2xl max-h-[80vh] overflow-y-auto"
            style={{ background: "var(--surface)", borderTop: "1px solid var(--border)" }}
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-light" style={{ fontFamily: "'Playfair Display', Georgia, serif" }}>{t.help}</h2>
              <button onClick={() => setShowHelp(false)} className="opacity-40 hover:opacity-100 transition-opacity text-xl">×</button>
            </div>

            {lang === "fr" ? (
              <div className="text-sm leading-relaxed space-y-4 opacity-85">
                <section>
                  <div className="text-xs uppercase tracking-widest opacity-50 mb-1">Journal</div>
                  <p>Ouvre une entrée pour lire le texte, écouter l'audio, corriger, taguer et interpréter le rêve.</p>
                </section>
                <section>
                  <div className="text-xs uppercase tracking-widest opacity-50 mb-1">Interprétations</div>
                  <p>Chaque interprète peut être lancé séparément. Si une génération échoue, un message d'erreur s'affiche dans la vue du rêve.</p>
                </section>
                <section>
                  <div className="text-xs uppercase tracking-widest opacity-50 mb-1">Date du rêve</div>
                  <p>Tu peux définir la date au moment de la création, puis la modifier plus tard dans le détail d'une entrée.</p>
                </section>
                <section>
                  <div className="text-xs uppercase tracking-widest opacity-50 mb-1">Notifications</div>
                  <p>Active les notifications pour être averti quand une transcription est prête.</p>
                </section>
                <section>
                  <div className="text-xs uppercase tracking-widest opacity-50 mb-1">Confidentialité locale</div>
                  <p>La langue, le thème et la clé API sont stockés localement sur cet appareil.</p>
                </section>
              </div>
            ) : (
              <div className="text-sm leading-relaxed space-y-4 opacity-85">
                <section>
                  <div className="text-xs uppercase tracking-widest opacity-50 mb-1">Journal</div>
                  <p>Open an entry to read text, play audio, correct transcript, tag, and generate interpretations.</p>
                </section>
                <section>
                  <div className="text-xs uppercase tracking-widest opacity-50 mb-1">Interpretations</div>
                  <p>Each interpreter can be triggered separately. If generation fails, an explicit error message is shown in the dream view.</p>
                </section>
                <section>
                  <div className="text-xs uppercase tracking-widest opacity-50 mb-1">Dream Date</div>
                  <p>You can set dream date during creation and edit it later from entry details.</p>
                </section>
                <section>
                  <div className="text-xs uppercase tracking-widest opacity-50 mb-1">Notifications</div>
                  <p>Enable notifications to get alerted when a transcription is ready.</p>
                </section>
                <section>
                  <div className="text-xs uppercase tracking-widest opacity-50 mb-1">Local Privacy</div>
                  <p>Language, theme, and API key preferences are stored locally on this device.</p>
                </section>
              </div>
            )}

            <button
              onClick={() => setShowHelp(false)}
              className="mt-5 w-full py-3 rounded-xl text-sm border border-white/10 hover:border-white/20 transition-colors"
            >
              {t.close}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ── ComposeModal ──────────────────────────────────────────────────────────────
function ComposeModal({ lang, onClose, onSaved }) {
  const t = translations[lang]
  const [mode, setMode] = useState(null)
  const [text, setText] = useState("")
  const [dreamDate, setDreamDate] = useState(toDateTimeLocalValue())
  const [saving, setSaving] = useState(false)
  const [recording, setRecording] = useState(false)
  const [mediaRecorder, setMediaRecorder] = useState(null)

  async function saveText() {
    if (!text.trim()) return
    setSaving(true)
    const dreamDateIso = dreamDate ? new Date(dreamDate).toISOString() : null
    try { await apiFetch("/entries/manual", { method: "POST", body: JSON.stringify({ text, dream_date: dreamDateIso }) }); onSaved(); onClose() }
    catch { setSaving(false) }
  }

  async function startRecording() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const mimeType = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : MediaRecorder.isTypeSupported("audio/mp4") ? "audio/mp4" : ""
    const mr = new MediaRecorder(stream, mimeType ? { mimeType } : {})
    const audioChunks = []
    mr.ondataavailable = e => { if (e.data && e.data.size > 0) audioChunks.push(e.data) }
    mr.onstop = async () => {
      const blob = new Blob(audioChunks, { type: mr.mimeType || "audio/mp4" })
      stream.getTracks().forEach(t => t.stop())
      if (blob.size < 500) { alert("Recording empty"); onClose(); return }
      const ext = blob.type.includes("mp4") ? "mp4" : "webm"
      const now = new Date()
      const timestamp = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,"0")}-${String(now.getDate()).padStart(2,"0")}_${String(now.getHours()).padStart(2,"0")}h${String(now.getMinutes()).padStart(2,"0")}`
      const form = new FormData()
      form.append("audio", blob, `audio.${ext}`)
      form.append("timestamp", timestamp)
      form.append("duration_seconds", "0")
      if (dreamDate) form.append("dream_date", new Date(dreamDate).toISOString())
      try {
        const res = await fetch(`${API_BASE}/upload`, { method: "POST", headers: { "X-API-Key": localStorage.getItem("api_key") || "" }, body: form })
        if (res.ok) { onSaved(); onClose() } else alert("Upload failed: " + res.status)
      } catch(e) { alert("Upload error: " + e.message) }
    }
    mr.start(1000); setMediaRecorder(mr); setRecording(true)
  }

  function stopRecording() { mediaRecorder?.stop(); setRecording(false) }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center" style={{ background: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)" }}>
      <div className="w-full max-w-lg rounded-t-2xl p-6" style={{ background: "var(--surface)", borderTop: "1px solid var(--border)" }}>
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-light" style={{ fontFamily: "'Playfair Display', Georgia, serif" }}>{lang === "fr" ? "Nouveau rêve" : "New dream"}</h2>
          <button onClick={onClose} className="opacity-40 hover:opacity-100 transition-opacity text-xl">×</button>
        </div>
        <div className="mb-5">
          <div className="text-xs uppercase tracking-widest opacity-40 mb-2">{t.dreamDate}</div>
          <div className="text-xs opacity-30 mb-2">{t.dreamDateHint}</div>
          <input
            type="datetime-local"
            value={dreamDate}
            onChange={e => setDreamDate(e.target.value)}
            className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-white/20 transition-colors"
          />
        </div>
        {!mode && (
          <div className="flex gap-3">
            <button onClick={() => setMode("write")} className="flex-1 py-6 rounded-xl border border-white/10 hover:border-white/20 transition-colors flex flex-col items-center gap-2">
              <span className="text-2xl">✍</span>
              <span className="text-sm opacity-60">{lang === "fr" ? "Écrire" : "Write"}</span>
            </button>
            <button onClick={async () => { setMode("record"); try { await startRecording() } catch(e) { alert(e.message || "Mic denied"); setMode(null) } }}
              className="flex-1 py-6 rounded-xl border border-white/10 hover:border-white/20 transition-colors flex flex-col items-center gap-2">
              <span className="text-2xl">🎙</span>
              <span className="text-sm opacity-60">{lang === "fr" ? "Enregistrer" : "Record"}</span>
            </button>
          </div>
        )}
        {mode === "write" && (
          <div>
            <textarea autoFocus value={text} onChange={e => setText(e.target.value)} rows={6}
              className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm resize-none focus:outline-none focus:border-white/20 transition-colors mb-4"
              placeholder={lang === "fr" ? "Décris ton rêve..." : "Describe your dream..."} style={{ fontFamily: "'Lora', Georgia, serif", lineHeight: "1.8" }} />
            <button onClick={saveText} disabled={!text.trim() || saving} className="w-full py-3 rounded-xl text-sm border border-white/20 hover:border-white/30 transition-colors disabled:opacity-30">
              {saving ? "…" : (lang === "fr" ? "Sauvegarder" : "Save")}
            </button>
          </div>
        )}
        {mode === "record" && (
          <div className="flex flex-col items-center py-6 gap-4">
            <div className="w-16 h-16 rounded-full flex items-center justify-center"
              style={{ background: recording ? "#ef444420" : "transparent", border: `2px solid ${recording ? "#ef4444" : "var(--border)"}` }}>
              <span className={`text-2xl ${recording ? "animate-pulse" : ""}`}>{recording ? "⏺" : "🎙"}</span>
            </div>
            <p className="text-sm opacity-50">{recording ? (lang === "fr" ? "Enregistrement en cours…" : "Recording…") : (lang === "fr" ? "Prêt" : "Ready")}</p>
            {recording && (
              <button onClick={stopRecording} className="px-6 py-3 rounded-xl text-sm border border-white/20 hover:border-white/30 transition-colors">
                {lang === "fr" ? "Arrêter et envoyer" : "Stop and send"}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ── BottomNav ─────────────────────────────────────────────────────────────────
function BottomNav({ screen, setScreen, lang }) {
  const t = translations[lang]
  const items = [
    { id: "journal", label: t.journal, icon: "◈" },
    { id: "digest", label: t.digest, icon: "☾" },
    { id: "stats", label: t.stats, icon: "◉" },
    { id: "map", label: t.dreamMap, icon: "✦" },
    { id: "settings", label: t.settings, icon: "⚙" },
  ]
  return (
    <nav className="fixed bottom-0 left-0 right-0 border-t border-white/5 bg-[var(--bg)]/90 backdrop-blur-xl">
      <div className="flex max-w-lg mx-auto">
        {items.map(item => (
          <button key={item.id} onClick={() => setScreen(item.id)}
            className={`flex-1 flex flex-col items-center gap-1 py-3 text-xs transition-colors ${screen === item.id ? "text-white" : "text-white/30 hover:text-white/50"}`}>
            <span className="text-lg leading-none">{item.icon}</span>
            <span className="tracking-wider uppercase text-[10px]">{item.label}</span>
          </button>
        ))}
      </div>
    </nav>
  )
}

// ── App ───────────────────────────────────────────────────────────────────────
export default function App() {
  const [screen, setScreen]   = useState("journal")
  const [lang, setLang]       = useState(localStorage.getItem("lang") || "fr")
  const [theme, setTheme]     = useState(localStorage.getItem("theme") || "auto")
  const [compose, setCompose] = useState(false)
  const [refresh, setRefresh] = useState(0)

  useEffect(() => {
    const root = document.documentElement
    const mode = ["auto", "light", "dark"].includes(theme) ? theme : "auto"
    if (mode === "auto") {
      root.removeAttribute("data-theme")
      localStorage.setItem("theme", "auto")
      return
    }
    root.setAttribute("data-theme", mode)
  }, [theme])

  return (
    <div style={{ fontFamily: "'DM Sans', sans-serif" }}>
      <div className="max-w-lg mx-auto pb-20 min-h-screen">
        {screen === "journal"  && <JournalScreen lang={lang} key={refresh} />}
        {screen === "digest"   && <DigestScreen lang={lang} />}
        {screen === "stats"    && <StatsScreen lang={lang} />}
        {screen === "map"      && <DreamMapScreen lang={lang} />}
        {screen === "settings" && <SettingsScreen lang={lang} setLang={setLang} theme={theme} setTheme={setTheme} />}
      </div>
      <button onClick={() => setCompose(true)}
        className="fixed bottom-20 right-6 w-12 h-12 rounded-full flex items-center justify-center text-xl shadow-lg transition-transform hover:scale-110 active:scale-95 z-40"
        style={{ background: "var(--accent)", color: "var(--bg)" }}>+</button>
      <BottomNav screen={screen} setScreen={setScreen} lang={lang} />
      {compose && <ComposeModal lang={lang} onClose={() => setCompose(false)} onSaved={() => setRefresh(r => r + 1)} />}
    </div>
  )
}
