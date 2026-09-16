from urllib.parse import quote
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
import os


load_dotenv()

MYDEVELON_CLIENT_ID = os.getenv("MYDEVELON_CLIENT_ID")
MYDEVELON_CLIENT_SECRET = os.getenv("MYDEVELON_CLIENT_SECRET")

BASE_URL = "https://extapi.mydevelon.com/api/rest/aemp/2.0"
TOKEN_URL = f"{BASE_URL}/token"


def get_access_token():
    response = requests.post(
        TOKEN_URL,
        auth=HTTPBasicAuth(
            MYDEVELON_CLIENT_ID,
            MYDEVELON_CLIENT_SECRET,
        ),
        timeout=30,
    )

    response.raise_for_status()

    return response.text.strip()


def get_equipment_by_pin_xml(access_token, pin):
    url = (
        f"{BASE_URL}/Fleet/Equipment/ID/"
        f"{quote(str(pin), safe='')}"
    )

    response = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/xml",
        },
        timeout=30,
    )

    return url, response


def main():
    print("=" * 70)
    print("TEST MYDEVELON POR PIN")
    print("=" * 70)

    pin = "DHKCEBDXCK0001085"

    print(f"\nPIN: {pin}")

    print("\nObteniendo token...")
    token = get_access_token()

    print("[OK] Token obtenido.")

    print("\nConsultando equipo por PIN...")

    url, response = get_equipment_by_pin_xml(
        token,
        pin,
    )

    print(f"\nURL:")
    print(url)

    print(f"\nHTTP: {response.status_code}")
    print(f"Content-Type: {response.headers.get('Content-Type')}")
    print(f"Content-Length: {response.headers.get('Content-Length')}")

    print("\nRESPUESTA:")
    print("-" * 70)
    print(response.text)
    print("-" * 70)


if __name__ == "__main__":
    main()