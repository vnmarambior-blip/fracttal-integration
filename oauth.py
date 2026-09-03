import os
import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("FRACTTAL_CLIENT_ID")
CLIENT_SECRET = os.getenv("FRACTTAL_CLIENT_SECRET")

TOKEN_URL = "https://one.fracttal.com/oauth/token"


response = requests.post(
    TOKEN_URL,
    auth=(CLIENT_ID, CLIENT_SECRET),
    data={
        "grant_type": "client_credentials"
    }
)

print("HTTP:", response.status_code)

if response.ok:
    token_data = response.json()

    print("TOKEN OBTENIDO CORRECTAMENTE")
    print("Token type:", token_data.get("token_type"))
    print("Expira en:", token_data.get("expires_in"), "segundos")
    print("Access token recibido:", "SI" if token_data.get("access_token") else "NO")

else:
    print("ERROR AL OBTENER TOKEN")
    print(response.text)