import os
import requests

client_id = os.getenv("MELI_CLIENT_ID")
client_secret = os.getenv("MELI_CLIENT_SECRET")
code = os.getenv("MELI_CODE")

if not client_id or not client_secret or not code:
    raise RuntimeError("Faltan MELI_CLIENT_ID, MELI_CLIENT_SECRET o MELI_CODE")

url = "https://api.mercadolibre.com/oauth/token"

data = {
    "grant_type": "authorization_code",
    "client_id": client_id,
    "client_secret": client_secret,
    "code": code,
    "redirect_uri": "https://radar",
}

response = requests.post(url, data=data, timeout=20)

print("STATUS:", response.status_code)
print(response.text[:1000])

response.raise_for_status()
