import re
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
from datetime import datetime

SEARCHES = [
    "casa venta montevideo reciclar",
    "casa venta montevideo ideal inversor",
    "casa venta montevideo padron unico",
    "local vivienda venta montevideo",
    "casa venta montevideo varios ambientes",
    "casa venta maldonado reciclar",
]

KEYWORDS = {
    "reciclar": 15,
    "a reciclar": 20,
    "ideal inversor": 15,
    "inversor": 8,
    "padrón único": 15,
    "padron unico": 15,
    "entrada independiente": 12,
    "dos entradas": 12,
    "fondo": 8,
    "patio": 8,
    "azotea": 10,
    "varios ambientes": 10,
    "local y vivienda": 15,
    "gran terreno": 12,
    "permite construir": 15,
    "ph": 6,
}

def get_html(url):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "es-UY,es;q=0.9,en;q=0.8",
    }
    r = requests.get(url, headers=headers, timeout=25)
    print("URL:", url)
    print("STATUS:", r.status_code)
    if r.status_code != 200:
        return None
    return r.text

def search_ml(query):
    url = f"https://listado.mercadolibre.com.uy/inmuebles/{quote_plus(query)}"
    html = get_html(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    results = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(" ", strip=True)

        if (
            "inmuebles.mercadolibre.com.uy" in href
            or "articulo.mercadolibre.com.uy" in href
        ):
            if len(text) > 10:
                results.append({
                    "query": query,
                    "titulo_listado": text[:180],
                    "link": href.split("#")[0],
                })

    return results

def extract_price(text):
    text = text.replace(".", "")
    match = re.search(r"U\$S\s*([0-9]+)", text)
    if match:
        return int(match.group(1))
    return None

def extract_m2(text):
    patterns = [
        r"([0-9]+)\s*m²",
        r"([0-9]+)\s*metros",
        r"([0-9]+)\s*mt2",
        r"([0-9]+)\s*m2",
    ]
    for p in patterns:
        match = re.search(p, text.lower())
        if match:
            return int(match.group(1))
    return None

def score_property(title, description):
    text = f"{title} {description}".lower()
    score = 0
    signals = []

    for keyword, points in KEYWORDS.items():
        if keyword in text:
            score += points
            signals.append(keyword)

    m2 = extract_m2(text)
    price = extract_price(text)

    if m2:
        if m2 >= 120:
            score += 20
            signals.append("más de 120 m²")
        if m2 >= 160:
            score += 15
            signals.append("más de 160 m²")

    if price and m2:
        usd_m2 = price / m2
        if usd_m2 < 900:
            score += 20
            signals.append("USD/m² bajo")
        elif usd_m2 < 1200:
            score += 10
            signals.append("USD/m² razonable")
    else:
        usd_m2 = None

    if price and price > 220000:
        score -= 20
        signals.append("precio alto")

    return min(max(score, 0), 100), signals, price, m2, usd_m2

def read_publication(link):
    html = get_html(link)
    if not html:
        return "", ""

    soup = BeautifulSoup(html, "html.parser")

    title = ""
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(" ", strip=True)

    text = soup.get_text(" ", strip=True)
    description = text[:5000]

    return title, description

def main():
    rows = []
    seen = set()

    for query in SEARCHES:
        for item in search_ml(query):
            link = item["link"]

            if link in seen:
                continue
            seen.add(link)

            title, description = read_publication(link)

            if not title:
                title = item["titulo_listado"]

            score, signals, price, m2, usd_m2 = score_property(title, description)

            if score < 30:
                continue

            rows.append({
                "fecha_detectada": datetime.now().strftime("%Y-%m-%d"),
                "fuente": "Mercado Libre",
                "query": query,
                "titulo": title,
                "precio_usd": price,
                "m2": m2,
                "usd_m2": round(usd_m2, 2) if usd_m2 else None,
                "score": score,
                "senales_detectadas": ", ".join(sorted(set(signals))),
                "hipotesis_reconversion": "Revisar posible división en varias unidades",
                "estado": "nuevo",
                "link": link,
            })

    df = pd.DataFrame(rows)

    if df.empty:
        print("No se encontraron oportunidades.")
        return

    df = df.drop_duplicates(subset=["link"])
    df = df.sort_values(by="score", ascending=False)

    df.to_csv("oportunidades.csv", index=False)

    print("\nTOP oportunidades:")
    print(df.head(20).to_string(index=False))

if __name__ == "__main__":
    main()
