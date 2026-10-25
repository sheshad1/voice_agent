# Demo script (5 minutes)

## Before going on stage
- Backend and tunnel running; `.env` filled; dashboard open on a second screen.
- Two leads added with your own numbers: one Hindi, one English.
- A recorded call and screenshots ready in case the phone line fails.

## Flow
1. **Problem (30s).** Rider recruitment is a calling problem: volume spikes, cold evening leads, inconsistent outcomes.
2. **Design (30s).** Show the architecture diagram. The agent talks; the backend decides.
3. **Live Hindi call (90s).** `rider-agent dial-lead <number>`. Answer as a rider: interested, own a bike, documents ready. Ask "kitna kamayenge?" so the agent answers from the FAQ. Accept the first slot.
4. **Dashboard (30s).** Show the new booking, the outcome, and the transcript.
5. **Live English edge case (60s).** Say you have no bike. The agent ends politely, offers no slot, and the CRM shows `not_qualified: no_vehicle`.
6. **Reliability (60s).** Show the scheduler holding evening leads until 09:00, a no-answer retry, a do-not-call request, and the test suite (`pytest`, plus the Sarvam scenario run).

## Lines judges should hear
- "The CRM recomputes the verdict, so two calls with the same answers always get the same outcome."
- "The agent cannot book an unqualified lead; the API refuses."
- "Pay answers come only from the approved FAQ; otherwise it says the team will confirm."
