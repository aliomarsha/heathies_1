# Healthies: breast health follow-up platform (prototype)

Team Healthies, AUB health hackathon. This is Ali's part: the whole platform, frontend and backend.

> **Research prototype with fictional data.** Hospitals are proposed partners, not confirmed integrations. Model results are **labelled demo fixtures** until Wassim's model is connected. SMS is **simulated only**: no gateway exists and no message is ever sent. This is not an official Ministry of Public Health service.

## What it does

One shared care journey, seen from three roles:

| Role | Screens | What they can do |
|---|---|---|
| **Participant** (Arabic and English, mobile-first) | Consent and safe contact, branching questionnaire, next step, hospital directory, appointment, care history | Consent; choose how she can safely be contacted; answer MCQs (with "I'm not sure" and an optional text question); resume a saved draft with code and PIN; see her next step and the reason for it; request, reschedule or cancel an appointment; ask for help; opt out |
| **Hospital imaging desk** (provider) | Request queue and appointment record | Confirm or decline a request; mark attended or missed (with the reason); record the verified finding, the clinician-approved next step and the review date |
| **Programme / Ministry** (government) | Overview, worklist, tasks, outreach, participant record | Journey funnel with honest denominators; prioritised worklist; follow-up tasks; record barriers and request a closer hospital; contact attempts and opt-out; simulated SMS outbox; change log |

The **journey rail** (Joined, Assessment, Next step, Requested, Confirmed, Attended, Result & plan) appears in every role's view. Everyone reads a participant's position the same way, and a stuck step is shown in amber.

## Run it

**Easiest (Windows, macOS or Linux):** Python 3.10 or newer. The built frontend is already included, so Node.js is not needed.

```bash
./run.sh          # macOS / Linux
run.bat           # Windows
```

Open <http://localhost:8000>. The first start loads 12 fictional participants.

**Manual:**

```bash
pip install -r backend/requirements-dev.txt
cd backend
uvicorn app.main:app --reload            # http://localhost:8000
```

**Frontend development** (hot reload, with the API proxied to port 8000):

```bash
cd frontend && npm install && npm run dev   # http://localhost:5173
```

**Docker:** `docker build -t healthies . && docker run -p 8000:8000 healthies`

**Tests:** `cd backend && python -m pytest -q`. There are 36 tests: the handbook's journey checks plus the risk-profile privacy and safety checks.

## Deploy on Vercel (GitHub)

The repo deploys as **one Vercel project with two services** (`vercel.json` at the root):

| Service | Folder | Public path | What it is |
|---|---|---|---|
| `frontend` | `frontend/` | everything except `/api` | React (Vite) website, with deep links such as `/programme` falling back to `index.html` |
| `backend` | `backend/` | `/api/*` | FastAPI (`app.main:app`); receives the full path, e.g. `/api/meta` |

There are no internal bindings: the browser calls `/api/...` on the same domain, and the backend calls no other service.

1. Push this folder to GitHub. `vercel.json` must be at the top of the repository, next to `backend/` and `frontend/`.
2. In Vercel, click **Add New → Project**, import the repo, and click **Deploy**. Nothing else is needed: no environment variables and no `.env` file.
3. Open the URL. The demo data loads automatically on the first request.

**About the data on Vercel:** without a database, the app uses SQLite in `/tmp`. That is fine for a pitch, but data resets when Vercel starts a fresh instance, and two instances do not share data. To make data permanent and shared: in the Vercel project, open **Storage → Create → Neon (Postgres) → Connect**. Vercel injects `POSTGRES_URL` and the app uses it automatically (no code change). Then redeploy.

On Vercel the AI parts run in their cloud-safe mode: rules plus reviewed templates. A local Ollama/MedGemma cannot be reached from Vercel. Jev or Dr7.ai can be switched on later with environment variables (see `docs/HYBRID_AI.md`).

## Demo accounts (fictional)

| Who | Sign in | Password / PIN |
|---|---|---|
| Programme officer | `programme` (or `coordinator`) | `demo1234` |
| Rafik Hariri University Hospital desk | `rhuh.desk` | `demo1234` |
| Baabda hospital desk | `baabda.desk` (one `<slug>.desk` account per hospital) | `demo1234` |
| Participants | `HL-1001` to `HL-1012` on "I already have a code" | PIN `1234` |

The **Demo controls** button (bottom corner) offers quick sign-in, **advance time** (+1, +3 or +7 days, so reminders and callbacks fall due), **Simulate model outage** and **Reset demo data**. Set `HEALTHIES_DEMO_MODE=0` to hide and disable them.

### The seeded fictional cases (handbook demo cases)

| Code | Case |
|---|---|
| HL-1001 Rima | **Case 1**: due for screening, lower fixture band, request waiting for the hospital |
| HL-1002 Maya | **Case 2**: age 34 with a new lump. Clinical assessment and high priority, whatever her band |
| HL-1003 Samira | **Case 3**: missed her Beirut appointment because of transport. Barrier task open; staff can request Halba |
| HL-1004 Hala | **Case 4**: attended; incomplete/suspicious imaging. Follow-up stays open |
| HL-1005 Nour | **Case 5**: campaign invite with no response. Invitation and 2 reminders, then a staff callback task |
| HL-1006 Layla | Complete journey: negative imaging, clinician-set review date |
| HL-1007 Zeina | Opted out. Later reminders are suppressed |
| HL-1008 Rania | "Not sure" answers, so clarification. Prefers calls; left a free-text note |
| HL-1009 Dalal | Model outage at submission, so "pending / staff review" (never low risk) |
| HL-1010 Mona | Survey draft in progress. Sign in to see resume |
| HL-1011 Fatima | Confirmed upcoming appointment, with a reminder scheduled |
| HL-1012 Lina | Mammogram less than a year ago, so "recently screened" |

`docs/DEMO_SCRIPT.md` has a timed walkthrough. `docs/screenshots/` has the screens for Jad's deck.

## Connecting Wassim's model

The app never needs code changes for this. Read **`docs/MODEL_INTEGRATION.md`**. In short:

```bash
cp model/inference_template.py model/inference.py      # Wassim fills in predict()
python model/check_model.py --backend python           # contract and safety checks
HEALTHIES_MODEL_BACKEND=python ./run.sh                # or: set HEALTHIES_MODEL_BACKEND=python & run.bat
```

There are also `sklearn` (drop in `fitted_pipeline.joblib` and `model_config.json`) and `http` (a separate model service) options.

## Long-term risk profile (Dr7.ai / MedGemma)

After she submits, an **educational** risk-factor summary is generated in the background:
- a risk tier (Low, Average, Moderate or High);
- background factors she cannot change, habits she can change, and steps to discuss with a clinician.

It is built from a **de-identified, allow-listed** payload: age band only, and no name, phone, code, location or free text. If any identifier slips through, the call is blocked. It uses the OpenAI SDK's `.parse()` with a strict schema, and an output guard removes any diagnosis-like statement. It **never** changes the next step, priority or tasks.

The default is a labelled demo fixture. To run MedGemma **on your own PC** with no internet or key, install Ollama, run `ollama pull medgemma1.5`, then start the app with `run_with_local_ai.bat`. To use Dr7.ai's remote gateway instead, set `HEALTHIES_RISK_BACKEND=dr7` and `DR7_API_KEY`. See **`docs/RISK_PROFILE.md`**, and test with `python backend/scripts/check_dr7.py`.

## Hybrid AI: rules + Jev + MedGemma 1.5

For scale, the risk profile is built in layers:
- **rules** find the facts and set a minimum tier;
- **Jev** (TypeSafe, typed decisions) decides the tier and checks the free-text note;
- **MedGemma 1.5** on your GPU rewrites the facts in plain Arabic or English;
- a **cache** reuses identical results.

Jev can only raise the tier, and MedGemma can only reword; anything invalid falls back to rules or templates. Start it with `run_with_jev_and_medgemma.bat`. See **`docs/HYBRID_AI.md`**, including what must change for 6 million users.

## What the content team edits (no code)

| File | Owner | Contents |
|---|---|---|
| `backend/app/data/survey.json` | Jad (wording), Wassim (`model_feature` names) | Questions, Arabic/English text, options, "unknown" options, branching, which answers go to the model |
| `backend/app/data/policy_config.json` | Jad with the clinical mentor | Campaign age, what counts as "recently screened", critical questions. **Provisional** |
| `backend/app/data/hospitals.json` | Jad (task J3) | Hospitals, services, cost/coverage status, verification flag, simulated slots |
| `backend/app/data/outreach_templates.json` | Jad | SMS wording and the reminder schedule |
| `frontend/src/i18n.js` | Jad | All other interface text in both languages |

After editing, click **Reset demo data** or restart the server.

## Safety rules built in

- A symptom or an unresolved investigation always leads to clinical assessment, even with a low score or a recent mammogram.
- Personal history or a surveillance plan leads to clinician plan review. Unknown critical answers lead to clarification ("unknown" never means "no").
- An asymptomatic participant who is due can always request screening. The model can only **add** clinician review.
- A model failure or invalid output means "pending / staff review", with a staff task. The app never invents a low-risk result.
- A request is not a booking (the hospital confirms). A self-report is not verified attendance. A missed appointment opens a barrier task and is not treated as refusal. Attendance does not close an open follow-up.
- A biopsy-confirmed result is never announced on the website; the participant sees "your care team will contact you". A one-year review date only appears when a clinician enters it.
- Programme staff see finding categories and next steps but not clinical notes. Every change is logged with who made it.
- Opting out suppresses all future simulated contact. SMS bodies never contain results.
- Free text is stored for staff review and never sent to the model.

## Project layout

```
backend/
  app/
    main.py              FastAPI app (also serves frontend/dist)
    models.py            database tables (SQLite by default)
    ml/                  model contract, adapters (fixture/python/sklearn/http), feature builder
    policy/              action policy (rules, separate from the model)
    services/            care operations, journey state, outreach simulation, timeline
    routers/             participant, provider, government, public, demo APIs
    data/                survey, policy, hospitals and SMS templates (JSON, editable)
    seed.py              fictional demo data and reset
  tests/                 journey and safety tests
frontend/                React (Vite), bilingual RTL/LTR UI
model/                   drop-in folder for Wassim, plus template, checker and plumbing example
docs/                    model integration contract, demo script, screenshots
```

The API documentation is generated automatically at <http://localhost:8000/docs>.

## Not done yet (by design or still blocked)

- **Real model:** waiting for Wassim (fixtures are in use and labelled).
- **Live Dr7.ai risk profile:** needs your API key. Their docs don't confirm JSON-schema support, so run `check_dr7.py` once to see whether `parse` or the validated fallback is used.
- **Final survey wording and clinical thresholds:** waiting for Jad and the clinical review.
- **Hospital costs, services and phone numbers:** all marked "not yet verified".
- **Real SMS, real appointments and Ministry systems:** out of scope.
- **Authentication:** demo-grade code+PIN and password login. Replace it before any real pilot.
- **Branding:** the original mark is a placeholder. Add partner logos only once a partnership is approved.
