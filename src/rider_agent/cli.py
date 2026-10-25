"""Command-line entry point: serve the backend, manage leads, run the scheduler."""

import csv
import time
from pathlib import Path
from typing import Annotated

import typer

from rider_agent import booking, calls, dnd, leads, scheduler
from rider_agent.config import get_settings
from rider_agent.db import Database
from rider_agent.errors import DialerError
from rider_agent.models import Language
from rider_agent.sarvam_client import SarvamClient
from rider_agent.timeutil import utcnow

app = typer.Typer(no_args_is_help=True, help="Swiggy rider onboarding voice agent tooling.")


def _database() -> Database:
    database = Database(get_settings().db_path)
    database.init_schema()
    return database


def _language(raw: str) -> Language:
    try:
        return Language(raw.strip().capitalize())
    except ValueError:
        raise typer.BadParameter(f"Language must be Hindi or English, got {raw!r}") from None


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Runs the booking, CRM and webhook backend."""
    import uvicorn

    uvicorn.run("rider_agent.api.app:create_app", factory=True, host=host, port=port)


@app.command("add-lead")
def add_lead(
    name: str,
    phone: str,
    city: str,
    language: Annotated[str, typer.Option(help="Hindi or English")] = "Hindi",
    source: str = "manual",
) -> None:
    """Adds one lead to the call queue."""
    lead, created = leads.add_lead(_database(), name, phone, city, _language(language), source)
    typer.echo(f"{'Added' if created else 'Already exists'}: lead {lead.id} {lead.phone}")


@app.command("import-leads")
def import_leads(csv_path: Path) -> None:
    """Imports leads from a CSV with columns: name, phone, city, language, source."""
    database = _database()
    added = skipped = 0
    with csv_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            try:
                _, created = leads.add_lead(
                    database,
                    row["name"].strip(),
                    row["phone"],
                    (row.get("city") or "").strip() or None,
                    _language(row.get("language") or "Hindi"),
                    (row.get("source") or "csv").strip(),
                )
            except ValueError as exc:
                typer.echo(f"Skipped {row.get('phone')!r}: {exc}", err=True)
                skipped += 1
                continue
            added += created
            skipped += not created
    typer.echo(f"Imported {added} leads, skipped {skipped}.")


@app.command("add-dnd")
def add_dnd(phone: str) -> None:
    """Blocks a number from ever being dialed."""
    dnd.add_to_dnd(_database(), phone)
    typer.echo("Added to DND list.")


@app.command("seed-slots")
def seed_slots(days: int = 14) -> None:
    """Creates onboarding slots for the next N days."""
    added = booking.seed_slots(_database(), get_settings(), days=days)
    typer.echo(f"Added {added} slots.")


@app.command("run-scheduler")
def run_scheduler(
    loop: Annotated[bool, typer.Option(help="Keep running instead of a single pass")] = False,
    interval: Annotated[int, typer.Option(help="Seconds between passes")] = 60,
) -> None:
    """Dials due leads within working hours."""
    settings = get_settings()
    database = _database()
    dialer = SarvamClient(settings)
    while True:
        for result in scheduler.run_once(database, dialer, settings):
            status = result.error or f"attempt {result.attempt_id}"
            typer.echo(f"lead {result.lead_id}: {status}")
        if not loop:
            return
        time.sleep(interval)


@app.command("dial-lead")
def dial_lead(phone: str) -> None:
    """Immediately dials one lead (demo use; bypasses working hours)."""
    settings = get_settings()
    database = _database()
    lead = leads.find_by_phone(database, phone)
    if lead is None:
        raise typer.BadParameter("Lead not found; add it first with add-lead.")
    if dnd.is_dnd(database, lead.phone):
        raise typer.BadParameter("Number is on the DND list.")
    try:
        attempt_id = SarvamClient(settings).place_call(lead)
    except DialerError as exc:
        typer.echo(f"Dial failed: {exc}", err=True)
        raise typer.Exit(1) from None
    now = utcnow()
    calls.record_attempt(database, lead.id, attempt_id, now)
    leads.mark_dialing(database, lead.id, now)
    typer.echo(f"Call placed, attempt {attempt_id}")


@app.command()
def stats() -> None:
    """Prints lead counts by status."""
    for status, count in sorted(leads.status_counts(_database()).items()):
        typer.echo(f"{status:<10}{count}")


if __name__ == "__main__":
    app()
