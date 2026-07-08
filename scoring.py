KEYWORDS = {
    "reciclar": 15,
    "a reciclar": 20,
    "ideal inversor": 15,
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
}


def calculate_score(prop):
    text = f"{prop.title} {prop.description}".lower()
    score = 0
    signals = []

    for keyword, points in KEYWORDS.items():
        if keyword in text:
            score += points
            signals.append(keyword)

    if prop.area_m2 >= 120:
        score += 20
        signals.append("más de 120 m²")

    if prop.area_m2 >= 160:
        score += 15
        signals.append("más de 160 m²")

    if prop.price_usd and prop.area_m2:
        usd_m2 = prop.price_usd / prop.area_m2

        if usd_m2 < 900:
            score += 20
            signals.append("USD/m² bajo")
        elif usd_m2 < 1200:
            score += 10
            signals.append("USD/m² razonable")
    else:
        usd_m2 = None

    return min(score, 100), signals, usd_m2
