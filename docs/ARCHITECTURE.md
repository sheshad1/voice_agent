# Architecture

```mermaid
flowchart LR
    CSV[Lead sources<br/>ads, referrals, careers] --> LDB[(Leads)]
    LDB --> SCH[Scheduler<br/>working hours, retries, DND]
    SCH -->|instant outbound API| SAR[Sarvam Voice Agent<br/>Saaras, Sarvam LLM, Bulbul V4]
    SAR <-->|phone call| LEAD((Lead))
    SAR -->|knowledge base query| FAQ[Rider FAQ]
    SAR -->|get_slots, book_slot| API[FastAPI backend]
    SAR -->|on_end push| API
    SAR -->|call-status webhook| API
    API --> BK[Booking service]
    API --> CRM[CRM service]
    BK --> DB[(SQLite)]
    CRM --> DB
    CRM -->|callback, retry, DND| LDB
    DB --> DASH[Streamlit dashboard]
```

## Call lifecycle

```mermaid
sequenceDiagram
    participant S as Scheduler
    participant V as Sarvam agent
    participant B as Backend
    S->>V: place call (lead variables, language, greeting)
    V->>V: intent, vehicle, documents, city
    V->>B: GET /slots?city=
    B-->>V: serviceable + open slots
    V->>B: POST /bookings (answers + slot_id)
    B-->>V: booked or speakable rejection
    V->>B: on_end POST /crm/outcomes
    B->>B: recompute verdict, update lead
    V->>B: webhook call-status (fallback and telephony result)
```

## Where each rule lives

| Concern | Owner | Why |
| --- | --- | --- |
| Conversation, language, tone | Sarvam agent | What LLMs do well |
| Qualified or not | `qualification.py` | Identical answers always give the same verdict |
| Slot capacity, no double booking | `booking.py` | Atomic update; idempotent per `interaction_id` |
| Final outcome | `crm.py` | Agent claim is recorded but never trusted |
| Who to call, when | `scheduler.py`, `schedule.py` | Working hours, retries, call-back windows |
| Never call again | `dnd.py` | Checked before every dial |

## Failure handling

- Unanswered, busy or failed calls: retry after the back-off, clamped to working hours, up to the attempt cap, then the lead is marked exhausted.
- Webhook never arrives: leads stuck in `dialing` are re-queued after 30 minutes.
- Duplicate webhooks or CRM pushes: ignored, so attempts are never double counted.
- Backend or tool error mid-call: the agent apologises and records `follow_up_needed`.
