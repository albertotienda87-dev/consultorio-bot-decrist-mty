import requests

from app.config import ACCESS_TOKEN, PHONE_NUMBER_ID

URL = f"https://graph.facebook.com/v25.0/{PHONE_NUMBER_ID}/messages"

headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

def send_whatsapp_payload(data: dict):
    response = requests.post(URL, headers=headers, json=data)

    print(response.status_code)
    print(response.text)

    return response

def send_appointment_reminder(
    phone: str,
    patient_name: str,
    appointment_date: str,
    appointment_time: str,
):
    data = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": (
                    f"Hola, {patient_name}.\n\n"
                    f"Te recordamos que tienes una cita programada para mañana, "
                    f"{appointment_date}, a las {appointment_time}.\n\n"
                    "Dra. Decris't Saldaña\n"
                    "Consultorio Monterrey\n\n"
                    "Por favor confirma tu asistencia."
                )
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": "reminder_confirm_appointment",
                            "title": "Confirmar cita"
                        }
                    },
                    {
                        "type": "reply",
                        "reply": {
                            "id": "reminder_reschedule_appointment",
                            "title": "Reagendar cita"
                        }
                    },
                    {
                        "type": "reply",
                        "reply": {
                            "id": "reminder_cancel_appointment",
                            "title": "Cancelar cita"
                        }
                    }
                ]
            }
        }
    }

    return send_whatsapp_payload(data)

def send_message(phone: str, message: str):
    data = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {
            "body": message
        }
    }

    return send_whatsapp_payload(data)


def send_main_menu(phone: str):
    data = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {
                "text": (
                    "¡Hola! Gracias por contactar a la Dra. Decris't Saldaña.\n\n"
                    "Especialista en Tricología Médica y Medicina Estética.\n\n"
                    "Te estás comunicando al consultorio de Monterrey. 📍\n\n"
                    "¿En qué puedo ayudarte?"
                )
            },
            "footer": {
                "text": "Consultorio Monterrey"
            },
            "action": {
                "button": "Ver opciones",
                "sections": [
                    {
                        "title": "Menú principal",
                        "rows": [
                            {
                                "id": "schedule_appointment",
                                "title": "Agendar cita",
                                "description": "Programar una nueva cita"
                            },
                            {
                                "id": "reschedule_appointment",
                                "title": "Reagendar cita",
                                "description": "Cambiar fecha u horario"
                            },
                            {
                                "id": "cancel_appointment",
                                "title": "Cancelar cita",
                                "description": "Cancelar una cita existente"
                            },
                            {
                                "id": "consultation_price",
                                "title": "Precio consulta",
                                "description": "Ver costo de consulta"
                            },
                            {
                                "id": "office_location",
                                "title": "Ubicación",
                                "description": "Ver dirección del consultorio"
                            }
                        ]
                    }
                ]
            }
        }
    }

    return send_whatsapp_payload(data)

def send_main_menu_button(phone: str, message: str):
    data = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": message
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": "back_main_menu",
                            "title": "Menú principal"
                        }
                    }
                ]
            }
        }
    }

    return send_whatsapp_payload(data)

def send_week_options(phone: str, weeks: list[dict]):
    rows = []

    for week in weeks:
        rows.append({
            "id": week["id"],
            "title": week["title"],
            "description": week["description"]
        })

    rows.append({
        "id": "back_main_menu",
        "title": "Menú principal",
        "description": "Volver al inicio"
    })

    data = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {
                "text": "Selecciona una semana disponible para tu cita:"
            },
            "footer": {
                "text": "Consultorio médico"
            },
            "action": {
                "button": "Ver semanas",
                "sections": [
                    {
                        "title": "Semanas disponibles",
                        "rows": rows
                    }
                ]
            }
        }
    }

    return send_whatsapp_payload(data)


def send_day_options(phone: str, selected_week_title: str, days: list[dict]):
    rows = []

    for day in days:
        rows.append({
            "id": day["id"],
            "title": day["title"],
            "description": day["description"]
        })

    rows.append({
        "id": "back_weeks",
        "title": "Ver semanas",
        "description": "Volver a seleccionar semana"
    })

    rows.append({
        "id": "back_main_menu",
        "title": "Menú principal",
        "description": "Volver al inicio"
    })

    data = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {
                "text": f"Seleccionaste: {selected_week_title}\n\nAhora elige un día disponible:"
            },
            "footer": {
                "text": "Consultorio médico"
            },
            "action": {
                "button": "Ver días",
                "sections": [
                    {
                        "title": "Días disponibles",
                        "rows": rows
                    }
                ]
            }
        }
    }

    return send_whatsapp_payload(data)


from datetime import datetime


def get_slot_datetime_from_id(slot_id: str):
    if not slot_id.startswith("slot_"):
        return None

    iso_value = slot_id.replace("slot_", "", 1)

    try:
        return datetime.fromisoformat(iso_value)
    except ValueError:
        return None


def filter_times_by_period(times: list[dict], period: str) -> list[dict]:
    filtered_times = []

    for time_item in times:
        slot_datetime = get_slot_datetime_from_id(time_item["id"])

        if not slot_datetime:
            continue

        hour = slot_datetime.hour

        if period == "morning" and 8 <= hour <= 13:
            filtered_times.append(time_item)

        elif period == "evening" and 14 <= hour <= 20:
            filtered_times.append(time_item)

    return filtered_times


def send_time_options(
    phone: str,
    selected_day_title: str,
    times: list[dict],
    period: str | None = None
):
    rows = []

    if period is None:
        rows.append({
            "id": "time_period_morning",
            "title": "Horarios matutinos",
            "description": "De 8:00 AM a 1:00 PM"
        })

        rows.append({
            "id": "time_period_evening",
            "title": "Horarios vespertinos",
            "description": "De 2:00 PM a 8:00 PM"
        })

        rows.append({
            "id": "back_days",
            "title": "Ver días",
            "description": "Volver a seleccionar día"
        })

        rows.append({
            "id": "back_weeks",
            "title": "Ver semanas",
            "description": "Volver a seleccionar semana"
        })

        rows.append({
            "id": "back_main_menu",
            "title": "Menú principal",
            "description": "Volver al inicio"
        })

        body_text = f"Seleccionaste: {selected_day_title}\n\n¿Qué horarios quieres ver?"

    else:
        filtered_times = filter_times_by_period(times, period)

        # WhatsApp permite máximo 10 filas.
        # Dejamos espacio para navegación.
        MAX_TIME_ROWS = 7
        filtered_times = filtered_times[:MAX_TIME_ROWS]

        for time_item in filtered_times:
            rows.append({
                "id": time_item["id"],
                "title": time_item["title"],
                "description": time_item["description"]
            })

        if period == "morning":
            rows.append({
                "id": "time_period_evening",
                "title": "Ver vespertinos",
                "description": "De 2:00 PM a 8:00 PM"
            })
            body_text = f"Seleccionaste: {selected_day_title}\n\nHorarios matutinos disponibles:"
        else:
            rows.append({
                "id": "time_period_morning",
                "title": "Ver matutinos",
                "description": "De 8:00 AM a 1:00 PM"
            })
            body_text = f"Seleccionaste: {selected_day_title}\n\nHorarios vespertinos disponibles:"

        rows.append({
            "id": "back_days",
            "title": "Ver días",
            "description": "Volver a seleccionar día"
        })

        rows.append({
            "id": "back_main_menu",
            "title": "Menú principal",
            "description": "Volver al inicio"
        })

        if not filtered_times:
            body_text = f"Seleccionaste: {selected_day_title}\n\nNo hay horarios disponibles en este periodo."

    data = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {
                "text": body_text
            },
            "footer": {
                "text": "Consultorio médico"
            },
            "action": {
                "button": "Ver horarios",
                "sections": [
                    {
                        "title": "Horarios disponibles",
                        "rows": rows
                    }
                ]
            }
        }
    }

    return send_whatsapp_payload(data)

def send_cancel_confirmation(phone: str, message: str):
    data = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": message
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": "confirm_cancel_appointment",
                            "title": "Sí, cancelar"
                        }
                    },
                    {
                        "type": "reply",
                        "reply": {
                            "id": "decline_cancel_appointment",
                            "title": "No cancelar"
                        }
                    }
                ]
            }
        }
    }

    return send_whatsapp_payload(data)

def send_reschedule_confirmation(phone: str, message: str):
    data = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": message
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": "confirm_reschedule_appointment",
                            "title": "Sí, reagendar"
                        }
                    },
                    {
                        "type": "reply",
                        "reply": {
                            "id": "decline_reschedule_appointment",
                            "title": "No reagendar"
                        }
                    }
                ]
            }
        }
    }

    return send_whatsapp_payload(data)