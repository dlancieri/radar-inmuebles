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


RECONVERSION_RULES = {
    "posibilidad de hacer apartamentos": 35,
    "posibilidad de apartamentos": 35,
    "varias unidades": 30,
    "generar varias unidades": 30,
    "mas de una renta": 25,
    "más de una renta": 25,

    "doble acceso": 22,
    "dos accesos": 22,
    "accesos independientes": 22,
    "entrada independiente": 18,
    "entradas independientes": 20,
    "pasaje lateral": 18,
    "corredor lateral": 18,
    "acceso lateral": 18,
    "esquina": 15,

    "padron unico": 18,
    "mismo padron": 15,
    "gran terreno": 15,
    "fondo grande": 15,
    "terreno de": 6,

    "para reciclar": 15,
    "a reciclar": 15,
    "a refaccionar": 15,
    "reciclaje": 12,
    "requiere mejoras": 8,

    "varios ambientes": 12,
    "espacios amplios": 10,
    "techos altos": 10,
    "altura de techos": 8,
    "dos plantas": 8,
    "planta alta": 5,
    "planta baja": 5,

    "local comercial": 8,
    "galpon": 6,
    "depósito": 5,
    "deposito": 5,
    "azotea transitable": 6,
}

IMMEDIATE_RENT_RULES = {
    "dos casas": 30,
    "2 casas": 30,
    "tres casas": 35,
    "3 casas": 35,
    "varias viviendas": 30,
    "apartamento independiente": 25,
    "apto independiente": 25,
    "segunda vivienda": 25,
    "segunda construccion": 18,
    "segunda construcción": 18,
    "tercera construccion": 20,
    "tercera construcción": 20,
    "ya alquilado": 15,
    "con renta": 12,
}

PENALTY_RULES = {
    "nuda propiedad": -70,
    "usufructo": -50,
    "derechos posesorios": -40,
    "ocupada": -25,
    "ocupado": -25,
    "solo contado": -8,
    "proteccion patrimonial": -8,
    "protección patrimonial": -8,
    "propiedad horizontal": -12,
    "ph": -5,
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


def calculate_score(prop: dict) -> tuple[int, int, list[str]]:
    reconversion_score = 0
    immediate_rent_score = 0
    signals: list[str] = []

    title = prop.get("titulo") or ""
    description = prop.get("descripcion_tarjeta") or ""
    full_card = prop.get("texto_tarjeta") or ""
    neighborhood = prop.get("barrio") or ""

    text = normalize_text(
        f"{title} {description} {full_card}"
    )
    normalized_neighborhood = normalize_text(neighborhood)

    price = prop.get("precio_usd")
    area = prop.get("area_m2")
    bedrooms = prop.get("dormitorios")
    bathrooms = prop.get("banos")
    usd_m2 = prop.get("usd_m2")

    # Superficie: ayuda, pero no debe dominar.
    if area:
        if area >= 300:
            reconversion_score += 24
            signals.append("300 m² o más")
        elif area >= 220:
            reconversion_score += 20
            signals.append("220 m² o más")
        elif area >= 180:
            reconversion_score += 16
            signals.append("180 m² o más")
        elif area >= 150:
            reconversion_score += 12
            signals.append("150 m² o más")
        elif area >= 120:
            reconversion_score += 7
            signals.append("120 m² o más")

    # USD/m².
    if usd_m2:
        if usd_m2 < 650:
            reconversion_score += 20
            signals.append("menos de USD 650/m²")
        elif usd_m2 < 850:
            reconversion_score += 15
            signals.append("menos de USD 850/m²")
        elif usd_m2 < 1050:
            reconversion_score += 8
            signals.append("menos de USD 1.050/m²")

    # Distribución existente.
    if bedrooms:
        if bedrooms >= 6:
            reconversion_score += 14
            signals.append("6 dormitorios o más")
        elif bedrooms >= 4:
            reconversion_score += 9
            signals.append("4 dormitorios o más")

    if bathrooms:
        if bathrooms >= 4:
            reconversion_score += 16
            signals.append("4 baños o más")
        elif bathrooms >= 3:
            reconversion_score += 11
            signals.append("3 baños")
        elif bathrooms >= 2:
            reconversion_score += 6
            signals.append("2 baños")

    # Señales de reconversión.
    for keyword, points in RECONVERSION_RULES.items():
        if keyword in text:
            reconversion_score += points
            signals.append(keyword)

    # Señales de renta ya existente.
    for keyword, points in IMMEDIATE_RENT_RULES.items():
        if keyword in text:
            immediate_rent_score += points
            signals.append(f"renta inmediata: {keyword}")

    # Penalizaciones.
    for keyword, points in PENALTY_RULES.items():
        if keyword in text:
            reconversion_score += points
            immediate_rent_score += points
            signals.append(f"penalización: {keyword}")

    # Zonas preferidas.
    for barrio, points in TARGET_NEIGHBORHOODS.items():
        if barrio in normalized_neighborhood:
            reconversion_score += points
            immediate_rent_score += points // 2
            signals.append(f"zona objetivo: {neighborhood}")
            break

    # Precio absoluto.
    if price:
        if price > 250_000:
            reconversion_score -= 25
            immediate_rent_score -= 20
            signals.append("precio superior a USD 250.000")
        elif price > 220_000:
            reconversion_score -= 15
            signals.append("precio superior a USD 220.000")
        elif price <= 150_000:
            reconversion_score += 8
            signals.append("precio hasta USD 150.000")
    else:
        reconversion_score -= 15
        immediate_rent_score -= 15

    if not area:
        reconversion_score -= 15
        signals.append("sin superficie confiable")

    return (
        max(0, min(reconversion_score, 100)),
        max(0, min(immediate_rent_score, 100)),
        sorted(set(signals)),
    )


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
            r"superficie cubierta(?: de)?\s*(\d+)\s*m",
            r"area total construida:\s*(\d+)",
            r"área total construida:\s*(\d+)",
            r"(\d+)\s*m²\s*construidos",
            r"(\d+)\s*m2\s*construidos",
            r"(\d+)\s*metros\s*construidos",
            r"(\d+)\s*m²",
            r"(\d+)\s*m2",
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

    reconversion_score, immediate_rent_score, signals = calculate_score(prop)

    prop["score_reconversion"] = reconversion_score
    prop["score_renta_inmediata"] = immediate_rent_score
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

    # Base completa.
    df.to_csv(
        "propiedades_infocasas.csv",
        index=False,
    )
    
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
    
    top_reconversion = candidates.sort_values(
        by=["score_reconversion", "usd_m2"],
        ascending=[False, True],
        na_position="last",
    ).head(30)
    
    top_renta = candidates.sort_values(
        by=["score_renta_inmediata", "score_reconversion"],
        ascending=[False, False],
    ).head(30)
    
    top_reconversion.to_csv(
        "top_reconversion.csv",
        index=False,
    )
    
    top_renta.to_csv(
        "top_renta_inmediata.csv",
        index=False,
    )
    
    print("\nRESUMEN")
    print(f"Propiedades únicas: {len(df)}")
    print(f"Candidatas: {len(candidates)}")
    
    print("\nTOP RECONVERSIÓN")
    print(
        top_reconversion[
            [
                "score_reconversion",
                "score_renta_inmediata",
                "titulo",
                "precio_usd",
                "area_m2",
                "usd_m2",
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
