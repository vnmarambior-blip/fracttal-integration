import os
from dotenv import load_dotenv

load_dotenv()

print("CLIENT_ID:", os.getenv("FRACTTAL_CLIENT_ID"))
print(
    "CLIENT_SECRET:",
    "CONFIGURADO" if os.getenv("FRACTTAL_CLIENT_SECRET") else "NO CONFIGURADO"
)
print("REDIRECT_URI:", os.getenv("FRACTTAL_REDIRECT_URI"))