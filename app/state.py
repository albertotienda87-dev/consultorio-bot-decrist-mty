from collections import deque

user_states = {}

processed_message_ids = set()
processed_message_order = deque()
MAX_PROCESSED_MESSAGES = 1000


def is_duplicate_message(message_id: str) -> bool:
    if not message_id:
        return False

    if message_id in processed_message_ids:
        return True

    processed_message_ids.add(message_id)
    processed_message_order.append(message_id)

    if len(processed_message_order) > MAX_PROCESSED_MESSAGES:
        old_message_id = processed_message_order.popleft()
        processed_message_ids.discard(old_message_id)

    return False