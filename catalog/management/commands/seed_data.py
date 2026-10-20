from django.core.management.base import BaseCommand
from django.utils.text import slugify

from catalog.models import Brand, CarModel, Region

# Коды регионов по данным ГРС/«Унаа». Проверьте и при необходимости поправьте в админке.
REGIONS = [
    ("01", "Бишкек"),
    ("02", "Ош"),
    ("03", "Баткенская область"),
    ("04", "Джалал-Абадская область"),
    ("05", "Нарынская область"),
    ("06", "Ошская область"),
    ("07", "Таласская область"),
    ("08", "Чуйская область"),
    ("09", "Иссык-Кульская область"),
    ("10", "Легализованные автомобили"),
    ("11", "Временный ввоз"),
]

BRANDS = {
    "Toyota": ["Camry", "Corolla", "Prius", "RAV4", "Land Cruiser", "Land Cruiser Prado", "Highlander", "Alphard", "Vitz", "Mark II", "Sienta", "Hilux"],
    "Honda": ["Fit", "Civic", "Accord", "CR-V", "Odyssey", "Stepwgn", "Vezel", "Freed"],
    "Mercedes-Benz": ["C-Class", "E-Class", "S-Class", "G-Class", "GLE", "GLK", "Sprinter", "Vito"],
    "BMW": ["3 Series", "5 Series", "7 Series", "X5", "X3", "X6"],
    "Lexus": ["RX", "LX", "GX", "ES", "IS", "LS"],
    "Nissan": ["Qashqai", "X-Trail", "Note", "Juke", "Teana", "Patrol"],
    "Hyundai": ["Solaris", "Sonata", "Elantra", "Tucson", "Santa Fe", "Accent", "Starex"],
    "Kia": ["Rio", "Optima", "Sportage", "Sorento", "Cerato", "K5"],
    "Subaru": ["Forester", "Outback", "Legacy", "Impreza", "XV"],
    "Mazda": ["3", "6", "CX-5", "Demio", "Axela"],
    "Mitsubishi": ["Outlander", "Pajero", "Lancer", "L200", "Delica"],
    "Volkswagen": ["Golf", "Passat", "Tiguan", "Touareg", "Polo", "Jetta"],
    "Audi": ["A4", "A6", "Q5", "Q7", "A3", "100"],
    "Chevrolet": ["Lacetti", "Cruze", "Spark", "Cobalt", "Aveo", "Malibu"],
    "Daewoo": ["Matiz", "Nexia", "Gentra", "Damas"],
    "Ford": ["Focus", "Fusion", "Escape", "Explorer", "Transit"],
    "Opel": ["Astra", "Vectra", "Zafira", "Omega", "Vivaro"],
    "Lada": ["2106", "2107", "2109", "2110", "Priora", "Granta", "Niva", "Vesta"],
    "GAZ": ["Gazelle", "Volga", "Sobol"],
    "UAZ": ["Patriot", "Bukhanka", "Hunter"],
    "Chery": ["Tiggo", "Arrizo", "QQ"],
    "Geely": ["Coolray", "Atlas", "Emgrand"],
    "BYD": ["Han", "Song", "Qin", "Tang", "Seal"],
    "Haval": ["Jolion", "H6", "F7"],
    "Tesla": ["Model 3", "Model Y", "Model S", "Model X"],
    "Land Rover": ["Range Rover", "Discovery", "Defender"],
    "Porsche": ["Cayenne", "Macan", "Panamera", "911"],
    "Infiniti": ["QX56", "QX80", "FX35", "G35"],
}


class Command(BaseCommand):
    help = "Заполняет регионы КР и популярные марки/модели (безопасно запускать повторно)"

    def handle(self, *args, **options):
        for code, name in REGIONS:
            Region.objects.update_or_create(code=code, defaults={"name": name})
        models_added = 0
        for brand_name, models in BRANDS.items():
            brand, _ = Brand.objects.get_or_create(
                name=brand_name, defaults={"slug": slugify(brand_name) or brand_name.lower()}
            )
            for model_name in models:
                _, created = CarModel.objects.get_or_create(
                    brand=brand, slug=slugify(model_name) or model_name.lower(),
                    defaults={"name": model_name},
                )
                models_added += int(created)
        self.stdout.write(self.style.SUCCESS(
            f"Регионов: {Region.objects.count()}, марок: {Brand.objects.count()}, "
            f"моделей: {CarModel.objects.count()} (новых моделей: {models_added})"
        ))
