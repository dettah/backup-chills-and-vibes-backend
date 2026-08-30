# backend/apps/core/utils.py
import uuid

def generate_secure_token(prefix: str) -> str:
    """
    Generates a unique, collision-resistant cryptographic string identifier.
    Prefixed with readable domain keys for easy debugging (e.g., 'ord_...', 'tkt_...').
    """
    unique_id = uuid.uuid4().hex
    return f"{prefix}_{unique_id}"
