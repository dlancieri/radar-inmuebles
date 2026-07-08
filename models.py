from dataclasses import dataclass
from datetime import datetime


@dataclass
class Property:
    source: str
    external_id: str
    title: str
    price_usd: float
    area_m2: float
    neighborhood: str
    city: str
    link: str
    description: str
    detected_at: str = datetime.now().strftime("%Y-%m-%d")
