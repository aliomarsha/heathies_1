# Live demo script (about 6 minutes, adapt to the pitch length)

Before you start, open **Demo controls** and click **Reset demo data**. Use two browser windows: one at phone width for the participant and one full width for staff.

## 1. Routine journey (2 min): the participant and the hospital

1. **Participant:** go to Landing, then **Start the assessment**, choose Arabic, consent and pick a safe contact method (for example "Text message", discreet), then set PIN `2468`. Point out the personal code.
2. Answer the questions: age 46, Mount Lebanon, no symptoms, "I don't know" for father's side, last mammogram more than 2 years ago, barrier: transport. Optionally go back to show that answers were saved.
3. The **next step** page reads "You can request a screening mammogram", with the reasons. The prototype estimate shows a band labelled "Demo values". Say: *"The band is a research estimate. The next step is what matters."*
4. Click **Choose a hospital**. Baabda appears first as near her. Cost reads "not yet confirmed" and slots are labelled simulated. Click **Send request**. The status says *requested, not booked yet*.
5. **Hospital** (`baabda.desk`): New requests, then the participant. Click **Confirm appointment**, then **Attended**, then record *Incomplete or suspicious imaging*, then *More imaging*, then a date and a clinician name.
6. **Participant**, after a reload: "The hospital asked for more tests. Many people who need more tests do not have cancer." The follow-up stays open.

## 2. Symptom override (1 min)

- **Programme** worklist, then **Maya (HL-1002)**: age 34, new lump, lower or intermediate band, yet the next step is **clinical assessment** with **high** priority. Say: *"A low score can never cancel a symptom referral."*

## 3. Barrier resolution (1 min)

- Worklist, then **Samira (HL-1003)**: missed appointment, reason transport, a barrier task, priority medium. Say: *"Missed is not refusal."*
- Click **Record a barrier**, choose transport, then *Request a closer hospital*, then Halba. The journey moves back to **Requested** and the task closes.

## 4. Follow-up and outreach (1.5 min)

- Overview: the funnel shows where people get stuck (each rate is out of the step before), plus open follow-ups and symptom cases seen.
- Outreach: the simulated outbox, labelled *Simulated SMS — no message sent*. Nour (HL-1005) got an invitation and 2 reminders, then a **staff callback task**. Zeina (HL-1007) opted out, so her reminders show as suppressed.
- **Demo controls, then +3 days:** scheduled reminders flip to "shown as sent (simulated)" and overdue tasks appear.

## 5. Safety (30 s, optional)

- **Demo controls, then Simulate model outage**, then submit a new participant. She sees "being reviewed by the care team" (never low risk), and a staff-review task appears.

## Fallback if live fails

Use the screenshots in `docs/screenshots/` in this order: 03, 06, 08, 09, 10, 11, 13, 19, 14, 15, 16, 17.

## Screenshot captions for Jad

| File | Caption |
|---|---|
| 01_landing_en / 02_landing_ar | Bilingual entry: start, resume, or staff sign-in |
| 03_enrol | Consent and safe contact preferences, chosen by the participant |
| 05_survey_validation | Clear prompts; "I'm not sure" is always available |
| 06_survey_symptoms | Symptom question with branching follow-up |
| 07_survey_review | Review before sending; answers saved as you go |
| 08_participant_result | The next step and why. The prototype band is clearly labelled, not a diagnosis |
| 09_hospitals | Hospital directory: nearest first, cost status honest, simulated availability |
| 10_participant_requested | A request is visibly different from a confirmed booking |
| 11_provider_requests / 12_provider_confirm | Hospital desk confirms the request |
| 13_provider_finding | Verified finding and clinician-approved next step |
| 19_participant_followup | Participant sees a safe explanation and the open follow-up |
| 14_programme_overview | Where participants get stuck, with honest denominators |
| 15_programme_worklist | Priority from care rules, not from the score alone |
| 16_programme_record_missed | Missed appointment: a barrier task, not refusal |
| 17_outreach | Simulated SMS outbox. No message is sent |
| 18_tasks | Staff follow-up tasks with owners and due dates |
| 20/21_mobile | Arabic, mobile: resume a saved assessment |
| 22_participant_risk_profile | Long-term risk factors, kept separate from the next step |
| 23_staff_risk_profile | Staff view: model, mode, prompt version and the exact de-identified payload sent |

All data, hospitals' availability, model outputs and messages shown are **fictional or simulated**.
