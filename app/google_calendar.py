from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import json
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build

from app.config import (
    GOOGLE_CALENDAR_ID,
    GOOGLE_SERVICE_ACCOUNT_FILE,
    GOOGLE_SERVICE_ACCOUNT_JSON,
)

SCOPES = ["https://www.googleapis.com/auth/calendar"]

BASE_DIR = Path(__file__).resolve().parent.parent
SERVICE_ACCOUNT_FILE = BASE_DIR / GOOGLE_SERVICE_ACCOUNT_FILE

TIMEZONE = "America/Monterrey"

APPOINTMENT_STATUS_UNCONFIRMED = "No Confirmada"
APPOINTMENT_STATUS_CONFIRMED = "Confirmada"

def get_calendar_service():
    if GOOGLE_SERVICE_ACCOUNT_JSON:
        service_account_info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)

        credentials = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=SCOPES,
        )
    else:
        credentials = service_account.Credentials.from_service_account_file(
            str(SERVICE_ACCOUNT_FILE),
            scopes=SCOPES,
        )

    return build("calendar", "v3", credentials=credentials)


def list_upcoming_events(max_results: int = 10):
    service = get_calendar_service()

    now = datetime.now(ZoneInfo(TIMEZONE)).isoformat()

    events_result = service.events().list(
        calendarId=GOOGLE_CALENDAR_ID,
        timeMin=now,
        maxResults=max_results,
        singleEvents=True,
        orderBy="startTime"
    ).execute()

    return events_result.get("items", [])


def create_appointment_event(
    patient_name: str,
    patient_phone: str,
    start_datetime,
    duration_minutes: int = 30
):
    service = get_calendar_service()

    end_datetime = start_datetime + timedelta(minutes=duration_minutes)

    event = {
        "summary": f"Cita - {patient_name} [No confirmada]",
        "description": (
            f"Paciente: {patient_name}\n"
            f"WhatsApp: {patient_phone}\n"
            f"Status: {APPOINTMENT_STATUS_UNCONFIRMED}\n"
            f"Recordatorio Enviado: NO\n"
            f"Agendada por bot de WhatsApp."
        ),
        "start": {
            "dateTime": start_datetime.isoformat(),
            "timeZone": TIMEZONE,
        },
        "end": {
            "dateTime": end_datetime.isoformat(),
            "timeZone": TIMEZONE,
        },
    }

    return service.events().insert(
        calendarId=GOOGLE_CALENDAR_ID,
        body=event,
    ).execute()

def find_future_appointment_by_phone(patient_phone: str):
    service = get_calendar_service()

    now = datetime.now(ZoneInfo(TIMEZONE)).isoformat()

    events_result = service.events().list(
        calendarId=GOOGLE_CALENDAR_ID,
        timeMin=now,
        singleEvents=True,
        orderBy="startTime",
        q=patient_phone,
        maxResults=10,
    ).execute()

    events = events_result.get("items", [])

    active_events = [
        event for event in events
        if event.get("status") != "cancelled"
    ]

    if not active_events:
        return None

    return active_events[0]

def reschedule_appointment_event(event_id: str, new_start_datetime, duration_minutes: int = 30):
    service = get_calendar_service()

    new_end_datetime = new_start_datetime + timedelta(minutes=duration_minutes)

    event = service.events().get(
        calendarId=GOOGLE_CALENDAR_ID,
        eventId=event_id,
    ).execute()

    description = get_event_description(event)

    updated_description = replace_or_add_description_line(
        description,
        "Status",
        f"Status: {APPOINTMENT_STATUS_UNCONFIRMED}",
    )

    updated_description = replace_or_add_description_line(
        updated_description,
        "Recordatorio Enviado",
        "Recordatorio Enviado: NO",
    )

    summary = event.get("summary", "Cita")

    summary = (
        summary
        .replace("[No Confirmada]", "")
        .replace("[No confirmada]", "")
        .replace("[Confirmada]", "")
        .replace("[Confirmada]", "")
        .strip()
    )

    updated_summary = f"{summary} [No confirmada]"

    updated_event = {
        "summary": updated_summary,
        "description": updated_description,
        "start": {
            "dateTime": new_start_datetime.isoformat(),
            "timeZone": TIMEZONE,
        },
        "end": {
            "dateTime": new_end_datetime.isoformat(),
            "timeZone": TIMEZONE,
        },
    }

    return service.events().patch(
        calendarId=GOOGLE_CALENDAR_ID,
        eventId=event_id,
        body=updated_event,
    ).execute()

def cancel_appointment_event(event_id: str):
    service = get_calendar_service()

    return service.events().delete(
        calendarId=GOOGLE_CALENDAR_ID,
        eventId=event_id,
    ).execute()

def get_event_description(event: dict) -> str:
    return event.get("description", "") or ""


def get_appointment_status(event: dict) -> str | None:
    description = get_event_description(event)

    for line in description.splitlines():
        if line.startswith("Status:"):
            return line.replace("Status:", "", 1).strip()

    return None


def get_reminder_sent_status(event: dict) -> str | None:
    description = get_event_description(event)

    for line in description.splitlines():
        if line.startswith("Recordatorio Enviado:"):
            return line.replace("Recordatorio Enviado:", "", 1).strip()

    return None


def replace_or_add_description_line(description: str, key: str, new_line: str) -> str:
    lines = description.splitlines()
    updated_lines = []
    found = False

    for line in lines:
        if line.startswith(f"{key}:"):
            updated_lines.append(new_line)
            found = True
        else:
            updated_lines.append(line)

    if not found:
        updated_lines.append(new_line)

    return "\n".join(updated_lines)


def mark_appointment_as_confirmed(event_id: str):
    service = get_calendar_service()

    event = service.events().get(
        calendarId=GOOGLE_CALENDAR_ID,
        eventId=event_id,
    ).execute()

    description = get_event_description(event)

    updated_description = replace_or_add_description_line(
        description,
        "Status",
        f"Status: {APPOINTMENT_STATUS_CONFIRMED}",
    )

    summary = event.get("summary", "Cita")

    summary = (
        summary
        .replace("[No Confirmada]", "")
        .replace("[No confirmada]", "")
        .replace("[Confirmada]", "")
        .replace("[confirmada]", "")
        .strip()
    )

    updated_summary = f"{summary} [Confirmada]"

    body = {
        "summary": updated_summary,
        "description": updated_description,
    }

    return service.events().patch(
        calendarId=GOOGLE_CALENDAR_ID,
        eventId=event_id,
        body=body,
    ).execute()


def mark_reminder_as_sent(event_id: str):
    service = get_calendar_service()

    event = service.events().get(
        calendarId=GOOGLE_CALENDAR_ID,
        eventId=event_id,
    ).execute()

    description = get_event_description(event)

    updated_description = replace_or_add_description_line(
        description,
        "Recordatorio Enviado",
        "Recordatorio Enviado: SI",
    )

    body = {
        "description": updated_description,
    }

    return service.events().patch(
        calendarId=GOOGLE_CALENDAR_ID,
        eventId=event_id,
        body=body,
    ).execute()


def get_tomorrow_unconfirmed_appointments():
    service = get_calendar_service()

    now = datetime.now(ZoneInfo(TIMEZONE))
    tomorrow = now.date() + timedelta(days=1)

    start_datetime = datetime.combine(
        tomorrow,
        datetime.min.time(),
        tzinfo=ZoneInfo(TIMEZONE),
    )

    end_datetime = start_datetime + timedelta(days=1)

    events_result = service.events().list(
        calendarId=GOOGLE_CALENDAR_ID,
        timeMin=start_datetime.isoformat(),
        timeMax=end_datetime.isoformat(),
        singleEvents=True,
        orderBy="startTime",
        maxResults=250,
    ).execute()

    events = events_result.get("items", [])

    unconfirmed_events = []

    for event in events:
        if event.get("status") == "cancelled":
            continue

        appointment_status = get_appointment_status(event)
        reminder_sent = get_reminder_sent_status(event)

        if appointment_status != APPOINTMENT_STATUS_UNCONFIRMED:
            continue

        if reminder_sent == "SI":
            continue

        unconfirmed_events.append(event)

    return unconfirmed_events