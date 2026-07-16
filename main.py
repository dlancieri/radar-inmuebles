import re
from datetime import datetime
from urllib.parse import urljoin

import pandas as pd
from playwright.sync_api import Locator, sync_playwright


BASE_URL = "https://www.infocasas.com.uy"
SEARCH_URL = "https://www.infocasas.com.uy/venta/casas/montevideo"


def clean_number(value: str) -> float | None:
    """Convierte textos como 445.000 o 1.250,50 en números."""
    if not value:
        return None

    cleaned = re.sub(r"[^\d.,]", "", value).strip()

    if not cleaned:
        return None

    # Formato uruguayo habitual: 445.000 o 1.250,50
    cleaned = cleaned.replace(".", "").replace(",", ".")

    try:
        return float(cleaned)
    except ValueError:
        return None


def extract_first_number(text: str, patterns: list[str]) -> int | None:
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


def safe_attribute(locator: Locator, attribute: str) -> str:
    try:
        if locator.count() > 0:
            return locator.first.get_attribute(attribute) or ""
    except Exception:
        pass

    return ""


def extract_property(card: Locator) -> dict | None:
    link_locator = card.locator("a.lc-data")

    if link_locator.count() == 0:
        return None

    relative_link = safe_attribute(link_locator, "href")

    if not relative_link:
        return None

    link = urljoin(BASE_URL, relative_link)

    title = safe_attribute(link_locator, "title")

    if not title:
        title = safe_text(link_locator)

    price_text = safe_text(card.locator(".main-price"))
    location_text = safe_text(card.locator(".lc-location"))
    agency = safe_text(card.locator(".lc-owner-name"))
    full_text = card.inner_text().strip()

    image_url = safe_attribute(card.locator("img"), "src")

    price_usd = None
    currency = None

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
            r"(\d+)\s*bañ\.",
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

    neighborhood = ""
    city = "Montevideo"

    # Ejemplo: "Casa en Pocitos, Montevideo"
    location_match = re.search(
        r"(?:Casa|Propiedad)\s+en\s+(.+?),\s*Montevideo",
        location_text,
        flags=re.IGNORECASE,
    )

    if location_match:
        neighborhood = location_match.group(1).strip()
    elif "," in location_text:
        neighborhood = location_text.split(",")[0]
        neighborhood = re.sub(
            r"^(Casa|Propiedad)\s+en\s+",
            "",
            neighborhood,
            flags=re.IGNORECASE,
        ).strip()

    external_id_match = re.search(r"/(\d+)(?:\?.*)?$", link)
    external_id = external_id_match.group(1) if external_id_match else link

    usd_m2 = None

    if price_usd and area_m2 and area_m2 > 0:
        usd_m2 = round(price_usd / area_m2, 2)

    return {
        "fecha_extraccion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "fuente": "InfoCasas",
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
        "ciudad": city,
        "inmobiliaria": agency,
        "imagen_principal": image_url,
        "link": link,
        "texto_tarjeta": " ".join(full_text.split()),
    }


def main() -> None:
    rows: list[dict] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)

        page = browser.new_page(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120 Safari/537.36"
            ),
            locale="es-UY",
        )

        print(f"Abriendo: {SEARCH_URL}")

        page.goto(
            SEARCH_URL,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        page.wait_for_selector(
            ".listingBoxCard",
            timeout=30000,
        )

        page.wait_for_timeout(3000)

        cards = page.locator(".listingBoxCard")
        total_cards = cards.count()

        print(f"Tarjetas encontradas: {total_cards}")

        for index in range(total_cards):
            try:
                prop = extract_property(cards.nth(index))

                if prop:
                    rows.append(prop)
                    print(
                        f"{len(rows):02d}. "
                        f"{prop['titulo'][:70]} — "
                        f"{prop['precio_texto']}"
                    )

            except Exception as error:
                print(f"Error procesando tarjeta {index + 1}: {error}")

        browser.close()

    columns = [
        "fecha_extraccion",
        "fuente",
        "external_id",
        "titulo",
        "precio_texto",
        "moneda",
        "precio_usd",
        "area_m2",
        "usd_m2",
        "dormitorios",
        "banos",
        "ubicacion_texto",
        "barrio",
        "ciudad",
        "inmobiliaria",
        "imagen_principal",
        "link",
        "texto_tarjeta",
    ]

    df = pd.DataFrame(rows, columns=columns)

    if not df.empty:
        df = df.drop_duplicates(subset=["link"])
        df = df.sort_values(
            by=["precio_usd", "area_m2"],
            ascending=[True, False],
            na_position="last",
        )

    # Se crea siempre, aun si no hay resultados.
    df.to_csv("propiedades_infocasas.csv", index=False)

    print()
    print(f"Propiedades guardadas: {len(df)}")
    print("Archivo generado: propiedades_infocasas.csv")

    if not df.empty:
        print()
        print(
            df[
                [
                    "titulo",
                    "precio_usd",
                    "area_m2",
                    "usd_m2",
                    "barrio",
                    "link",
                ]
            ]
            .head(10)
            .to_string(index=False)
        )


if __name__ == "__main__":
    main()
