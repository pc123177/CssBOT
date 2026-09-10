import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib import parse, request

from history import append_history, load_history, render_dashboard, save_history

BASE_URL = "https://cssdeals.com"
API_URL = f"{BASE_URL}/api/product?fields=1&page=1&pageSize=20"
STATE_FILE = "seen_ids.json"
HISTORY_FILE = "docs/history.json"
DASHBOARD_FILE = "docs/index.html"
PRICE_FILE = "prices.json"
HEALTH_FILE = "health.json"
SETTINGS_FILE = "settings.json"
TELEGRAM_FILE = "telegram_state.json"


def retry(operation, attempts: int = 3, base_delay: float = 1, sleep=time.sleep):
    for attempt in range(attempts):
        try:
            return operation()
        except Exception:
            if attempt == attempts - 1:
                raise
            sleep(base_delay * (2 ** attempt))


@dataclass(frozen=True)
class Product:
    id: str
    title: str
    price: str
    sku: str
    image: str
    url: str
    source_link: str = ""
    sale_platform: str = ""
    quantity: str = ""


def _csv(value: str) -> list[str]:
    return [part.strip().lower() for part in value.split(",") if part.strip()]


def apply_filters(products: list[Product], include: str = "", exclude: str = "",
                  max_price: str = "", platforms: str = "") -> list[Product]:
    includes, excludes, allowed = _csv(include), _csv(exclude), _csv(platforms)
    limit = float(max_price) if max_price else None
    return [p for p in products if
            (not includes or any(word in p.title.lower() for word in includes)) and
            not any(word in p.title.lower() for word in excludes) and
            (limit is None or float(p.price) <= limit) and
            (not allowed or p.sale_platform.lower() in allowed)]


def get_price_drops(products: list[Product], prices: dict[str, str]) -> list[tuple[Product, str]]:
    drops = []
    for product in products:
        old_price = prices.get(product.id)
        if old_price is not None and float(product.price) < float(old_price):
            drops.append((product, old_price))
        prices[product.id] = product.price
    return drops


def _map_product(record: dict) -> Product:
    skus = record.get("skus") or []
    first_sku = skus[0] if skus else {}
    price = first_sku.get("price") or record.get("price") or 0
    if isinstance(price, str):
        price = price.strip()
    images = record.get("images") or []
    image = first_sku.get("image") or (images[0].get("url") if images and isinstance(images[0], dict) else "")
    return Product(
        id=str(record["id"]),
        title=record.get("title", ""),
        price=str(price),
        sku=first_sku.get("skuNames", first_sku.get("name", "")),
        image=image,
        url=f"{BASE_URL}/product-detail.html?itemid={record['id']}",
        source_link=(record.get("sourceLink") or "").strip(),
        sale_platform=str(record.get("salePlatform", "")),
        quantity=str(first_sku.get("quantity", "")),
    )


def fetch_products(max_pages: int = 1, seen_ids: set[str] | None = None) -> list[Product]:
    all_products: list[Product] = []
    seen = seen_ids or set()
    for page in range(1, max_pages + 1):
        url = f"{BASE_URL}/api/product?fields=1&page={page}&pageSize=20"
        req = request.Request(url, headers={'User-Agent': 'SniperDeals/1.0'})
        response = retry(lambda: request.urlopen(req, timeout=30))
        with response as response:
            data = json.loads(response.read())
        products = [_map_product(record) for record in data.get("data", {}).get("records", [])]
        all_products.extend(products)
        if seen and all(product.id in seen for product in products):
            break
    return all_products


def find_new_products(products: list[Product], seen_ids: set[str],
                      send_all: bool = False) -> list[Product]:
    if send_all:
        return list(products)
    new = [product for product in products if product.id not in seen_ids]
    seen_ids.update(product.id for product in products)
    return new


def format_message(product: Product) -> str:
    return (
        "🎯 Novo item no CSSDeals!\n\n"
        f"📦 {product.title}\n"
        f"💴 ¥{product.price}\n"
        f"📏 {product.sku or 'Não informado'}\n"
        f"🏪 {product.sale_platform or 'Não informado'}\n"
        f"🔢 Quantidade: {product.quantity or 'Não informada'}\n\n"
        f"🔗 {product.url}"
        + (f"\n🔗 Link original: {product.source_link}" if product.source_link else "")
    )


def _telegram_call(url: str, data: bytes) -> None:
    def send():
        with request.urlopen(request.Request(url, data=data), timeout=30) as response:
            result = json.loads(response.read())
        if not result.get("ok"):
            raise RuntimeError(f"Telegram rejeitou o alerta: {result}")
    retry(send)


def send_telegram(product: Product, token: str, chat_id: str, message: str | None = None) -> None:
    message = message or format_message(product)
    photo_data = parse.urlencode({"chat_id": chat_id, "photo": product.image, "caption": message}).encode()
    try:
        _telegram_call(f"https://api.telegram.org/bot{token}/sendPhoto", photo_data)
    except Exception:
        text_data = parse.urlencode({"chat_id": chat_id, "text": message}).encode()
        _telegram_call(f"https://api.telegram.org/bot{token}/sendMessage", text_data)


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


def load_json(path: str, default):
    try:
        with open(path, encoding="utf-8") as state:
            return json.load(state)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: str, value) -> None:
    dir_name = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as state:
            json.dump(value, state, ensure_ascii=False, indent=2)
            state.write("\n")
            state.flush()
            os.fsync(state.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_health(path: str = HEALTH_FILE) -> dict:
    return load_json(path, {"failure_count": 0, "last_success": None, "last_failure": None, "last_error": None})


def record_failure(state: dict, error: Exception, now: str) -> None:
    state["failure_count"] = state.get("failure_count", 0) + 1
    state["last_failure"] = now
    state["last_error"] = str(error)


def record_success(state: dict, now: str) -> None:
    state["failure_count"] = 0
    state["last_success"] = now
    state["last_error"] = None


def status_report(state: dict) -> str:
    return ("📊 Status diário SniperDeals\n"
            f"Falhas consecutivas: {state.get('failure_count', 0)}\n"
            f"Último sucesso: {state.get('last_success') or 'nunca'}\n"
            f"Última falha: {state.get('last_failure') or 'nenhuma'}")


def should_alert_failure(state: dict, threshold: int = 3) -> bool:
    count = state.get("failure_count", 0)
    if count < threshold or state.get("last_alerted_failure") == count:
        return False
    state["last_alerted_failure"] = count
    return True


def mark_daily_report_if_due(state: dict, at: str) -> bool:
    day = at[:10]
    if state.get("last_report_date") == day:
        return False
    state["last_report_date"] = day
    return True


def handle_command(text: str, health: dict, history: list[dict], settings: dict) -> str:
    command, _, argument = text.strip().partition(" ")
    command = command.lower().split("@", 1)[0]
    if command == "/status":
        return status_report(health)
    if command == "/ultimos":
        if not history:
            return "Nenhum item enviado ainda."
        return "🕘 Últimos itens\n\n" + "\n\n".join(
            f"📦 {item.get('title', '')}\n💴 ¥{item.get('price', '')}\n🔗 {item.get('url', '')}"
            for item in history[:5])
    if command == "/pausar":
        settings["paused"] = True
        return "⏸️ Monitoramento pausado."
    if command == "/retomar":
        settings["paused"] = False
        return "▶️ Monitoramento retomado."
    if command == "/incluir":
        settings["filter_include"] = argument.strip()
        return f"✅ Filtro de inclusão: {argument.strip() or 'desativado'}"
    if command == "/excluir":
        settings["filter_exclude"] = argument.strip()
        return f"✅ Filtro de exclusão: {argument.strip() or 'desativado'}"
    if command == "/precomax":
        if argument.strip():
            float(argument.strip())
        settings["filter_max_price"] = argument.strip()
        return f"✅ Preço máximo: {argument.strip() or 'desativado'}"
    if command == "/plataformas":
        settings["filter_platforms"] = argument.strip()
        return f"✅ Plataformas: {argument.strip() or 'todas'}"
    return ("Comandos: /status, /ultimos, /pausar, /retomar, "
            "/incluir palavras, /excluir palavras, /precomax valor, /plataformas lista")


def poll_commands(token: str, chat_id: str, health: dict, history: list[dict],
                  settings: dict, offset: int = 0) -> int:
    url = f"https://api.telegram.org/bot{token}/getUpdates?timeout=0&offset={offset}"
    with retry(lambda: request.urlopen(url, timeout=15)) as response:
        payload = json.loads(response.read())
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram getUpdates falhou: {payload}")
    next_offset = offset
    for update in payload.get("result", []):
        next_offset = max(next_offset, int(update["update_id"]) + 1)
        message = update.get("message") or {}
        if str((message.get("chat") or {}).get("id")) != str(chat_id):
            continue
        text = message.get("text", "")
        if not text.startswith("/"):
            continue
        try:
            reply = handle_command(text, health, history, settings)
        except ValueError:
            reply = "Valor inválido. Exemplo: /precomax 100"
        data = parse.urlencode({"chat_id": chat_id, "text": reply}).encode()
        _telegram_call(f"https://api.telegram.org/bot{token}/sendMessage", data)
    return next_offset


def _translate_libre(text: str) -> str:
    query = parse.urlencode({"q": text, "source": "auto", "target": "pt"})
    req = request.Request("http://127.0.0.1:5000/translate", data=query.encode(), headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "SniperDeals/1.0"})
    with request.urlopen(req, timeout=15) as response:
        data = json.loads(response.read())
    translated = data.get("translatedText")
    return translated if translated and not translated.startswith("[") else text


def _translate_google(text: str) -> str:
    query = parse.urlencode({"client": "gtx", "sl": "auto", "tl": "pt", "dt": "t", "q": text})
    req = request.Request(f"https://translate.googleapis.com/translate_a/single?{query}", headers={"User-Agent": "Mozilla/5.0"})
    with request.urlopen(req, timeout=20) as response:
        data = json.loads(response.read())
    return "".join(part[0] for part in data[0])


def translate_text(text: str) -> str:
    if not text:
        return text
    try:
        translated = _translate_libre(text)
        if translated != text:
            return translated
    except Exception as error:
        print(f"Aviso: LibreTranslate falhou ({error}); tentando Google...")
    try:
        return _translate_google(text)
    except Exception as error:
        print(f"Aviso: tradução Google falhou ({error}); usando texto original.")
        return text


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        sys.exit("Defina TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID no .env")

    send_all = os.environ.get("SEND_ALL", "").lower() in ("1", "true", "yes")
    seen_ids = load_seen_ids()
    health = load_health()
    history = load_history(HISTORY_FILE)
    settings = load_json(SETTINGS_FILE, {"paused": False})
    telegram_state = load_json(TELEGRAM_FILE, {"offset": 0})
    telegram_state["offset"] = poll_commands(
        token, chat_id, health, history, settings, int(telegram_state.get("offset", 0)))
    save_json(SETTINGS_FILE, settings)
    save_json(TELEGRAM_FILE, telegram_state)
    if settings.get("paused"):
        print("Monitoramento pausado pelo Telegram.")
        return
    now = datetime.now(timezone.utc).isoformat()
    try:
        max_pages = min(int(os.environ.get("CSSDEALS_MAX_PAGES", "5")), 100)
        products = fetch_products(max_pages=max_pages, seen_ids=seen_ids)
        discovered_ids = {product.id for product in products}
        alert_candidates = apply_filters(
            products,
            settings.get("filter_include", os.environ.get("FILTER_INCLUDE", "")),
            settings.get("filter_exclude", os.environ.get("FILTER_EXCLUDE", "")),
            settings.get("filter_max_price", os.environ.get("FILTER_MAX_PRICE", "")),
            settings.get("filter_platforms", os.environ.get("FILTER_PLATFORMS", "")))
        prices = load_json(PRICE_FILE, {})
        drops = get_price_drops(alert_candidates, prices)
        save_json(PRICE_FILE, prices)
        if not seen_ids and not send_all:
            save_seen_ids(discovered_ids)
            record_success(health, now)
            save_json(HEALTH_FILE, health)
            print(f"Primeira execução: {len(products)} itens registrados, sem alertas antigos.")
            return

        new_products = find_new_products(alert_candidates, seen_ids, send_all=send_all)
        drop_ids = {product.id: old for product, old in drops if product.id not in {p.id for p in new_products}}
        history = load_history(HISTORY_FILE)
        alert_products = new_products + [product for product, _old in drops if product.id in drop_ids]
        for product in reversed(alert_products):
            translated = Product(
                product.id, translate_text(product.title), product.price,
                translate_text(product.sku), product.image, product.url,
                product.source_link, product.sale_platform, product.quantity,
            )
            if product.id in drop_ids:
                old_price = drop_ids[product.id]
                message = f"📉 Queda de preço: ¥{old_price} → ¥{product.price}\n\n{format_message(translated)}"
                data = parse.urlencode({"chat_id": chat_id, "text": message}).encode()
                _telegram_call(f"https://api.telegram.org/bot{token}/sendMessage", data)
            else:
                send_telegram(translated, token, chat_id)
            history = append_history(history, product, now)
            save_history(HISTORY_FILE, history)

        seen_ids.update(discovered_ids)
        save_seen_ids(seen_ids)
        os.makedirs("docs", exist_ok=True)
        with open(DASHBOARD_FILE, "w", encoding="utf-8") as dashboard:
            dashboard.write(render_dashboard(history))
        record_success(health, now)
        if int(datetime.now(timezone.utc).strftime("%H")) == int(os.environ.get("DAILY_REPORT_UTC_HOUR", "12")):
            if mark_daily_report_if_due(health, now):
                data = parse.urlencode({"chat_id": chat_id, "text": status_report(health)}).encode()
                _telegram_call(f"https://api.telegram.org/bot{token}/sendMessage", data)
        save_json(HEALTH_FILE, health)
        print(f"Monitoramento concluído: {len(new_products)} item(ns) novo(s), {len(drop_ids)} queda(s) de preço.")
    except Exception as error:
        record_failure(health, error, now)
        if should_alert_failure(health, int(os.environ.get("FAILURE_ALERT_THRESHOLD", "3"))):
            try:
                data = parse.urlencode({
                    "chat_id": chat_id,
                    "text": f"🚨 SniperDeals falhou {health['failure_count']} vezes seguidas.\nErro: {error}",
                }).encode()
                _telegram_call(f"https://api.telegram.org/bot{token}/sendMessage", data)
            except Exception as alert_error:
                print(f"Falha ao enviar alerta de saúde: {alert_error}")
        save_json(HEALTH_FILE, health)
        raise


if __name__ == "__main__":
    main()
