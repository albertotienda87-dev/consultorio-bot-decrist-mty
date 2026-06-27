from datetime import datetime
from zoneinfo import ZoneInfo

from app.google_calendar import (
    TIMEZONE,
    get_tomorrow_unconfirmed_appointments,
    mark_reminder_as_sent,
)
from app.whatsapp import send_appointment_reminder
from app.conversation import (
    extract_patient_name_from_event,
    format_event_date_es,
    format_event_time_es,
)

def extract_phone_from_event(event: dict) -> str | None:
    description = event.get("description", "") or ""

    for line in description.splitlines():
        if line.startswith("WhatsApp:"):
            return line.replace("WhatsApp:", "", 1).strip()

    return None

def send_tomorrow_appointment_reminders() -> dict:
    events = get_tomorrow_unconfirmed_appointments()

    sent_count = 0
    skipped_count = 0
    errors = []

    for event in events:
        event_id = event.get("id")
        phone = extract_phone_from_event(event)

        if not event_id or not phone:
            skipped_count += 1
            continue

        patient_name = extract_patient_name_from_event(event)
        appointment_date = format_event_date_es(event)
        appointment_time = format_event_time_es(event)

        try:
            response = send_appointment_reminder(
                phone=phone,
                patient_name=patient_name,
                appointment_date=appointment_date,
                appointment_time=appointment_time,
            )

            if 200 <= response.status_code < 300:
                mark_reminder_as_sent(event_id)
                sent_count += 1
            else:
                errors.append({
                    "event_id": event_id,
                    "phone": phone,
                    "status_code": response.status_code,
                    "response": response.text,
                })

        except Exception as e:
            errors.append({
                "event_id": event_id,
                "phone": phone,
                "error": str(e),
            })

    return {
        "checked_at": datetime.now(ZoneInfo(TIMEZONE)).isoformat(),
        "events_found": len(events),
        "sent_count": sent_count,
        "skipped_count": skipped_count,
        "errors": errors,
    }