import os
import requests

token = os.getenv("MELI_ACCESS_TOKEN")

headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/json"
}

url = "https://api.mercadolibre.com/sites/MLU/search"

params = {
    "q": "casa montevideo",
    "limit": 3
}

r = requests.get(url, headers=headers, params=params)

print(r.status_code)
print(r.text)
