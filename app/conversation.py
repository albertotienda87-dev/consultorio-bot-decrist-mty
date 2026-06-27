from datetime import datetime
from app.state import user_states
from app.availability import (
    get_available_weeks,
    get_available_days_for_week,
    parse_day_id,
)
from app.calendar_availability import (
    build_time_rows_for_day,
    book_calendar_appointment,
    reschedule_calendar_appointment,
    cancel_calendar_appointment,
)

from app.google_calendar import (
    find_future_appointment_by_phone,
    mark_appointment_as_confirmed,
)

UNSUPPORTED_MESSAGE = "__unsupported_message__"

# -------------------------
# Helpers generales
# -------------------------

def unsupported_message_response(state) -> dict:
    if state == "awaiting_name":
        return safe_text_response(
            "Por ahora solo puedo recibir texto para registrar tu nombre.\n\n"
            "Por favor escribe tu nombre completo para continuar con la cita."
        )

    if isinstance(state, dict):
        step = state.get("step")

        if step in ["awaiting_week", "reschedule_awaiting_week"]:
            weeks = get_available_weeks()
            return invalid_week_response(weeks)

        if step in ["awaiting_day", "reschedule_awaiting_day"]:
            week_id = state.get("week_id")
            week_title = state.get("week_title", "Semana seleccionada")
            days = get_available_days_for_week(week_id)

            return invalid_day_response(week_title, days)

        if step in ["awaiting_time", "reschedule_awaiting_time"]:
            day_id, day_title, selected_date, time_rows = get_day_and_times_from_state(state)

            if selected_date and time_rows:
                return invalid_time_response(
                    day_title=day_title,
                    time_rows=time_rows,
                    period=state.get("time_period"),
                )

            return main_menu_button_response(
                "No pude recuperar los horarios disponibles.\n\n"
                "Puedes volver al menú principal para intentarlo de nuevo."
            )

        if step == "cancel_awaiting_confirmation":
            patient_name = state.get("existing_event_patient_name", "paciente")
            event_date = state.get("existing_event_date", "fecha no disponible")
            event_time = state.get("existing_event_time", "hora no disponible")

            return {
                "type": "cancel_confirmation",
                "message": (
                    f"Paciente: {patient_name}\n"
                    f"Fecha: {event_date}\n"
                    f"Hora: {event_time}\n\n"
                    "¿Confirmas que deseas cancelar esta cita?"
                ),
            }

        if step == "reschedule_awaiting_confirmation":
            patient_name = state.get("existing_event_patient_name", "paciente")
            event_date = state.get("existing_event_date", "fecha no disponible")
            event_time = state.get("existing_event_time", "hora no disponible")

            return {
                "type": "reschedule_confirmation",
                "message": (
                    f"Paciente: {patient_name}\n"
                    f"Fecha actual: {event_date}\n"
                    f"Hora actual: {event_time}\n\n"
                    "¿Confirmas que deseas reagendar esta cita?"
                ),
            }

    return invalid_main_menu_response()

def safe_text_response(message: str) -> dict:
    return {
        "type": "text",
        "message": message,
    }


def main_menu_response() -> dict:
    return {
        "type": "main_menu",
    }


def main_menu_button_response(message: str) -> dict:
    return {
        "type": "main_menu_button",
        "message": message,
    }


def multi_response(responses: list[dict]) -> dict:
    return {
        "type": "multi",
        "responses": responses,
    }


def normalize_text(value: str) -> str:
    if not value:
        return ""

    return (
        value.strip()
        .lower()
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ü", "u")
    )


def is_menu_request(text: str) -> bool:
    text_lower = normalize_text(text)

    keywords = [
        "hola",
        "buenos dias",
        "buen dia",
        "buenas tardes",
        "buenas noches",
        "menu",
        "inicio",
        "empezar",
        "start",
        "volver al menu",
    ]

    return any(keyword in text_lower for keyword in keywords)

def is_price_request(text: str) -> bool:
    text_lower = normalize_text(text)

    keywords = [
        "precio",
        "costo",
        "cuanto cuesta",
        "cuanto vale",
        "valor consulta",
        "precio consulta",
        "costo consulta",
        "consulta precio",
    ]

    return any(keyword in text_lower for keyword in keywords)

def is_location_request(text: str) -> bool:
    text_lower = normalize_text(text)

    keywords = [
        "ubicacion",
        "direccion",
        "donde estan",
        "donde se ubican",
        "consultorio",
        "maps",
        "google maps",
        "como llegar",
    ]

    return any(keyword in text_lower for keyword in keywords)

def is_schedule_request(text: str) -> bool:
    text_lower = normalize_text(text)

    keywords = [
        "agendar",
        "agenda",
        "cita",
        "consulta",
        "quiero cita",
        "sacar cita",
        "programar",
        "reservar",
    ]

    return any(keyword in text_lower for keyword in keywords)


def looks_like_valid_name(text: str) -> bool:
    text_clean = text.strip()

    if len(text_clean) < 3:
        return False

    invalid_keywords = [
        "hola",
        "menu",
        "cita",
        "agendar",
        "cancelar",
        "reagendar",
    ]

    text_lower = normalize_text(text_clean)

    if any(keyword in text_lower for keyword in invalid_keywords):
        return False

    return True


# -------------------------
# Datos de eventos
# -------------------------

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
    12: "diciembre",
}


def extract_patient_name_from_event(event: dict) -> str:
    description = event.get("description", "")
    summary = event.get("summary", "")

    for line in description.splitlines():
        if line.lower().startswith("paciente:"):
            return line.replace("Paciente:", "", 1).strip()

    if summary.lower().startswith("cita -"):
        return summary.replace("Cita -", "", 1).strip()

    if summary:
        return summary.strip()

    return "paciente"


def format_event_date_es(event: dict) -> str:
    start_data = event.get("start", {})
    raw_datetime = start_data.get("dateTime")
    raw_date = start_data.get("date")

    if raw_datetime:
        event_datetime = datetime.fromisoformat(raw_datetime)
        event_date = event_datetime.date()
    elif raw_date:
        event_date = datetime.fromisoformat(raw_date).date()
    else:
        return "fecha no disponible"

    month_name = MONTH_NAMES[event_date.month]

    return f"{event_date.day} de {month_name} de {event_date.year}"

def format_event_time_es(event: dict) -> str:
    start_data = event.get("start", {})
    raw_datetime = start_data.get("dateTime")

    if not raw_datetime:
        return "hora no disponible"

    event_datetime = datetime.fromisoformat(raw_datetime)

    return event_datetime.strftime("%I:%M %p").lstrip("0")

def duplicate_appointment_response(existing_event: dict) -> dict:
    patient_name = extract_patient_name_from_event(existing_event)
    event_date = format_event_date_es(existing_event)
    event_time = format_event_time_es(existing_event)

    return multi_response([
        safe_text_response(
            "Ya tienes una cita agendada.\n\n"
            f"Paciente: {patient_name}\n"
            f"Fecha: {event_date}\n"
            f"Hora: {event_time}"
        ),
        main_menu_button_response(
            "Para evitar duplicados, no es posible agendar otra cita desde este mismo número.\n\n"
            "Si necesitas cambiar o cancelar tu cita, vuelve al menú principal y selecciona la opción correspondiente."
        ),
    ])

# -------------------------
# Fallbacks específicos
# -------------------------

def invalid_week_response(weeks: list[dict]) -> dict:
    return multi_response([
        safe_text_response(
            "No pude identificar esa semana.\n\n"
            "Por favor selecciona una opción de la lista de semanas disponibles."
        ),
        {
            "type": "week_options",
            "weeks": weeks,
        },
    ])


def invalid_day_response(week_title: str, days: list[dict]) -> dict:
    return multi_response([
        safe_text_response(
            "No pude identificar ese día.\n\n"
            "Por favor selecciona una opción de la lista de días disponibles."
        ),
        {
            "type": "day_options",
            "selected_week_title": week_title,
            "days": days,
        },
    ])


def invalid_time_response(
    day_title: str,
    time_rows: list[dict],
    period: str | None = None,
) -> dict:
    return multi_response([
        safe_text_response(
            "No pude identificar ese horario.\n\n"
            "Por favor selecciona una opción de la lista de horarios disponibles."
        ),
        {
            "type": "time_options",
            "selected_day_title": day_title,
            "times": time_rows,
            "period": period,
        },
    ])

def invalid_main_menu_response() -> dict:
    return multi_response([
        safe_text_response(
            "No pude identificar esa opción.\n\n"
            "Por favor selecciona una opción del menú principal."
        ),
        main_menu_response(),
    ])

# -------------------------
# Resolvers estrictos
# -------------------------

def find_week_by_text(text: str, weeks: list[dict]) -> dict | None:
    text_lower = normalize_text(text)

    for week in weeks:
        week_id = week.get("id", "")
        week_title = normalize_text(week.get("title", ""))

        if text == week_id:
            return week

        if text_lower == week_title:
            return week

        if week_title.startswith("semana "):
            week_number = week_title.replace("semana ", "", 1).strip()

            if text_lower == week_number:
                return week

    return None


def find_day_by_text(text: str, days: list[dict]) -> dict | None:
    text_lower = normalize_text(text)

    for day in days:
        day_id = day.get("id", "")
        day_title = normalize_text(day.get("title", ""))

        if text == day_id:
            return day

        if text_lower == day_title:
            return day

    return None


def find_time_by_text(text: str, times: list[dict]) -> dict | None:
    text_lower = normalize_text(text)

    for time_row in times:
        time_id = time_row.get("id", "")
        time_title = normalize_text(time_row.get("title", ""))

        if text == time_id:
            return time_row

        if text_lower == time_title:
            return time_row

    return None


# -------------------------
# Responses de listas
# -------------------------

def week_options_response() -> dict:
    weeks = get_available_weeks()

    if not weeks:
        return main_menu_button_response(
            "Por el momento no hay semanas disponibles para agendar.\n\n"
            "Por favor intenta más tarde o contacta al consultorio."
        )

    return {
        "type": "week_options",
        "weeks": weeks,
    }


def day_options_response(week_id: str, week_title: str) -> dict:
    days = get_available_days_for_week(week_id)

    if not days:
        return multi_response([
            safe_text_response(
                "No encontré días disponibles en esa semana.\n\n"
                "Por favor selecciona otra semana."
            ),
            week_options_response(),
        ])

    return {
        "type": "day_options",
        "selected_week_title": week_title,
        "days": days,
    }


def time_options_response(
    day_id: str,
    day_title: str,
    period: str | None = None,
) -> dict:
    selected_date = parse_day_id(day_id)

    if not selected_date:
        return main_menu_button_response(
            "No pude recuperar el día seleccionado.\n\n"
            "Puedes volver al menú principal para intentarlo de nuevo."
        )

    times = build_time_rows_for_day(selected_date)

    if not times:
        return safe_text_response(
            "Ese día ya no tiene horarios disponibles. Por favor selecciona otro día."
        )

    return {
        "type": "time_options",
        "selected_day_title": day_title,
        "times": times,
        "period": period,
    }


# -------------------------
# Helpers de flujo
# -------------------------

def handle_period_selection(
    phone: str,
    text: str,
    state: dict,
    day_title: str,
    time_rows: list[dict],
) -> dict | None:
    if text == "time_period_morning":
        user_states[phone] = {
            **state,
            "time_period": "morning",
        }

        return {
            "type": "time_options",
            "selected_day_title": day_title,
            "times": time_rows,
            "period": "morning",
        }

    if text == "time_period_evening":
        user_states[phone] = {
            **state,
            "time_period": "evening",
        }

        return {
            "type": "time_options",
            "selected_day_title": day_title,
            "times": time_rows,
            "period": "evening",
        }

    return None


def get_day_and_times_from_state(state: dict):
    day_id = state.get("day_id")
    day_title = state.get("day_title", "Día seleccionado")
    selected_date = parse_day_id(day_id)

    if not selected_date:
        return day_id, day_title, None, []

    time_rows = build_time_rows_for_day(selected_date)

    return day_id, day_title, selected_date, time_rows


# -------------------------
# Handler principal
# -------------------------

def handle_user_message(phone: str, text: str) -> dict:
    text = text.strip()
    state = user_states.get(phone)

    if text == UNSUPPORTED_MESSAGE:
        return unsupported_message_response(state)

    # Siempre permitir volver al menú desde cualquier punto.
    if text == "back_main_menu" or is_menu_request(text):
        user_states[phone] = "main_menu"
        return main_menu_response()

    if text == "reminder_confirm_appointment":
        existing_event = find_future_appointment_by_phone(phone)

        if not existing_event:
            user_states[phone] = "main_menu"

            return main_menu_button_response(
                "No encontré una cita activa asociada a este número de WhatsApp.\n\n"
                "Puedes volver al menú principal para revisar las opciones disponibles."
            )

        try:
            mark_appointment_as_confirmed(existing_event.get("id"))

        except Exception as e:
            print("ERROR confirming appointment:", e)

            return main_menu_button_response(
                "No pude confirmar tu cita en este momento.\n\n"
                "Por favor intenta de nuevo o contacta directamente al consultorio."
            )

        patient_name = extract_patient_name_from_event(existing_event)
        event_date = format_event_date_es(existing_event)
        event_time = format_event_time_es(existing_event)

        user_states[phone] = "main_menu"

        return main_menu_button_response(
            "✅ Tu cita fue confirmada correctamente.\n\n"
            "Te esperamos en el consultorio."
        )

    if text == "reminder_reschedule_appointment":
        text = "reschedule_appointment"

    if text == "reminder_cancel_appointment":
        text = "cancel_appointment"

    if text == "office_location" or is_location_request(text):
        user_states[phone] = "main_menu"

        return main_menu_button_response(
            "Ubicación del consultorio:\n\n"
            "Care Medical Hub\n"
            "Bolivia 103, Balcones de Galerías, 64620 Monterrey, N.L.\n\n"
            "Piso 11, Consultorio 4\n\n"
            "Google Maps:\n"
            "https://maps.app.goo.gl/gCDJoY1MMVujpXyk7"
        )

    if text == "consultation_price" or is_price_request(text):
        user_states[phone] = "main_menu"

        return main_menu_button_response(
            "El costo de la consulta es de $1,300 MXN.\n\n"
            "Este monto es reembolsable al iniciar tratamiento en la primera consulta de mesoterapia."
        )

    if text == "schedule_appointment" or is_schedule_request(text):
        existing_event = find_future_appointment_by_phone(phone)

        if existing_event:
            user_states[phone] = "main_menu"
            return duplicate_appointment_response(existing_event)

        user_states[phone] = "awaiting_name"

        return safe_text_response(
            "Perfecto. Vamos a agendar tu cita.\n\n"
            "Por favor escribe tu nombre completo."
        )

    if text == "reschedule_appointment":
        existing_event = find_future_appointment_by_phone(phone)

        if not existing_event:
            user_states[phone] = "main_menu"

            return main_menu_button_response(
                "No encontré una cita activa asociada a este número de WhatsApp.\n\n"
                "Si deseas agendar una nueva cita, vuelve al menú principal y selecciona “Agendar cita”."
            )

        patient_name = extract_patient_name_from_event(existing_event)
        event_date = format_event_date_es(existing_event)
        event_time = format_event_time_es(existing_event)

        user_states[phone] = {
            "step": "reschedule_awaiting_confirmation",
            "existing_event_id": existing_event.get("id"),
            "existing_event_patient_name": patient_name,
            "existing_event_date": event_date,
            "existing_event_time": event_time,
        }

        return {
            "type": "reschedule_confirmation",
            "message": (
                f"Paciente: {patient_name}\n"
                f"Fecha actual: {event_date}\n"
                f"Hora actual: {event_time}\n\n"
                "¿Confirmas que deseas reagendar esta cita?"
            ),
        }

    if text == "cancel_appointment":
        existing_event = find_future_appointment_by_phone(phone)

        if not existing_event:
            user_states[phone] = "main_menu"

            return main_menu_button_response(
                "No encontré una cita activa asociada a este número de WhatsApp.\n\n"
                "Si deseas agendar una nueva cita, vuelve al menú principal y selecciona “Agendar cita”."
            )

        patient_name = extract_patient_name_from_event(existing_event)
        event_date = format_event_date_es(existing_event)
        event_time = format_event_time_es(existing_event)

        user_states[phone] = {
            "step": "cancel_awaiting_confirmation",
            "existing_event_id": existing_event.get("id"),
            "existing_event_patient_name": patient_name,
            "existing_event_date": event_date,
            "existing_event_time": event_time,
        }
        return {
            "type": "cancel_confirmation",
            "message": (
                f"Paciente: {patient_name}\n"
                f"Fecha: {event_date}\n"
                f"Hora: {event_time}\n\n"
                "¿Confirmas que deseas cancelar esta cita?"
            ),
        }

    # -------------------------
    # Estado: esperando nombre
    # -------------------------

    if state == "awaiting_name":
        if not looks_like_valid_name(text):
            return safe_text_response(
                "Por favor escribe tu nombre completo para continuar con la cita."
            )

        user_states[phone] = {
            "step": "awaiting_week",
            "name": text,
        }

        return week_options_response()

    # -------------------------
    # Estados con contexto
    # -------------------------

    if isinstance(state, dict):
        step = state.get("step")

        # -------------------------
        # Navegación
        # -------------------------

        if text == "back_weeks":
            if step and step.startswith("reschedule_"):
                user_states[phone] = {
                    **state,
                    "step": "reschedule_awaiting_week",
                }
            else:
                user_states[phone] = {
                    "step": "awaiting_week",
                    "name": state.get("name"),
                }

            return week_options_response()

        if text == "back_days":
            week_id = state.get("week_id")
            week_title = state.get("week_title", "Semana seleccionada")

            if step and step.startswith("reschedule_"):
                user_states[phone] = {
                    **state,
                    "step": "reschedule_awaiting_day",
                }
            else:
                user_states[phone] = {
                    "step": "awaiting_day",
                    "name": state.get("name"),
                    "week_id": week_id,
                    "week_title": week_title,
                }

            return day_options_response(week_id, week_title)

        # -------------------------
        # Cancelar cita: esperando confirmación
        # -------------------------

        if step == "cancel_awaiting_confirmation":
            existing_event_id = state.get("existing_event_id")

            if text == "decline_cancel_appointment":
                user_states[phone] = "main_menu"

                return main_menu_button_response(
                    "De acuerdo. Tu cita no fue cancelada."
                )

            if text != "confirm_cancel_appointment":
                return {
                    "type": "cancel_confirmation",
                    "message": (
                        "Para cancelar tu cita necesito tu confirmación.\n\n"
                        "¿Confirmas que deseas cancelarla?"
                    ),
                }

            try:
                cancel_calendar_appointment(existing_event_id)

            except Exception as e:
                print("ERROR cancelling calendar event:", e)

                return main_menu_button_response(
                    "No pude cancelar la cita en este momento.\n\n"
                    "Por favor intenta de nuevo desde el menú principal o contacta directamente al consultorio."
                )

            user_states[phone] = {
                "step": "completed",
                "cancelled_event_id": existing_event_id,
            }

            return main_menu_button_response(
                "✅ Tu cita fue cancelada correctamente.\n\n"
                "El calendario del consultorio fue actualizado."
            )

        # -------------------------
        # Agendar: esperando semana
        # -------------------------

        if step == "awaiting_week":
            weeks = get_available_weeks()
            selected_week = find_week_by_text(text, weeks)

            if not selected_week:
                return invalid_week_response(weeks)

            week_id = selected_week["id"]
            week_title = selected_week["title"]

            days = get_available_days_for_week(week_id)

            if not days:
                return day_options_response(week_id, week_title)

            user_states[phone] = {
                "step": "awaiting_day",
                "name": state.get("name"),
                "week_id": week_id,
                "week_title": week_title,
            }

            return {
                "type": "day_options",
                "selected_week_title": week_title,
                "days": days,
            }

        # -------------------------
        # Agendar: esperando día
        # -------------------------

        if step == "awaiting_day":
            week_id = state.get("week_id")
            week_title = state.get("week_title", "Semana seleccionada")

            days = get_available_days_for_week(week_id)
            selected_day = find_day_by_text(text, days)

            if not selected_day:
                return invalid_day_response(week_title, days)

            day_id = selected_day["id"]
            day_title = selected_day["title"]
            selected_date = parse_day_id(day_id)

            if not selected_date:
                return invalid_day_response(week_title, days)

            time_rows = build_time_rows_for_day(selected_date)

            if not time_rows:
                return day_options_response(week_id, week_title)

            user_states[phone] = {
                "step": "awaiting_time",
                "name": state.get("name"),
                "week_id": week_id,
                "week_title": week_title,
                "day_id": day_id,
                "day_title": day_title,
                "selected_date": selected_date.isoformat(),
                "time_period": None,
            }

            return {
                "type": "time_options",
                "selected_day_title": day_title,
                "times": time_rows,
                "period": None,
            }

        # -------------------------
        # Agendar: esperando horario
        # -------------------------

        if step == "awaiting_time":
            day_id, day_title, selected_date, time_rows = get_day_and_times_from_state(state)

            if not selected_date:
                return main_menu_button_response(
                    "No pude recuperar el día seleccionado.\n\n"
                    "Puedes volver al menú principal para intentarlo de nuevo."
                )

            period_response = handle_period_selection(
                phone=phone,
                text=text,
                state=state,
                day_title=day_title,
                time_rows=time_rows,
            )

            if period_response:
                return period_response

            selected_time = find_time_by_text(text, time_rows)

            if not selected_time:
                return invalid_time_response(
                    day_title=day_title,
                    time_rows=time_rows,
                    period=state.get("time_period"),
                )

            name = state.get("name")
            slot_id = selected_time["id"]
            selected_time_title = selected_time["title"]

            existing_event = find_future_appointment_by_phone(phone)

            if existing_event:
                user_states[phone] = "main_menu"
                return duplicate_appointment_response(existing_event)

            try:
                created_event = book_calendar_appointment(
                    patient_name=name,
                    patient_phone=phone,
                    slot_id=slot_id,
                )

                event_link = created_event.get("htmlLink", "")

            except Exception as e:
                print("ERROR creating calendar event:", e)

                refreshed_time_rows = build_time_rows_for_day(selected_date)

                if refreshed_time_rows:
                    return invalid_time_response(
                        day_title=day_title,
                        time_rows=refreshed_time_rows,
                        period=state.get("time_period"),
                    )

                return main_menu_button_response(
                    "Ese horario ya no está disponible y no quedan más horarios para ese día.\n\n"
                    "Puedes volver al menú principal para intentar con otra fecha."
                )

            user_states[phone] = {
                "step": "completed",
                "name": name,
                "day_id": day_id,
                "day_title": day_title,
                "slot_id": slot_id,
                "time_title": selected_time_title,
                "google_event_id": created_event.get("id"),
                "google_event_link": event_link,
            }

            return main_menu_button_response(
                f"✅ Cita agendada.\n\n"
                f"Paciente: {name}\n"
                f"Día: {day_title}\n"
                f"Horario: {selected_time_title}\n\n"
                f"Tu cita quedó registrada en el calendario del consultorio.\n\n"
                f"Gracias por contactar al consultorio."
            )

        if step == "reschedule_awaiting_confirmation":
            existing_event_id = state.get("existing_event_id")

            if text == "decline_reschedule_appointment":
                user_states[phone] = "main_menu"

                return main_menu_button_response(
                    "De acuerdo. Tu cita no fue modificada."
                )

            if text != "confirm_reschedule_appointment":
                return {
                    "type": "reschedule_confirmation",
                    "message": (
                        "Para reagendar tu cita necesito tu confirmación.\n\n"
                        "¿Confirmas que deseas reagendarla?"
                    ),
                }

            user_states[phone] = {
                **state,
                "step": "reschedule_awaiting_week",
                "existing_event_id": existing_event_id,
            }

            return week_options_response()

        # -------------------------
        # Reagendar: esperando semana
        # -------------------------

        if step == "reschedule_awaiting_week":
            weeks = get_available_weeks()
            selected_week = find_week_by_text(text, weeks)

            if not selected_week:
                return invalid_week_response(weeks)

            week_id = selected_week["id"]
            week_title = selected_week["title"]

            days = get_available_days_for_week(week_id)

            if not days:
                return day_options_response(week_id, week_title)

            user_states[phone] = {
                **state,
                "step": "reschedule_awaiting_day",
                "week_id": week_id,
                "week_title": week_title,
            }

            return {
                "type": "day_options",
                "selected_week_title": week_title,
                "days": days,
            }

        # -------------------------
        # Reagendar: esperando día
        # -------------------------

        if step == "reschedule_awaiting_day":
            week_id = state.get("week_id")
            week_title = state.get("week_title", "Semana seleccionada")

            days = get_available_days_for_week(week_id)
            selected_day = find_day_by_text(text, days)

            if not selected_day:
                return invalid_day_response(week_title, days)

            day_id = selected_day["id"]
            day_title = selected_day["title"]
            selected_date = parse_day_id(day_id)

            if not selected_date:
                return invalid_day_response(week_title, days)

            time_rows = build_time_rows_for_day(selected_date)

            if not time_rows:
                return day_options_response(week_id, week_title)

            user_states[phone] = {
                **state,
                "step": "reschedule_awaiting_time",
                "day_id": day_id,
                "day_title": day_title,
                "selected_date": selected_date.isoformat(),
                "time_period": None,
            }

            return {
                "type": "time_options",
                "selected_day_title": day_title,
                "times": time_rows,
                "period": None,
            }

        # -------------------------
        # Reagendar: esperando horario
        # -------------------------

        if step == "reschedule_awaiting_time":
            day_id, day_title, selected_date, time_rows = get_day_and_times_from_state(state)
            existing_event_id = state.get("existing_event_id")

            if not selected_date:
                return main_menu_button_response(
                    "No pude recuperar el día seleccionado.\n\n"
                    "Puedes volver al menú principal para intentarlo de nuevo."
                )

            period_response = handle_period_selection(
                phone=phone,
                text=text,
                state=state,
                day_title=day_title,
                time_rows=time_rows,
            )

            if period_response:
                return period_response

            selected_time = find_time_by_text(text, time_rows)

            if not selected_time:
                return invalid_time_response(
                    day_title=day_title,
                    time_rows=time_rows,
                    period=state.get("time_period"),
                )

            slot_id = selected_time["id"]
            selected_time_title = selected_time["title"]

            try:
                updated_event = reschedule_calendar_appointment(
                    event_id=existing_event_id,
                    slot_id=slot_id,
                )

                event_link = updated_event.get("htmlLink", "")

            except Exception as e:
                print("ERROR rescheduling calendar event:", e)

                refreshed_time_rows = build_time_rows_for_day(selected_date)

                if refreshed_time_rows:
                    return invalid_time_response(
                        day_title=day_title,
                        time_rows=refreshed_time_rows,
                        period=state.get("time_period"),
                    )

                return main_menu_button_response(
                    "Ese horario ya no está disponible y no quedan más horarios para ese día.\n\n"
                    "Puedes volver al menú principal para intentar con otra fecha."
                )

            user_states[phone] = {
                "step": "completed",
                "day_id": day_id,
                "day_title": day_title,
                "slot_id": slot_id,
                "time_title": selected_time_title,
                "google_event_id": updated_event.get("id"),
                "google_event_link": event_link,
            }

            return main_menu_button_response(
                f"✅ Cita reagendada.\n\n"
                f"Nuevo día: {day_title}\n"
                f"Nuevo horario: {selected_time_title}\n\n"
                f"Tu cita fue actualizada en el calendario del consultorio."
            )
        
        if state == "main_menu":
            return invalid_main_menu_response()

    # Fallback universal.
    return invalid_main_menu_response()