# Hybrid AI: rules + Jev + MedGemma 1.5

Each part does only the job it is best at, so the result is fast, cheap at national scale, and
safe by construction.

```
survey answers
   │  de-identify (allow-list, age band, scrub, identifier gate)            app/risk/sanitize.py
   ▼
1. RULES   facts + rule-based tier (the safety floor)        free, instant  app/risk/service.py (_fixture)
2. JEV     decides the risk tier (typed choice + confidence)  ~0.1–0.5 s    app/decisions/
           checks the free-text note (breast change? barrier?)
3. MEDGEMMA 1.5 (on your PC via Ollama) rewrites the facts     few s (GPU)   app/risk/writer.py
           in plain Arabic/English – cannot change the tier or add factors
4. CACHE   identical de-identified answers reuse the stored result → no model call
   ▼
risk profile card (participant) + full audit trail (staff)
```

The care pathway itself (next step, priority, booking, follow-up) stays with the reviewed rules
and is **never** changed by any of these models.

## Safety contract (tested in `backend/tests/test_hybrid.py`)

| Rule | What happens |
|---|---|
| Jev can **raise** the tier, never lower it below the rule-based tier | `source = rules_floor` |
| Jev confidence < `JEV_MIN_CONFIDENCE` (0.5), timeout, outage, bad reply | rules tier is used, reason noted for staff |
| MedGemma returns a different number of items than the facts | that section uses the reviewed template text |
| MedGemma says anything diagnostic / reassuring / a percentage | that sentence is removed by the guard |
| MedGemma unreachable (Ollama off) | template text, page still works |
| Note triage | rules **and** Jev both run; either can add a staff-review task, neither can remove one |
| Identifiers | Jev and MedGemma only ever receive the de-identified payload; notes are scrubbed of name/phone/codes |

## Run it

```powershell
ollama pull medgemma1.5                  # once
$env:JEV_API_KEY = "your-jev-key"        # from TypeSafe (early access)
.\run_with_jev_and_medgemma.bat
```

Check the Jev connection on its own first: `cd backend; ..\.venv\Scripts\python.exe scripts\check_jev.py`.
TypeSafe has published the request format but not the full response format; `normalise()` in
`app/decisions/jev.py` accepts the likely shapes, and the script tells you if it needs adjusting.

| Variable | Default | Meaning |
|---|---|---|
| `HEALTHIES_RISK_BACKEND` | `hybrid` | `hybrid`, `local`, `dr7`, `fixture`, `off` |
| `HEALTHIES_DECISION_BACKEND` | `rules` | `jev` to use Jev (rules remain the floor/fallback) |
| `HEALTHIES_RISK_WRITER` | `local` | `local` (MedGemma/Ollama), `dr7`, `templates` |
| `JEV_API_KEY` / `JEV_URL` / `JEV_MODEL` | – / `https://api.typesafe.ai/v1/systemone` / `jev-latest` | Jev connection |
| `JEV_MIN_CONFIDENCE` | `0.5` | below this, the rules decide |
| `JEV_TRIAGE_THRESHOLD` | `0.3` | P(breast change) that adds a staff task (low on purpose) |
| `HEALTHIES_RISK_CACHE` | `1` | reuse identical results |

## Scaling to a national programme (≈ 6 million women)

What already scales:
- **Jev** is the cheap part: vendor pricing implies roughly 6,000,000 × ~$0.0004 ≈ **$2,400** for
  one decision per woman (vendor figures, unverified). With the cache, repeated answer patterns cost nothing.
- **Rules + cache** carry most of the load for free; most women share common answer combinations.
- All model calls run **after** the response, so a slow model never slows the website.

What must change before a national rollout (honest list):
1. **Database:** SQLite is for the demo. Set `HEALTHIES_DATABASE_URL=postgresql+psycopg://...` (and `pip install psycopg[binary]`).
2. **Background work:** move `run_in_background` to a worker queue (Celery/RQ/Redis) with several workers.
3. **MedGemma serving:** one RTX 5060 is perfect for the pilot, not for millions. Serve it on GPU
   servers (e.g. vLLM, same OpenAI-compatible API – only `LOCAL_LLM_BASE_URL` changes), or keep
   template text for most cases and use MedGemma only where wording matters.
4. **Dashboard queries:** the worklist and metrics currently load all participants in Python;
   they need SQL aggregation, pagination and indexes.
5. **Several app servers** behind a load balancer (`uvicorn --workers N` or gunicorn), real
   authentication (Ministry identity provider), backups and monitoring.
6. **Data governance:** Jev runs on TypeSafe's servers in the US (West Coast). Even with
   de-identification, the Ministry must approve sending health data abroad. MedGemma on
   Ministry-controlled GPUs keeps the wording step inside Lebanon.
7. **Validation:** Jev and MedGemma are general/medical models, not validated Lebanese risk
   calculators. Clinical review of tiers and wording is required before real use.
