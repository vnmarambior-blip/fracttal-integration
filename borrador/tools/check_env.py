import os
from dotenv import load_dotenv

load_dotenv()


def main():

    print(
        "CLIENT_ID:",
        "CONFIGURADO" if os.getenv("FRACTTAL_CLIENT_ID") else "NO CONFIGURADO"
    )
    print(
        "CLIENT_SECRET:",
        "CONFIGURADO" if os.getenv("FRACTTAL_CLIENT_SECRET") else "NO CONFIGURADO"
    )
    print("REDIRECT_URI:", os.getenv("FRACTTAL_REDIRECT_URI"))


if __name__ == "__main__":
    main()
