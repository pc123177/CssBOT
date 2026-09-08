import json


def append_history(history: list[dict], product, sent_at: str, max_items: int = 100) -> list[dict]:
    entry = {
        "id": product.id,
        "title": product.title,
        "price": product.price,
        "sku": product.sku,
        "image": product.image,
        "url": product.url,
        "sent_at": sent_at,
    }
    return ([entry] + [item for item in history if item["id"] != product.id])[:max_items]


def load_history(path: str) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as state:
            return json.load(state)
    except FileNotFoundError:
        return []


def save_history(path: str, history: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as state:
        json.dump(history, state, ensure_ascii=False, indent=2)
        state.write("\n")


def render_dashboard(history: list[dict]) -> str:
    if not history:
        cards = "<p>Nenhum item enviado ainda.</p>"
    else:
        cards = "\n".join(
            f'''<article class="card">
  <img src="{item["image"]}" alt="{item["title"]}" loading="lazy">
  <h2>{item["title"]}</h2>
  <p class="price">¥{item["price"]}</p>
  <p class="sku">{item["sku"] or ""}</p>
  <p class="date">{item["sent_at"]}</p>
  <a href="{item["url"]}" target="_blank" rel="noopener">Ver no CSSDeals</a>
</article>'''
            for item in history
        )
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>SniperDeals — Itens enviados</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body {{ font-family: system-ui, sans-serif; background: #111; color: #eee; margin: 0; padding: 24px; }}
h1 {{ text-align: center; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; max-width: 1200px; margin: 24px auto; }}
.card {{ background: #1c1c1c; border-radius: 8px; padding: 12px; }}
.card img {{ width: 100%; border-radius: 6px; aspect-ratio: 1; object-fit: cover; }}
.card h2 {{ font-size: 15px; margin: 8px 0 4px; }}
.price {{ color: #4ade80; font-weight: bold; }}
.sku, .date {{ color: #999; font-size: 12px; }}
.card a {{ display: inline-block; margin-top: 8px; color: #60a5fa; text-decoration: none; }}
</style>
</head>
<body>
<h1>🎯 SniperDeals — Itens enviados</h1>
<div class="grid">
{cards}
</div>
</body>
</html>
"""
