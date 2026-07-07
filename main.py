import requests
import pandas as pd
from scoring import score_property

SEARCHES = [
    "casa reciclar montevideo",
    "casa ideal inversor montevideo",
    "local vivienda montevideo",
    "oficina grande montevideo",
    "casa padrón único montevideo",
    "casa reciclar maldonado",
    "local vivienda maldonado",
]

def search_mercadolibre(query, limit=20):
    url = "https://api.mercadolibre.com/sites/MLU/search"
    params = {
        "q": query,
        "limit": limit,
    }

    headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    }

    response = requests.get(url, params=params, headers=headers, timeout=20)
    response.raise_for_status()
    return response.json().get("results", [])

def extract_price_usd(item):
    currency = item.get("currency_id")
    price = item.get("price")
    if currency == "USD":
        return price
    return None

def extract_m2(item):
    attributes = item.get("attributes", [])
    for attr in attributes:
        name = (attr.get("name") or "").lower()
        if "superficie" in name or "metros" in name or "m²" in name:
            value = attr.get("value_name")
            if value:
                digits = "".join(ch for ch in value if ch.isdigit())
                if digits:
                    return int(digits)
    return None

def build_rows():
    rows = []

    for query in SEARCHES:
        items = search_mercadolibre(query)

        for item in items:
            title = item.get("title")
            price_usd = extract_price_usd(item)
            m2 = extract_m2(item)
            link = item.get("permalink")
            item_id = item.get("id")

            description = ""  # En V2 traemos descripción por item_id
            score, signals = score_property(title, description, price_usd, m2)

            if score < 40:
                continue

            usd_m2 = round(price_usd / m2, 2) if price_usd and m2 else None

            rows.append({
                "fuente": "Mercado Libre",
                "id_publicacion": item_id,
                "titulo": title,
                "precio_usd": price_usd,
                "m2": m2,
                "usd_m2": usd_m2,
                "link": link,
                "senales_detectadas": ", ".join(signals),
                "score": score,
                "estado": "nuevo",
            })

    return rows

if __name__ == "__main__":
    rows = build_rows()
    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["id_publicacion"])
    df = df.sort_values(by="score", ascending=False)

    print(df.head(20).to_string(index=False))
