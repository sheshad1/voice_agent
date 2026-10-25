# Swiggy Rider Onboarding Voice Agent

A Hindi and English voice agent on Sarvam Voice Agents that calls delivery-rider leads, qualifies them against a fixed checklist, answers pay questions from an approved FAQ, books an onboarding slot at a city centre, and reports every outcome to the CRM.

The agent holds the conversation. A Python backend owns everything that must be deterministic: the qualification verdict, slot inventory, booking guardrails, CRM records, call scheduling and compliance.

## Brief coverage

| Requirement | Where it is met |
| --- | --- |
| Call every lead within working hours | `scheduler.py` dials due leads 09:00-21:00 IST, queues evening leads for the next morning, retries no-answers with back-off |
| Lead's own language | Hindi or English per lead (`initial_language_name`, localised greeting), live language switch in the agent |
| Qualify against a checklist | `agent/instruction.md` walks intent, vehicle, documents, city; `qualification.py` is the single source of truth for the verdict (documents are recorded but never block, as the approved FAQ says none are needed to start) |
| Pay answers from approved material | Approved Rider FAQ (`agent/knowledge/rider_faq.csv`, verbatim); the instruction forbids answers outside it |
| Book a slot via API tool | `get_slots` and `book_slot` tools hit `/slots` and `/bookings` |
| Report to CRM on call end | `push_crm_outcome` runs as an `on_end` tool into `/crm/outcomes`, with the call webhook as a fallback |

## Design choices

- **Consistent outcomes.** The CRM recomputes the verdict from the captured answers and the booking table. If the agent claims `qualified_booked` without a booking, the record says `follow_up_needed` and the disagreement is counted on the dashboard.
- **Booking guardrails.** `/bookings` refuses unqualified leads, slots in another city, full or past slots, and is idempotent per call.
- **No missed call-backs.** Unanswered calls retry up to 3 times; a caller who asks for "evening" is called back in the evening window.
- **Compliance.** The agent discloses it is an AI, never quotes unapproved pay figures, and a do-not-call request blocks all future dials.
- **Fail closed.** The backend rejects every request when `BACKEND_API_KEY` is unset.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md).

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,dashboard]"
Copy-Item .env.example .env   # then fill in the values
.\.venv\Scripts\python.exe -m pytest
```

### 1. Backend

```powershell
rider-agent serve                       # http://127.0.0.1:8000
cloudflared tunnel --url http://127.0.0.1:8000   # or ngrok; put the URL in PUBLIC_BASE_URL
```

Sarvam's servers must reach the backend. If it sits behind a firewall, allow `4.213.167.70` and `35.154.84.150`.

### 2. Sarvam workspace

1. **Knowledge base:** create "Rider FAQ" from `agent/knowledge/rider_faq.csv`. Description: "Approved answers for delivery-partner leads: earnings per order and per km, onboarding fee, incentives, documents (PAN, licence, Aadhaar, bank account), delivery kit and insurance, shift options and how onboarding works. Search for any pay or how-it-works question. Not for personal account data."
2. **Secret:** in Settings > Secrets, store `BACKEND_API_KEY` as `rider_backend_api_key`.
3. **Agent:** create a single-state agent, paste `agent/instruction.md`, and add the variables from `agent/variables.yaml`.
4. **Tools:** create the three API tools from `agent/tools.yaml` (paste the `curl` to import). Mark `push_crm_outcome` as `on_end`. Test each with the Test button.
5. **Settings:** attach the knowledge base, enable language switching, voicemail detection and end-call, and pick the male Bulbul V4 voice "Shubh" for Hindi and English.
6. **Tests:** add the scenarios in `agent/tests/scenarios.yaml` and run them against the committed version.
7. **Deploy:** connect a phone number, then copy the app id, version, connection id and agent number into `.env`.

### 3. Run the pipeline

```powershell
rider-agent add-lead "Asha" 9876543210 Bengaluru --language Hindi
rider-agent dial-lead 9876543210        # demo: dials immediately
rider-agent run-scheduler --loop        # production: dials within working hours
streamlit run dashboard/app.py
```

Bulk load with `rider-agent import-leads leads.csv` (columns `name, phone, city, language, source`).

## Notes

- Centre names and slots are sample data seeded by `cities.py` and `booking.py`.
- Sarvam posts call results to `/webhooks/call-status?token=...`; `dial-lead` and the scheduler register that URL on every call.
