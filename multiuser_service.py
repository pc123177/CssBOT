import json
import os
import sys
from urllib import parse, request

from multiuser import MultiUserBot
from sniper_deals import (
    Product, _telegram_call, fetch_products, format_message, load_json, retry,
    translate_text,
)
from users import UserStore

STATE_FILE = "multiuser_state.json"
DATABASE_FILE = "users.db"


def send_text(token: str, chat_id: str, text: str) -> None:
    data = parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    _telegram_call(f"https://api.telegram.org/bot{token}/sendMessage", data)


def poll_updates(token: str, offset: int) -> tuple[list[dict], int]:
    url = f"https://api.telegram.org/bot{token}/getUpdates?timeout=45&offset={offset}"
    with retry(lambda: request.urlopen(url, timeout=60)) as response:
        payload = json.loads(response.read())
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram getUpdates falhou: {payload}")
    updates = payload.get("result", [])
    next_offset = max([offset] + [int(update["update_id"]) + 1 for update in updates])
    return updates, next_offset


def translated(product: Product) -> Product:
    return Product(
        product.id, translate_text(product.title), product.price,
        translate_text(product.sku), product.image, product.url,
        product.source_link, product.sale_platform, product.quantity,
    )


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    admin_chat_id = os.environ.get("TELEGRAM_ADMIN_CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID")
    invite_code = os.environ.get("INVITE_CODE", "")
    if not token or not admin_chat_id or not invite_code:
        sys.exit("Defina TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_CHAT_ID e INVITE_CODE.")

    state = load_json(STATE_FILE, {"offset": 0, "known_ids": []})
    store = UserStore(DATABASE_FILE)

    def sender(value):
        if len(value) == 2:
            chat_id, text = value
            send_text(token, chat_id, text)
            return
        chat_id, product, is_drop, old_price = value
        item = translated(product)
        message = format_message(item)
        if is_drop:
            message = f"📉 Queda de preço: ¥{old_price} → ¥{product.price}\n\n{message}"
        from sniper_deals import send_telegram
        send_telegram(item, token, chat_id, message)

    bot = MultiUserBot(store, invite_code, admin_chat_id, sender)
    try:
        # Migra o administrador automaticamente na primeira execução.
        if not store.get(admin_chat_id):
            store.register(admin_chat_id, "Administrador")
        products = fetch_products(max_pages=int(os.environ.get("CSSDEALS_MAX_PAGES", "5")))
        known_ids = set(state.get("known_ids", []))
        for product in reversed(products):
            bot.deliver(product, allow_new=product.id not in known_ids)
        state["known_ids"] = list(dict.fromkeys(
            [product.id for product in products] + list(state.get("known_ids", []))))[:2000]

        updates, next_offset = poll_updates(token, int(state.get("offset", 0)))
        for update in updates:
            message = update.get("message") or {}
            text = message.get("text", "")
            chat = message.get("chat") or {}
            if not text.startswith("/") or "id" not in chat:
                continue
            name = " ".join(filter(None, [message.get("from", {}).get("first_name"),
                                           message.get("from", {}).get("last_name")]))
            try:
                reply = bot.command(str(chat["id"]), name, text)
            except ValueError:
                reply = "Valor inválido. Exemplo: /precomax 100"
            send_text(token, str(chat["id"]), reply)
        state["offset"] = next_offset
        with open(STATE_FILE, "w", encoding="utf-8") as output:
            json.dump(state, output, indent=2)
            output.write("\n")
    finally:
        store.close()


if __name__ == "__main__":
    main()
