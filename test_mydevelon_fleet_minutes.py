from mydevelon import get_access_token
import requests

BASE_URL = "https://extapi.mydevelon.com/api/rest/aemp/2.0"


def main():
    print("Obteniendo token...")
    token = get_access_token()

    url = f"{BASE_URL}/Fleet/minutes/1"

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/xml",
    }

    print(f"\nGET {url}")
    print("Consultando Fleet Snapshot (minutes)...\n")

    response = requests.get(
        url,
        headers=headers,
        timeout=60,
    )

    print("STATUS:", response.status_code)
    print("CONTENT-TYPE:", response.headers.get("Content-Type"))
    print("CONTENT-LENGTH:", len(response.content))

    print("\n--- RESPUESTA ---")
    print(response.text[:10000])

    if response.status_code == 200:
        with open("mydevelon_fleet_minutes.xml", "w", encoding="utf-8") as f:
            f.write(response.text)

        print("\n[OK] XML guardado en:")
        print("mydevelon_fleet_minutes.xml")


if __name__ == "__main__":
    main()