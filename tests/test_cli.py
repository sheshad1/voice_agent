from typer.testing import CliRunner

from rider_agent import cli, dnd, leads

runner = CliRunner()


def invoke(settings, monkeypatch, *args):
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    return runner.invoke(cli.app, list(args))


def test_add_lead_then_duplicate(settings, db, monkeypatch):
    first = invoke(settings, monkeypatch, "add-lead", "Asha", "9876543210", "Pune", "--language", "english")
    again = invoke(settings, monkeypatch, "add-lead", "Asha", "98765 43210", "Pune")
    assert "Added" in first.output
    assert "Already exists" in again.output
    assert leads.find_by_phone(db, "9876543210").language.value == "English"


def test_add_lead_rejects_unknown_language(settings, monkeypatch):
    result = invoke(settings, monkeypatch, "add-lead", "Asha", "9876543210", "Pune", "--language", "French")
    assert result.exit_code != 0


def test_import_leads_skips_invalid_rows(settings, db, monkeypatch, tmp_path):
    csv_file = tmp_path / "leads.csv"
    csv_file.write_text(
        "name,phone,city,language,source\n"
        "Asha,9876543210,Pune,Hindi,ads\n"
        "Bad,12345,Pune,Hindi,ads\n"
        "Asha again,9876543210,Pune,Hindi,ads\n",
        encoding="utf-8",
    )
    result = invoke(settings, monkeypatch, "import-leads", str(csv_file))
    assert "Imported 1 leads, skipped 2" in result.output


def test_dnd_and_stats(settings, db, monkeypatch):
    invoke(settings, monkeypatch, "add-lead", "Asha", "9876543210", "Pune")
    invoke(settings, monkeypatch, "add-dnd", "9876543210")
    assert dnd.is_dnd(db, "9876543210")
    assert "new" in invoke(settings, monkeypatch, "stats").output


def test_run_scheduler_with_no_leads_is_quiet(settings, monkeypatch):
    result = invoke(settings, monkeypatch, "run-scheduler")
    assert result.exit_code == 0
    assert result.output == ""


def test_seed_slots_reports_count(settings, monkeypatch):
    assert "Added" in invoke(settings, monkeypatch, "seed-slots", "--days", "2").output
