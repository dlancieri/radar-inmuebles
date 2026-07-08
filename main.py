import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus

SEARCHES = [
    "casa reciclar montevideo",
    "casa ideal inversor montevideo",
    "local vivienda montevideo",
    "casa padrón único montevideo",
]

def search_ml_web(query):
    url = f"https://listado.mercadolibre.com.uy/inmuebles/{quote_plus(query)}"
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    r = requests.get(url, headers=headers, timeout=20)
    print("URL:", url)
    print("STATUS:", r.status_code)

    if r.status_code != 200:
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    links = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(" ", strip=True)

        if "articulo.mercadolibre.com.uy" in href or "inmuebles.mercadolibre.com.uy" in href:
            if href not in [x["link"] for x in links]:
                links.append({
                    "titulo": text[:120],
                    "link": href
                })

    return links

if __name__ == "__main__":
    all_results = []

    for query in SEARCHES:
        results = search_ml_web(query)
        all_results.extend(results)

    print(f"Resultados encontrados: {len(all_results)}")

    for r in all_results[:20]:
        print("-", r["titulo"])
        print(" ", r["link"])
