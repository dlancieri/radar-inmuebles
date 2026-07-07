KEYWORDS = {
    "a reciclar": 15,
    "reciclar": 12,
    "ideal inversor": 10,
    "inversor": 8,
    "padrón único": 12,
    "padron unico": 12,
    "dos entradas": 10,
    "entrada independiente": 10,
    "fondo": 8,
    "patio": 6,
    "azotea": 8,
    "varios ambientes": 8,
    "varios dormitorios": 8,
    "local y vivienda": 12,
    "propiedad horizontal": 6,
    "permite construir": 12,
    "gran terreno": 10,
}

def score_property(title, description, price_usd=None, m2=None):
    text = f"{title or ''} {description or ''}".lower()
    score = 0
    signals = []

    if m2:
        if m2 >= 120:
            score += 20
            signals.append("más de 120 m²")
        if m2 >= 160:
            score += 15
            signals.append("más de 160 m²")

    if price_usd and m2:
        usd_m2 = price_usd / m2
        if usd_m2 < 900:
            score += 15
            signals.append("USD/m² bajo")
        elif usd_m2 < 1200:
            score += 8
            signals.append("USD/m² razonable")
    else:
        score -= 20
        signals.append("faltan m² o precio")

    for keyword, points in KEYWORDS.items():
        if keyword in text:
            score += points
            signals.append(keyword)

    if price_usd and price_usd > 180000:
        score -= 15
        signals.append("precio sobre rango objetivo")

    return min(score, 100), list(set(signals))
