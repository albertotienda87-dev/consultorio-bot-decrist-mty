from datetime import date, timedelta

from app.calendar_availability import (
    get_available_slots_for_range,
    get_min_bookable_date,
)


WEEKDAY_NAMES = {
    0: "Lunes",
    1: "Martes",
    2: "Miércoles",
    3: "Jueves",
    4: "Viernes",
    5: "Sábado",
    6: "Domingo"
}


MONTH_NAMES = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre"
}


def format_date_es(value: date) -> str:
    weekday = WEEKDAY_NAMES[value.weekday()]
    month = MONTH_NAMES[value.month]

    return f"{weekday} {value.day} de {month}"


def get_week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def get_available_weeks() -> list[dict]:
    """
    Optimizado:
    NO consulta Google Calendar.
    Solo muestra las próximas 6 semanas desde la fecha mínima agendable.
    """
    min_bookable_date = get_min_bookable_date()
    first_week_start = get_week_start(min_bookable_date)

    weeks = []

    for index in range(4):
        week_start = first_week_start + timedelta(weeks=index)
        week_end = week_start + timedelta(days=6)

        week_id = f"week_{week_start.isoformat()}"

        weeks.append({
            "id": week_id,
            "title": f"Semana {index + 1}",
            "description": (
                f"{week_start.day} {MONTH_NAMES[week_start.month]} - "
                f"{week_end.day} {MONTH_NAMES[week_end.month]}"
            ),
            "start_date": week_start.isoformat(),
            "end_date": week_end.isoformat()
        })

    return weeks


def find_week_by_id(week_id: str) -> dict | None:
    weeks = get_available_weeks()
    return next((week for week in weeks if week["id"] == week_id), None)


def get_available_days_for_week(week_id: str) -> list[dict]:
    """
    Optimizado:
    Consulta Google Calendar UNA sola vez para toda la semana.
    """
    week = find_week_by_id(week_id)

    if not week:
        return []

    week_start = date.fromisoformat(week["start_date"])
    week_end = date.fromisoformat(week["end_date"])

    slots_by_day = get_available_slots_for_range(week_start, week_end)

    days = []

    current_day = week_start

    while current_day <= week_end:
        available_slots = slots_by_day.get(current_day.isoformat(), [])

        if available_slots:
            day_id = f"day_{current_day.isoformat()}"

            days.append({
                "id": day_id,
                "title": format_date_es(current_day),
                "description": f"{len(available_slots)} horarios disponibles",
                "date": current_day.isoformat()
            })

        current_day += timedelta(days=1)

    return days


def find_day_by_id(week_id: str, day_id: str) -> dict | None:
    days = get_available_days_for_week(week_id)
    return next((day for day in days if day["id"] == day_id), None)


def parse_day_id(day_id: str) -> date | None:
    if not day_id or not day_id.startswith("day_"):
        return None

    raw_date = day_id.replace("day_", "", 1)

    return date.fromisoformat(raw_date)