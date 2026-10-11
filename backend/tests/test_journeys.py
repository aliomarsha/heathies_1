"""Checks the behaviours the handbook's completion criteria ask for."""
from conftest import enrol, login, submit


def rhuh_id(c):
    return next(h["id"] for h in c.get("/api/hospitals").json() if h["slug"] == "rhuh")


def test_full_routine_journey_visible_to_every_role(client):
    c = client
    h, code = enrol(c)
    o = submit(c, h)
    assert o["recommendation"]["action"] == "routine_screening"
    assert o["recommendation"]["booking_eligible"] is True
    assert o["prediction"]["is_fixture"] is True

    o = c.post("/api/me/appointments", headers=h, json={"hospital_id": rhuh_id(c)}).json()
    appt = o["appointments"][0]
    assert appt["status"] == "requested"          # a request is not a booking
    assert o["journey"]["stage"] == "appointment_requested"

    pv = login(c, "rhuh.desk")
    # attendance cannot be recorded before the hospital confirms
    assert c.post(f"/api/provider/appointments/{appt['id']}/attendance", headers=pv, json={"attended": True}).status_code == 409
    assert c.post(f"/api/provider/appointments/{appt['id']}/confirm", headers=pv, json={"date": "2026-12-01", "time": "10:00"}).status_code == 200
    # finding cannot be recorded before verified attendance
    bad = c.post(f"/api/provider/appointments/{appt['id']}/finding", headers=pv,
                 json={"state": "negative_benign", "next_step": "routine_review", "next_review_date": "2027-12-01", "clinician_name": "Dr X"})
    assert bad.status_code == 409
    c.post(f"/api/provider/appointments/{appt['id']}/attendance", headers=pv, json={"attended": True})
    # a routine review needs a clinician-set date
    nodate = c.post(f"/api/provider/appointments/{appt['id']}/finding", headers=pv,
                    json={"state": "negative_benign", "next_step": "routine_review", "clinician_name": "Dr X"})
    assert nodate.status_code == 422
    ok = c.post(f"/api/provider/appointments/{appt['id']}/finding", headers=pv,
                json={"state": "negative_benign", "next_step": "routine_review", "next_review_date": "2027-12-01",
                      "clinician_name": "Dr X", "clinical_note": "secret note"})
    assert ok.status_code == 200

    me = c.get("/api/me/overview", headers=h).json()
    assert me["journey"]["stage"] == "next_step_recorded"
    assert me["finding"]["next_review_date"] == "2027-12-01"
    assert "clinical_note" not in me["finding"]

    gov = login(c, "programme")
    row = next(r for r in c.get("/api/gov/worklist", headers=gov).json() if r["code"] == code)
    assert row["journey"]["stage"] == "next_step_recorded"
    rec = c.get(f"/api/gov/participants/{row['id']}", headers=gov).json()
    assert rec["finding"]["state"] == "negative_benign"
    assert "clinical_note" not in rec["finding"]           # programme staff do not see clinical notes
    assert rec["audit"], "changes must be logged"
    assert any(l["actor"] == "rhuh.desk" and l["action"] == "finding_recorded" for l in rec["audit"])


def test_symptom_cannot_be_overridden_by_low_score_or_model_failure(client):
    c = client
    h, _ = enrol(c)
    o = submit(c, h, q_age=33, q_symptoms=["lump"], q_symptom_duration="not_checked", q_menopause="pre", q_hormone_therapy=None,
               q_last_mammogram="under_1y")
    assert o["recommendation"]["action"] == "clinical_assessment"
    assert o["recommendation"]["priority"] == "high"

    c.post("/api/demo/model-failure", json={"enabled": True})
    h2, _ = enrol(c)
    o2 = submit(c, h2, q_age=33, q_symptoms=["skin_change"], q_symptom_duration="not_checked", q_menopause="pre", q_hormone_therapy=None)
    assert o2["prediction"]["status"] != "ok"
    assert o2["prediction"]["band"] is None
    assert o2["recommendation"]["action"] == "clinical_assessment"


def test_model_failure_is_pending_never_low(client):
    c = client
    c.post("/api/demo/model-failure", json={"enabled": True})
    h, code = enrol(c)
    o = submit(c, h)
    assert o["prediction"]["status"] == "unavailable" and o["prediction"]["band"] is None
    assert "MODEL_RESULT_PENDING" in o["recommendation"]["reason_codes"]
    assert o["recommendation"]["booking_eligible"] is True       # eligibility comes from rules, not the model
    gov = login(c, "programme")
    row = next(r for r in c.get("/api/gov/worklist", headers=gov).json() if r["code"] == code)
    assert "result_pending" in row["journey"]["flags"]
    rec = c.get(f"/api/gov/participants/{row['id']}", headers=gov).json()
    assert any(t["kind"] == "staff_review" and t["status"] == "open" for t in rec["tasks"])


def test_unknown_critical_answers_route_to_clarification(client):
    c = client
    h, _ = enrol(c)
    o = submit(c, h, q_age="unknown", q_symptoms=["unknown"])
    assert o["recommendation"]["action"] == "clarification"
    assert o["recommendation"]["booking_eligible"] is False
    r = c.post("/api/me/appointments", headers=h, json={"hospital_id": rhuh_id(c)})
    assert r.status_code == 409


def test_higher_band_only_adds_review(client):
    c = client
    h, _ = enrol(c)
    o = submit(c, h, q_family_maternal="yes", q_family_paternal="yes", q_symptoms=["none"], q_hormone_therapy="current",
               q_menarche="under_12", q_first_birth="no_births")
    assert o["prediction"]["band"] == "higher"
    assert o["recommendation"]["action"] == "routine_screening"
    assert o["recommendation"]["clinician_review"] is True


def test_draft_resume_and_validation(client):
    c = client
    h, code = enrol(c)
    c.get("/api/me/assessment", headers=h)
    c.put("/api/me/assessment", headers=h, json={"answers": {"q_age": 47, "q_governorate": "south", "q_bogus": "x"}, "current_step": 2})
    r = c.post("/api/me/assessment/submit", headers=h)
    assert r.status_code == 422 and "missing" in r.json()["detail"]
    # sign in again with code + PIN and resume
    t = c.post("/api/auth/participant-login", json={"code": code, "pin": "1111"}).json()["token"]
    d = c.get("/api/me/assessment", headers={"Authorization": "Bearer " + t}).json()["draft"]
    assert d["answers"] == {"q_age": 47, "q_governorate": "south"} and d["current_step"] == 2


def test_role_permissions(client):
    c = client
    h, _ = enrol(c)
    assert c.get("/api/gov/worklist", headers=h).status_code == 403
    assert c.get("/api/provider/appointments", headers=h).status_code == 403
    pv = login(c, "rhuh.desk")
    assert c.get("/api/gov/worklist", headers=pv).status_code == 403
    gov = login(c, "programme")
    assert c.get("/api/provider/appointments", headers=gov).status_code == 403
    assert c.get("/api/me/overview", headers=gov).status_code == 403
    # a provider cannot open a participant who has no appointment at their hospital
    hala = next(r for r in c.get("/api/gov/worklist", headers=gov).json() if r["code"] == "HL-1004")
    assert c.get(f"/api/provider/participants/{hala['id']}", headers=pv).status_code == 404
    assert c.get(f"/api/provider/participants/{hala['id']}", headers=login(c, "baabda.desk")).status_code == 200
    assert c.get("/api/gov/worklist").status_code == 401


def test_follow_up_stays_open_and_biopsy_not_announced(client):
    c = client
    h, code = enrol(c)
    submit(c, h)
    a = c.post("/api/me/appointments", headers=h, json={"hospital_id": rhuh_id(c)}).json()["appointments"][0]
    pv = login(c, "rhuh.desk")
    c.post(f"/api/provider/appointments/{a['id']}/confirm", headers=pv, json={"date": "2026-11-01", "time": "09:00"})
    c.post(f"/api/provider/appointments/{a['id']}/attendance", headers=pv, json={"attended": True})
    c.post(f"/api/provider/appointments/{a['id']}/finding", headers=pv,
           json={"state": "incomplete_suspicious", "next_step": "biopsy", "clinician_name": "Dr Y"})
    me = c.get("/api/me/overview", headers=h).json()
    assert "follow_up_open" in me["journey"]["flags"]          # attendance did not close follow-up
    c.post(f"/api/provider/appointments/{a['id']}/finding", headers=pv,
           json={"state": "biopsy_confirmed", "next_step": "specialist_referral", "clinician_name": "Dr Y"})
    me = c.get("/api/me/overview", headers=h).json()
    assert me["finding"]["state"] == "care_team_will_contact"
    assert "biopsy" not in str(me["timeline"]) and "biopsy" not in str(me["finding"])
    gov = login(c, "programme")
    m = c.get("/api/gov/metrics", headers=gov).json()
    assert m["feedback_records"] >= 2


def test_missed_appointment_is_barrier_not_refusal_and_staff_can_rebook(client):
    c = client
    gov = login(c, "programme")
    samira = next(r for r in c.get("/api/gov/worklist", headers=gov).json() if r["code"] == "HL-1003")
    assert "missed_appointment" in samira["journey"]["flags"] and not samira["opted_out"]
    halba = next(h["id"] for h in c.get("/api/hospitals").json() if h["slug"] == "halba")
    r = c.post(f"/api/gov/participants/{samira['id']}/barrier", headers=gov,
               json={"barrier": "transport", "new_hospital_id": halba, "note": "closer to home"})
    assert r.status_code == 200 and r.json()["appointment"]["status"] == "requested"
    rec = c.get(f"/api/gov/participants/{samira['id']}", headers=gov).json()
    assert rec["journey"]["stage"] == "appointment_requested"
    assert not any(t["kind"] == "barrier_support" and t["status"] == "open" for t in rec["tasks"])


def test_outreach_simulation_rules(client):
    c = client
    gov = login(c, "programme")
    h, code = enrol(c)
    pid = next(r["id"] for r in c.get("/api/gov/worklist", headers=gov).json() if r["code"] == code)

    def events():
        return [e for e in c.get("/api/gov/outreach", headers=gov).json()["events"] if e["participant_id"] == pid]

    ev = events()
    assert ev and all(e["simulated"] for e in ev)
    assert {e["template"] for e in ev} == {"assessment_reminder"}
    assert all("cancer" not in e["body_preview"].lower() for e in ev)
    c.get("/api/gov/outreach", headers=gov)
    assert len(events()) == len(ev)                              # deduplicated

    submit(c, h)
    assert all(e["state"] == "cancelled" for e in events() if e["template"] == "assessment_reminder")

    a = c.post("/api/me/appointments", headers=h, json={"hospital_id": rhuh_id(c)}).json()["appointments"][0]
    assert any(e["template"] == "appointment_request_reminder" and e["state"] == "scheduled" for e in events())
    pv = login(c, "rhuh.desk")
    c.post(f"/api/provider/appointments/{a['id']}/confirm", headers=pv, json={"date": "2026-12-20", "time": "09:00"})
    ev = events()
    assert any(e["template"] == "confirmed_reminder" and e["state"] == "scheduled" for e in ev)
    assert all(e["state"] != "scheduled" for e in ev if e["template"] == "appointment_request_reminder")

    c.put("/api/me/contact", headers=h, json={"opted_out": True})
    assert all(e["state"] != "scheduled" for e in events())
    c.post("/api/demo/advance", json={"days": 30})
    assert not any(e["state"] == "simulated_sent" and e["template"] == "confirmed_reminder" for e in events())


def test_callback_task_after_reminder_sequence(client):
    c = client
    gov = login(c, "programme")
    # HL-1005 is the seeded campaign invitee with no response
    nour = next(r for r in c.get("/api/gov/worklist", headers=gov).json() if r["code"] == "HL-1005")
    rec = c.get(f"/api/gov/participants/{nour['id']}", headers=gov).json()
    assert any(t["kind"] == "callback" and t["status"] == "open" for t in rec["tasks"])
    assert any(e["template"] == "callback_task" and e["channel"] == "staff_call" for e in rec["outreach"])
    # opted-out participant: invitation went out before opt-out, nothing after
    zeina = next(r for r in c.get("/api/gov/worklist", headers=gov).json() if r["code"] == "HL-1007")
    zrec = c.get(f"/api/gov/participants/{zeina['id']}", headers=gov).json()
    assert any(e["state"] == "suppressed" for e in zrec["outreach"])
    assert not any(t["kind"] == "callback" for t in zrec["tasks"])


def test_metrics_have_honest_denominators(client):
    gov = login(client, "programme")
    m = client.get("/api/gov/metrics", headers=gov).json()
    f = {x["key"]: x for x in m["funnel"]}
    assert f["assessment_submitted"]["d"] == f["enrolled"]["n"]
    assert f["appointment_confirmed"]["d"] == f["appointment_requested"]["n"]
    assert f["next_step_recorded"]["d"] == f["attended_verified"]["n"]
