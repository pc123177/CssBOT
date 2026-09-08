import json
import os
import sys
from dataclasses import dataclass
from urllib import parse, request

BASE_URL = "https://cssdeals.com"
API_URL = f"{BASE_URL}/api/product?fields=1&page=1&pageSize=20"
STATE_FILE = "seen_ids.json"


@dataclass(frozen=True)
class Product:
    id: str
    title: str
    price: str
    sku: str
    image: str
    url: str


def find_new_products(products: list[Product], seen_ids: set[str], send_all: bool = False) -> list[Product]:
    if send_all:
        return list(products)
    return [product for product in products if product.id not in seen_ids]


def fetch_products() -> list[Product]:
    req = request.Request(API_URL, headers={"User-Agent": "SniperDeals/1.0"})
    with request.urlopen(req, timeout=30) as response:
        records = json.loads(response.read())["data"]["records"]
    products = []
    for record in records:
        sku = record["skus"][0]
        product_id = str(record["id"])
        products.append(Product(
            product_id,
            record["title"],
            str(sku["price"]),
            sku.get("skuNames") or f'{sku.get("color", "")} {sku.get("size", "")}'.strip(),
            sku["image"],
            f"{BASE_URL}/product-detail.html?itemid={product_id}",
        ))
    return products


def translate_text(text: str) -> str:
    if not text:
        return text
    query = parse.urlencode({"client": "gtx", "sl": "auto", "tl": "pt", "dt": "t", "q": text})
    req = request.Request(f"https://translate.googleapis.com/translate_a/single?{query}", headers={"User-Agent": "Mozilla/5.0"})
    try:
        with request.urlopen(req, timeout=20) as response:
            data = json.loads(response.read())
        return "".join(part[0] for part in data[0])
    except Exception as error:
        print(f"Aviso: tradução falhou ({error}); usando texto original.")
        return text


def format_message(product: Product) -> str:
    return (
        "🎯 Novo item no CSSDeals!\n\n"
        f"📦 {product.title}\n"
        f"💴 ¥{product.price}\n"
        f"📏 {product.sku or 'Não informado'}\n\n"
        f"🔗 {product.url}"
    )


def send_telegram(product: Product, token: str, chat_id: str) -> None:
    data = parse.urlencode({
        "chat_id": chat_id,
        "photo": product.image,
        "caption": format_message(product),
    }).encode()
    req = request.Request(f"https://api.telegram.org/bot{token}/sendPhoto", data=data)
    with request.urlopen(req, timeout=30) as response:
        result = json.loads(response.read())
    if not result.get("ok"):
        raise RuntimeError(f"Telegram rejeitou o alerta: {result}")


def load_seen_ids() -> set[str]:
    try:
        with open(STATE_FILE, encoding="utf-8") as state:
            return set(json.load(state))
    except FileNotFoundError:
        return set()


def save_seen_ids(ids: set[str]) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as state:
        json.dump(sorted(ids), state, indent=2)
        state.write("\n")


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        sys.exit("Defina TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID.")

    send_all = os.environ.get("SEND_ALL", "").lower() in ("1", "true", "yes")

    products = fetch_products()
    seen_ids = load_seen_ids()
    if not seen_ids and not send_all:
        save_seen_ids({product.id for product in products})
        print(f"Primeira execução: {len(products)} itens registrados, sem alertas antigos.")
        return

    new_products = find_new_products(products, seen_ids, send_all=send_all)
    for product in reversed(new_products):
        translated = Product(
            product.id,
            translate_text(product.title),
            product.price,
            translate_text(product.sku),
            product.image,
            product.url,
        )
        send_telegram(translated, token, chat_id)
        seen_ids.add(product.id)
        save_seen_ids(seen_ids)
    print(f"Monitoramento concluído: {len(new_products)} item(ns) novo(s).")


if __name__ == "__main__":
    main()
