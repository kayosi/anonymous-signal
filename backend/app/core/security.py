from cryptography.fernet import Fernet
import os

# Load or generate secret key
SECRET_KEY = os.getenv("SECRET_KEY").encode()  # Must be 32 url-safe base64 bytes
fernet = Fernet(SECRET_KEY)

def encrypt_report(data: str) -> str:
    return fernet.encrypt(data.encode()).decode()

def decrypt_report(token: str) -> str:
    return fernet.decrypt(token.encode()).decode()

def encrypt_attachment(base64_data: str) -> bytes:
    # Convert string to bytes, encrypt
    return fernet.encrypt(base64_data.encode())
    
def decrypt_attachment(encrypted_bytes: bytes) -> str:
    return fernet.decrypt(encrypted_bytes).decode()

