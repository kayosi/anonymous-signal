from cryptography.fernet import Fernet
import os

# Load or generate secret key
SECRET_KEY = os.getenv("SECRET_KEY").encode()  # Must be 32 url-safe base64 bytes
fernet = Fernet(SECRET_KEY)

def encrypt_report(data: str) -> str:
    return fernet.encrypt(data.encode()).decode()

def decrypt_report(token: str) -> str:
    return fernet.decrypt(token.encode()).decode()
