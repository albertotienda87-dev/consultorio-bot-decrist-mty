from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
from app.slot_locks import slot_lock
from app.google_calendar import (
    get_calendar_service,
    create_appointment_event,
    find_future_appointment_by_phone,
    reschedule_appointment_event,
    cancel_appointment_event,
    TIMEZONE,
)

APPOINTMENT_DURATION_MINUTES = 60
MIN_ADVANCE_DAYS = 2

# Horario laboral base del consultorio.
# Ajusta esto según la doctora.
WORKING_HOURS = {
    0: [("08:00", "21:00")],  # Lunes
    1: [("08:00", "21:00")],  # Martes
    2: [("08:00", "21:00")],  # Miércoles
    3: [("08:00", "21:00")],  # Jueves
    4: [("08:00", "21:00")],  # Viernes
    5: [("08:00", "21:00")],  # Sábado
    6: [("08:00", "21:00")],  # Domingo
}

def parse_time(value: str) -> time:
    hour, minute = value.split(":")
    return time(hour=int(hour), minute=int(minute))


def combine_date_time(day: date, time_value: str) -> datetime:
    return datetime.combine(
        day,
        parse_time(time_value),
        tzinfo=ZoneInfo(TIMEZONE)
    )


def get_today_local_date() -> date:
    return datetime.now(ZoneInfo(TIMEZONE)).date()


def get_min_bookable_date() -> date:
    return get_today_local_date() + timedelta(days=MIN_ADVANCE_DAYS)


def is_day_bookable(day: date) -> bool:
    return day >= get_min_bookable_date()


def generate_candidate_slots_for_day(day: date) -> list[datetime]:
    if not is_day_bookable(day):
        return []

    weekday = day.weekday()
    working_blocks = WORKING_HOURS.get(weekday, [])

    slots = []

    for block_start_str, block_end_str in working_blocks:
        block_start = combine_date_time(day, block_start_str)
        block_end = combine_date_time(day, block_end_str)

        current = block_start

        while current + timedelta(minutes=APPOINTMENT_DURATION_MINUTES) <= block_end:
            slots.append(current)
            current += timedelta(minutes=APPOINTMENT_DURATION_MINUTES)

    return slots


def get_busy_events_for_range(start_day: date, end_day: date) -> list[dict]:
    """
    end_day es inclusivo.
    Ejemplo: lunes a domingo.
    Internamente Google Calendar necesita timeMax exclusivo.
    """
    service = get_calendar_service()

    start_datetime = datetime.combine(
        start_day,
        time.min,
        tzinfo=ZoneInfo(TIMEZONE)
    )

    end_datetime = datetime.combine(
        end_day + timedelta(days=1),
        time.min,
        tzinfo=ZoneInfo(TIMEZONE)
    )

    events_result = service.events().list(
        calendarId="primary",
        timeMin=start_datetime.isoformat(),
        timeMax=end_datetime.isoformat(),
        singleEvents=True,
        orderBy="startTime"
    ).execute()

    return events_result.get("items", [])


def event_to_interval(event: dict):
    start_raw = event["start"].get("dateTime")
    end_raw = event["end"].get("dateTime")

    if start_raw and end_raw:
        start = datetime.fromisoformat(start_raw)
        end = datetime.fromisoformat(end_raw)
        return start, end

    start_date_raw = event["start"].get("date")
    end_date_raw = event["end"].get("date")

    if not start_date_raw or not end_date_raw:
        return None

    start_date = date.fromisoformat(start_date_raw)
    end_date = date.fromisoformat(end_date_raw)

    start = datetime.combine(
        start_date,
        time.min,
        tzinfo=ZoneInfo(TIMEZONE)
    )

    end = datetime.combine(
        end_date,
        time.min,
        tzinfo=ZoneInfo(TIMEZONE)
    )

    return start, end


def build_busy_intervals(events: list[dict]) -> list[tuple[datetime, datetime]]:
    busy_intervals = []

    for event in events:
        interval = event_to_interval(event)

        if interval:
            busy_intervals.append(interval)

    return busy_intervals


def intervals_overlap(
    start_a: datetime,
    end_a: datetime,
    start_b: datetime,
    end_b: datetime
) -> bool:
    return start_a < end_b and start_b < end_a


def is_slot_available(
    slot_start: datetime,
    slot_end: datetime,
    busy_intervals: list[tuple[datetime, datetime]]
) -> bool:
    for busy_start, busy_end in busy_intervals:
        if intervals_overlap(slot_start, slot_end, busy_start, busy_end):
            return False

    return True


def get_available_slots_for_day_with_busy_intervals(
    day: date,
    busy_intervals: list[tuple[datetime, datetime]]
) -> list[datetime]:
    candidate_slots = generate_candidate_slots_for_day(day)
    available_slots = []

    for slot_start in candidate_slots:
        slot_end = slot_start + timedelta(minutes=APPOINTMENT_DURATION_MINUTES)

        if is_slot_available(slot_start, slot_end, busy_intervals):
            available_slots.append(slot_start)

    return available_slots


def get_available_slots_for_range(start_day: date, end_day: date) -> dict[str, list[datetime]]:
    """
    Consulta Google Calendar UNA sola vez para todo el rango.
    Regresa:
    {
        "2026-05-25": [datetime(...), datetime(...)],
        "2026-05-26": [...]
    }
    """
    busy_events = get_busy_events_for_range(start_day, end_day)
    busy_intervals = build_busy_intervals(busy_events)

    result = {}

    current_day = start_day

    while current_day <= end_day:
        slots = get_available_slots_for_day_with_busy_intervals(
            current_day,
            busy_intervals
        )

        result[current_day.isoformat()] = slots
        current_day += timedelta(days=1)

    return result


def get_available_slots_for_day(day: date) -> list[datetime]:
    """
    Sigue existiendo para cuando solo necesitamos consultar un día.
    Ahora internamente usa la función por rango.
    """
    slots_by_day = get_available_slots_for_range(day, day)
    return slots_by_day.get(day.isoformat(), [])


def format_slot_title(slot: datetime) -> str:
    return slot.strftime("%I:%M %p").lstrip("0")


def build_time_rows_for_day(day: date) -> list[dict]:
    available_slots = get_available_slots_for_day(day)

    rows = []

    for slot in available_slots:
        rows.append({
            "id": f"slot_{slot.isoformat()}",
            "title": format_slot_title(slot),
            "description": "Disponible"
        })

    return rows


def parse_slot_id(slot_id: str) -> datetime | None:
    if not slot_id.startswith("slot_"):
        return None

    iso_value = slot_id.replace("slot_", "", 1)

    return datetime.fromisoformat(iso_value)

def is_slot_still_available(slot_id: str) -> bool:
    slot_start = parse_slot_id(slot_id)

    if not slot_start:
        return False

    slot_end = slot_start + timedelta(minutes=APPOINTMENT_DURATION_MINUTES)

    busy_events = get_busy_events_for_range(
        slot_start.date(),
        slot_start.date()
    )

    busy_intervals = build_busy_intervals(busy_events)

    return is_slot_available(
        slot_start,
        slot_end,
        busy_intervals
    )

def format_slot_from_id(slot_id: str) -> str:
    slot = parse_slot_id(slot_id)

    if not slot:
        return ""

    return format_slot_title(slot)

def book_calendar_appointment(
    patient_name: str,
    patient_phone: str,
    slot_id: str
):
    start_datetime = parse_slot_id(slot_id)

    if not start_datetime:
        raise ValueError("Invalid slot_id")

    with slot_lock(slot_id):
        if not is_slot_still_available(slot_id):
            raise ValueError("Slot is no longer available")

        return create_appointment_event(
            patient_name=patient_name,
            patient_phone=patient_phone,
            start_datetime=start_datetime,
            duration_minutes=APPOINTMENT_DURATION_MINUTES
        )


def patient_has_future_appointment(patient_phone: str) -> bool:
    existing_event = find_future_appointment_by_phone(patient_phone)
    return existing_event is not None

def reschedule_calendar_appointment(event_id: str, slot_id: str):
    start_datetime = parse_slot_id(slot_id)

    if not start_datetime:
        raise ValueError("Invalid slot_id")

    with slot_lock(slot_id):
        if not is_slot_still_available(slot_id):
            raise ValueError("Slot is no longer available")

        return reschedule_appointment_event(
            event_id=event_id,
            new_start_datetime=start_datetime,
            duration_minutes=APPOINTMENT_DURATION_MINUTES,
        )

def cancel_calendar_appointment(event_id: str):
    if not event_id:
        raise ValueError("Missing event_id")

    return cancel_appointment_event(event_id)