from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from app.reminders import send_tomorrow_appointment_reminders

from app.config import VERIFY_TOKEN, REMINDER_JOB_SECRET
from app.whatsapp import (
    send_message,
    send_main_menu,
    send_main_menu_button,
    send_week_options,
    send_day_options,
    send_time_options,
    send_cancel_confirmation,
    send_reschedule_confirmation,
)

from app.conversation import handle_user_message, UNSUPPORTED_MESSAGE
from app.state import is_duplicate_message

app = FastAPI()

@app.post("/jobs/send-appointment-reminders")
def send_appointment_reminders_job(secret: str | None = None):
    if REMINDER_JOB_SECRET and secret != REMINDER_JOB_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    result = send_tomorrow_appointment_reminders()
    return result

@app.get("/")
async def root():
    return {"status": "running"}

@app.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params

    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return int(challenge)

    return {"error": "verification failed"}

def dispatch_response(phone: str, response: dict | None):

    if not response:
        send_message(
            phone,
            "No pude procesar tu mensaje. Escribe “hola” para volver al menú principal."
        )
        return

    response_type = response.get("type")

    if response_type == "multi":
        for item in response.get("responses", []):
            dispatch_response(phone, item)
        return

    if response_type == "main_menu":
        send_main_menu(phone)
        return

    if response_type == "week_options":
        send_week_options(
            phone,
            response.get("weeks", [])
        )
        return

    if response_type == "day_options":
        send_day_options(
            phone,
            response.get("selected_week_title", ""),
            response.get("days", [])
        )
        return

    if response_type == "time_options":
        send_time_options(
            phone,
            response.get("selected_day_title", ""),
            response.get("times", []),
            response.get("period")
        )
        return

    if response_type == "text":
        send_message(
            phone,
            response.get(
                "message",
                "Ocurrió un error. Escribe “hola” para volver al menú."
            )
        )
        return
    
    if response_type == "cancel_confirmation":
        send_cancel_confirmation(
            phone,
            response.get("message", "¿Confirmas que deseas cancelar tu cita?")
        )
        return
    
    if response_type == "main_menu_button":
        send_main_menu_button(
            phone,
            response.get("message", "Puedes volver al menú principal.")
        )
        return
    
    if response_type == "reschedule_confirmation":
        send_reschedule_confirmation(
            phone,
            response.get("message", "¿Confirmas que deseas reagendar tu cita?")
        )
        return

    send_message(phone, "Ocurrió un error. Escribe “hola” para volver al menú.")


def extract_incoming_message(body: dict):
    try:
        entry = body["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]

        messages = value.get("messages")

        if not messages:
            return None

        message = messages[0]

        phone = message.get("from")
        message_id = message.get("id")
        message_type = message.get("type")

        incoming_text = UNSUPPORTED_MESSAGE

        if message_type == "text":
            incoming_text = message.get("text", {}).get("body", "")

        elif message_type == "interactive":
            interactive = message.get("interactive", {})
            interactive_type = interactive.get("type")

            if interactive_type == "button_reply":
                incoming_text = interactive.get("button_reply", {}).get("id", UNSUPPORTED_MESSAGE)

            elif interactive_type == "list_reply":
                incoming_text = interactive.get("list_reply", {}).get("id", UNSUPPORTED_MESSAGE)
        
        elif message_type == "button":
            button = message.get("button", {})

            incoming_text = (
                button.get("payload")
                or button.get("text")
                or "__unsupported_message__"
            )

        return {
            "phone": phone,
            "message_id": message_id,
            "message_type": message_type,
            "incoming_text": incoming_text,
            "raw_message": message,
        }

    except Exception as e:
        print("ERROR extracting incoming message:", e)
        return None


def process_message(body: dict):
    incoming = extract_incoming_message(body)

    if not incoming:
        return

    phone = incoming["phone"]
    message_id = incoming["message_id"]
    message_type = incoming["message_type"]
    incoming_text = incoming["incoming_text"]

    if is_duplicate_message(message_id):
        print(f"Mensaje duplicado ignorado: {message_id}")
        return

    print(f"Mensaje recibido de {phone}")
    print(f"Tipo: {message_type}")
    print(f"Texto/ID: {incoming_text}")

    if not incoming_text:
        incoming_text = UNSUPPORTED_MESSAGE

    try:
        response = handle_user_message(phone, incoming_text)
        dispatch_response(phone, response)

    except Exception as e:
        print("ERROR processing message:", e)

        error_text = str(e)

        if "invalid_grant" in error_text:
            send_message(
                phone,
                "El calendario del consultorio necesita volver a autorizarse. Por favor contacta al administrador del sistema."
            )
            return

        send_message(
            phone,
            "Ocurrió un error procesando tu mensaje. Escribe “hola” para volver al menú principal."
        )


@app.post("/webhook")
async def receive_message(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()

    print("Webhook recibido")

    # Respondemos rápido a Meta para evitar reintentos.
    background_tasks.add_task(process_message, body)

    return {"status": "ok"}