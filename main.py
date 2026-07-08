import re
import pandas as pd
from datetime import datetime
from urllib.parse import quote_plus
from playwright.sync_api import sync_playwright

SEARCHES = [
    "casa venta montevideo reciclar",
    "casa venta montevideo ideal inversor",
    "casa venta montevideo padron unico",
    "local vivienda venta montevideo",
    "casa venta montevideo varios ambientes",
    "casa venta maldonado reciclar",
]

KEYWORDS = [
    "reciclar",
    "a reciclar",
    "ideal inversor",
    "inversor",
    "padrón único",
    "padron unico",
    "entrada independiente",
    "dos entradas",
    "fondo",
    "patio",
    "azotea",
    "varios ambientes",
    "local y vivienda",
    "gran terreno",
    "permite construir",
]

def clean_link(link):
    return link.split("#")[0].split("?")[0]

def extract_links(page, query):
    url = f"https://listado.mercadolibre.com.uy/inmuebles/{quote_plus(query)}"
    print("Buscando:", url)

    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.screenshot(path="busqueda.png", full_page=True)

    print("Título:", page.title())
    print("URL final:", page.url)

    with open("pagina.html", "w", encoding="utf-8") as f:
        f.write(page.content())
    page.wait_for_timeout(3000)

    links = page.locator("a").evaluate_all("""
        elements => elements
            .map(a => ({text: a.innerText, href: a.href}))
            .filter(x => x.href && (
                x.href.includes('inmuebles.mercadolibre.com.uy') ||
                x.href.includes('articulo.mercadolibre.com.uy')
            ))
    """)

    results = []
    seen = set()

    for item in links:
        href = clean_link(item["href"])
        text = (item["text"] or "").strip()

        if href in seen:
            continue

        if len(text) < 10:
            continue

        seen.add(href)
        results.append({
            "query": query,
            "titulo_listado": text[:180],
            "link": href,
        })

    print("Links encontrados:", len(results))
    return results

def extract_price(text):
    text = text.replace(".", "")
    match = re.search(r"U\$S\s*([0-9]+)", text)
    return int(match.group(1)) if match else None

def extract_m2(text):
    patterns = [
        r"([0-9]+)\s*m²",
        r"([0-9]+)\s*m2",
        r"([0-9]+)\s*mt2",
        r"([0-9]+)\s*metros",
    ]

    for pattern in patterns:
        match = re.search(pattern, text.lower())
        if match:
            return int(match.group(1))

    return None

def score_property(title, text):
    full_text = f"{title} {text}".lower()
    score = 0
    signals = []

    for kw in KEYWORDS:
        if kw in full_text:
            score += 10
            signals.append(kw)

    m2 = extract_m2(full_text)
    price = extract_price(full_text)

    usd_m2 = None
    if price and m2:
        usd_m2 = price / m2
        if usd_m2 < 900:
            score += 20
            signals.append("USD/m² bajo")
        elif usd_m2 < 1200:
            score += 10
            signals.append("USD/m² razonable")

    if m2:
        if m2 >= 120:
            score += 20
            signals.append("más de 120 m²")
        if m2 >= 160:
            score += 15
            signals.append("más de 160 m²")

    return min(score, 100), sorted(set(signals)), price, m2, usd_m2

def read_publication(page, link):
    print("Leyendo:", link)

    try:
        page.goto(link, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2500)

        title = ""
        if page.locator("h1").count() > 0:
            title = page.locator("h1").first.inner_text().strip()

        text = page.locator("body").inner_text(timeout=15000)

        return title, text[:8000]

    except Exception as e:
        print("Error leyendo publicación:", e)
        return "", ""

def main():
    rows = []
    seen_links = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
        )

        all_links = []

        for query in SEARCHES:
            all_links.extend(extract_links(page, query))

        for item in all_links:
            link = item["link"]

            if link in seen_links:
                continue

            seen_links.add(link)

            title, text = read_publication(page, link)

            if not title:
                title = item["titulo_listado"]

            score, signals, price, m2, usd_m2 = score_property(title, text)

            if score < 30:
                continue

            rows.append({
                "fecha_detectada": datetime.now().strftime("%Y-%m-%d"),
                "fuente": "Mercado Libre",
                "query": item["query"],
                "titulo": title,
                "precio_usd": price,
                "m2": m2,
                "usd_m2": round(usd_m2, 2) if usd_m2 else None,
                "score": score,
                "senales_detectadas": ", ".join(signals),
                "hipotesis_reconversion": "Revisar posible división en varias unidades",
                "estado": "nuevo",
                "link": link,
            })

        browser.close()

    df = pd.DataFrame(rows)

    if df.empty:
        print("No se encontraron oportunidades.")
        return

    df = df.drop_duplicates(subset=["link"])
    df = df.sort_values(by="score", ascending=False)
    df.to_csv("oportunidades.csv", index=False)

    print(df.head(20).to_string(index=False))

if __name__ == "__main__":
    main()
