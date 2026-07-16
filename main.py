import re
import time
import unicodedata
from datetime import datetime
from urllib.parse import urljoin

import pandas as pd
from playwright.sync_api import Locator, sync_playwright


BASE_URL = "https://www.infocasas.com.uy"
SEARCH_BASE = f"{BASE_URL}/venta/casas/montevideo"

# Empezamos con 10 páginas: unas 200 propiedades.
MAX_PAGES = 10

# Rango inicial del MVP.
MIN_PRICE_USD = 60_000
MAX_PRICE_USD = 250_000
MIN_AREA_M2 = 90


KEYWORD_RULES = {
    "padron unico": 25,
    "mismo padron": 25,
    "varias unidades": 25,
    "varias viviendas": 25,
    "dos casas": 25,
    "2 casas": 25,
    "tres casas": 30,
    "3 casas": 30,
    "apartamento independiente": 20,
    "entrada independiente": 15,
    "entradas independientes": 18,
    "ideal inversor": 18,
    "oportunidad inversor": 18,
    "renta": 10,
    "para reciclar": 15,
    "a reciclar": 15,
    "reciclaje": 12,
    "propiedad horizontal": 8,
    "azotea": 7,
    "patio": 6,
    "fondo": 7,
    "galpon": 8,
    "local": 6,
    "varios ambientes": 10,
    "gran terreno": 10,
    "posibilidad de construir": 15,
}


TARGET_NEIGHBORHOODS = {
    "centro": 12,
    "cordon": 12,
    "aguada": 12,
    "palermo": 10,
    "barrio sur": 10,
    "tres cruces": 10,
    "la comercial": 10,
    "goes": 10,
    "la blanqueada": 8,
    "union": 8,
    "jacinto vera": 8,
    "reducto": 8,
    "villa munoz": 8,
    "ciudad vieja": 8,
}


def normalize_text(value: str) -> str:
    value = value or ""
    value = unicodedata.normalize("NFD", value)
    value = "".join(
        char for char in value
        if unicodedata.category(char) != "Mn"
    )
    return " ".join(value.lower().split())


def clean_number(value: str) -> float | None:
    if not value:
        return None

    cleaned = re.sub(r"[^\d.,]", "", value)

    if not cleaned:
        return None

    cleaned = cleaned.replace(".", "").replace(",", ".")

    try:
        return float(cleaned)
    except ValueError:
        return None


def extract_first_number(
    text: str,
    patterns: list[str],
) -> int | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)

        if match:
            try:
                return int(match.group(1))
            except ValueError:
                continue

    return None


def safe_text(locator: Locator) -> str:
    try:
        if locator.count() > 0:
            return locator.first.inner_text().strip()
    except Exception:
        pass

    return ""


def safe_attribute(
    locator: Locator,
    attribute: str,
) -> str:
    try:
        if locator.count() > 0:
            return locator.first.get_attribute(attribute) or ""
    except Exception:
        pass

    return ""


def extract_neighborhood(location_text: str) -> str:
    # Ejemplo: Casa en Pocitos, Montevideo
    match = re.search(
        r"(?:Casa|Propiedad)\s+en\s+(.+?),\s*Montevideo",
        location_text,
        flags=re.IGNORECASE,
    )

    if match:
        return match.group(1).strip()

    if "," in location_text:
        first_part = location_text.split(",")[0]

        return re.sub(
            r"^(Casa|Propiedad)\s+en\s+",
            "",
            first_part,
            flags=re.IGNORECASE,
        ).strip()

    return ""


def calculate_score(prop: dict) -> tuple[int, list[str]]:
    score = 0
    signals: list[str] = []

    title = prop.get("titulo") or ""
    description = prop.get("descripcion_tarjeta") or ""
    neighborhood = prop.get("barrio") or ""

    text = normalize_text(f"{title} {description}")
    normalized_neighborhood = normalize_text(neighborhood)

    price = prop.get("precio_usd")
    area = prop.get("area_m2")
    bedrooms = prop.get("dormitorios")
    bathrooms = prop.get("banos")
    usd_m2 = prop.get("usd_m2")

    # Superficie
    if area:
        if area >= 250:
            score += 28
            signals.append("250 m² o más")
        elif area >= 180:
            score += 23
            signals.append("180 m² o más")
        elif area >= 150:
            score += 18
            signals.append("150 m² o más")
        elif area >= 120:
            score += 12
            signals.append("120 m² o más")

    # Precio por metro cuadrado
    if usd_m2:
        if usd_m2 < 700:
            score += 25
            signals.append("menos de USD 700/m²")
        elif usd_m2 < 900:
            score += 20
            signals.append("menos de USD 900/m²")
        elif usd_m2 < 1_100:
            score += 12
            signals.append("menos de USD 1.100/m²")

    # Dormitorios y baños
    if bedrooms:
        if bedrooms >= 6:
            score += 18
            signals.append("6 dormitorios o más")
        elif bedrooms >= 4:
            score += 12
            signals.append("4 dormitorios o más")
        elif bedrooms >= 3:
            score += 5
            signals.append("3 dormitorios")

    if bathrooms:
        if bathrooms >= 3:
            score += 12
            signals.append("3 baños o más")
        elif bathrooms >= 2:
            score += 7
            signals.append("2 baños")

    # Palabras clave
    for keyword, points in KEYWORD_RULES.items():
        if keyword in text:
            score += points
            signals.append(keyword)

    # Barrio
    for barrio, points in TARGET_NEIGHBORHOODS.items():
        if barrio in normalized_neighborhood:
            score += points
            signals.append(f"zona objetivo: {neighborhood}")
            break

    # Penalizaciones
    if price and price > MAX_PRICE_USD:
        score -= 25
        signals.append("sobre precio máximo")

    if area and area < MIN_AREA_M2:
        score -= 20
        signals.append("superficie reducida")

    # Sin datos suficientes
    if not area:
        score -= 15
        signals.append("sin superficie")

    if not price:
        score -= 15
        signals.append("sin precio USD")

    return max(0, min(score, 100)), sorted(set(signals))


def extract_property(
    card: Locator,
    page_number: int,
) -> dict | None:
    link_locator = card.locator("a.lc-data")

    if link_locator.count() == 0:
        return None

    relative_link = safe_attribute(link_locator, "href")

    if not relative_link:
        return None

    link = urljoin(BASE_URL, relative_link)
    title = safe_attribute(link_locator, "title")

    if not title:
        title = safe_text(card.locator(".lc-title"))

    price_text = safe_text(card.locator(".main-price"))
    location_text = safe_text(card.locator(".lc-location"))
    description = safe_text(card.locator(".lc-description"))
    agency = safe_text(card.locator(".lc-owner-name"))
    full_text = card.inner_text().strip()
    image_url = safe_attribute(card.locator("img"), "src")

    currency = None
    price_usd = None

    if "U$S" in price_text.upper() or "USD" in price_text.upper():
        currency = "USD"
        price_usd = clean_number(price_text)

    bedrooms = extract_first_number(
        full_text,
        [
            r"(\d+)\s*dormitorios?",
            r"(\d+)\s*dorms?\.?",
        ],
    )

    bathrooms = extract_first_number(
        full_text,
        [
            r"(\d+)\s*baños?",
            r"(\d+)\s*bañ\.?",
        ],
    )

    area_m2 = extract_first_number(
        full_text,
        [
            r"(\d+)\s*m²",
            r"(\d+)\s*m2",
            r"(\d+)\s*mt2",
            r"(\d+)\s*metros cuadrados",
        ],
    )

    neighborhood = extract_neighborhood(location_text)

    external_id_match = re.search(r"/(\d+)(?:\?.*)?$", link)
    external_id = (
        external_id_match.group(1)
        if external_id_match
        else link
    )

    usd_m2 = None

    if price_usd and area_m2:
        usd_m2 = round(price_usd / area_m2, 2)

    prop = {
        "fecha_extraccion": datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "fuente": "InfoCasas",
        "pagina": page_number,
        "external_id": external_id,
        "titulo": title,
        "precio_texto": price_text,
        "moneda": currency,
        "precio_usd": price_usd,
        "area_m2": area_m2,
        "usd_m2": usd_m2,
        "dormitorios": bedrooms,
        "banos": bathrooms,
        "ubicacion_texto": location_text,
        "barrio": neighborhood,
        "ciudad": "Montevideo",
        "inmobiliaria": agency,
        "imagen_principal": image_url,
        "link": link,
        "descripcion_tarjeta": " ".join(description.split()),
        "texto_tarjeta": " ".join(full_text.split()),
    }

    score, signals = calculate_score(prop)

    prop["score"] = score
    prop["senales"] = " | ".join(signals)

    return prop


def page_url(page_number: int) -> str:
    if page_number == 1:
        return SEARCH_BASE

    return f"{SEARCH_BASE}/pagina{page_number}"


def main() -> None:
    rows: list[dict] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)

        page = browser.new_page(
            viewport={"width": 1440, "height": 900},
            locale="es-UY",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120 Safari/537.36"
            ),
        )

        for page_number in range(1, MAX_PAGES + 1):
            url = page_url(page_number)
            print(f"\nPágina {page_number}: {url}")

            try:
                page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=60000,
                )

                page.wait_for_selector(
                    ".listingBoxCard",
                    timeout=30000,
                )

                page.wait_for_timeout(2000)

                cards = page.locator(".listingBoxCard")
                card_count = cards.count()

                print(f"Tarjetas encontradas: {card_count}")

                if card_count == 0:
                    print("No hay más propiedades. Finalizando.")
                    break

                for index in range(card_count):
                    try:
                        prop = extract_property(
                            cards.nth(index),
                            page_number,
                        )

                        if prop:
                            rows.append(prop)

                    except Exception as error:
                        print(
                            f"Error en página {page_number}, "
                            f"tarjeta {index + 1}: {error}"
                        )

                # Pequeña pausa para no golpear el sitio.
                time.sleep(1)

            except Exception as error:
                print(
                    f"Error procesando página {page_number}: {error}"
                )

        browser.close()

    df = pd.DataFrame(rows)

    if df.empty:
        print("No se extrajeron propiedades.")
        pd.DataFrame().to_csv(
            "propiedades_infocasas.csv",
            index=False,
        )
        pd.DataFrame().to_csv(
            "top_oportunidades.csv",
            index=False,
        )
        return

    df = df.drop_duplicates(subset=["external_id"])

    # Archivo completo
    df = df.sort_values(
        by=["score", "usd_m2"],
        ascending=[False, True],
        na_position="last",
    )

    df.to_csv(
        "propiedades_infocasas.csv",
        index=False,
    )

    # Filtro razonable para el MVP
    candidates = df[
        (df["precio_usd"].between(
            MIN_PRICE_USD,
            MAX_PRICE_USD,
            inclusive="both",
        ))
        & (
            df["area_m2"].isna()
            | (df["area_m2"] >= MIN_AREA_M2)
        )
    ].copy()

    top = candidates.head(30)

    top.to_csv(
        "top_oportunidades.csv",
        index=False,
    )

    print("\nRESUMEN")
    print(f"Propiedades únicas: {len(df)}")
    print(f"Candidatas dentro del rango: {len(candidates)}")
    print(f"TOP exportadas: {len(top)}")

    print("\nTOP 15")
    print(
        top[
            [
                "score",
                "titulo",
                "precio_usd",
                "area_m2",
                "usd_m2",
                "dormitorios",
                "banos",
                "barrio",
                "senales",
                "link",
            ]
        ]
        .head(15)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
