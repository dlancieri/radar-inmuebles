from models import Property
from scoring import calculate_score
from database import init_db, upsert_property, export_opportunities_csv


def get_mock_properties():
    return [
        Property(
            source="Mock",
            external_id="mock-001",
            title="Casa antigua a reciclar con padrón único",
            price_usd=135000,
            area_m2=180,
            neighborhood="Cordón",
            city="Montevideo",
            link="https://example.com/mock-001",
            description="Casa amplia con patio, azotea, varios ambientes, ideal inversor. Posibilidad de reciclar."
        ),
        Property(
            source="Mock",
            external_id="mock-002",
            title="Local y vivienda con fondo",
            price_usd=95000,
            area_m2=120,
            neighborhood="La Comercial",
            city="Montevideo",
            link="https://example.com/mock-002",
            description="Local al frente y vivienda al fondo, dos entradas independientes, ideal renta."
        ),
        Property(
            source="Mock",
            external_id="mock-003",
            title="Apartamento moderno",
            price_usd=145000,
            area_m2=55,
            neighborhood="Pocitos",
            city="Montevideo",
            link="https://example.com/mock-003",
            description="Apartamento pronto para entrar, un dormitorio."
        ),
    ]


def main():
    init_db()

    properties = get_mock_properties()

    for prop in properties:
        score, signals, usd_m2 = calculate_score(prop)
        upsert_property(prop, score, signals, usd_m2)

    df = export_opportunities_csv()

    print("Oportunidades detectadas:")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
