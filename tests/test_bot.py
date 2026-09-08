import unittest
from unittest.mock import Mock, patch

from sniper_deals import Product, fetch_products, find_new_products, format_message, translate_text
from history import append_history, render_dashboard


class FindNewProductsTest(unittest.TestCase):
    def test_returns_only_unseen_products_in_source_order(self):
        products = [
            Product("3", "Novo", "50", "43", "https://img/3", "https://cssdeals.com/3"),
            Product("2", "Antigo", "40", "42", "https://img/2", "https://cssdeals.com/2"),
        ]

        self.assertEqual([products[0]], find_new_products(products, {"2"}))

    def test_send_all_ignores_seen_ids(self):
        products = [
            Product("3", "Novo", "50", "43", "https://img/3", "https://cssdeals.com/3"),
            Product("2", "Antigo", "40", "42", "https://img/2", "https://cssdeals.com/2"),
        ]

        self.assertEqual(products, find_new_products(products, {"2", "3"}, send_all=True))

    @patch("sniper_deals.request.urlopen")
    def test_fetches_and_maps_cssdeals_api(self, urlopen):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"data":{"records":[{"id":"9","title":"Chain Sneakers","skus":[{"price":132.86,"skuNames":"Black 41","image":"https://img/9.jpg"}]}]}}'
        urlopen.return_value = response

        products = fetch_products()

        self.assertEqual(Product("9", "Chain Sneakers", "132.86", "Black 41", "https://img/9.jpg", "https://cssdeals.com/product-detail.html?itemid=9"), products[0])

    def test_formats_telegram_message_in_portuguese(self):
        product = Product("9", "Tênis de corrente", "132.86", "Preto 41", "https://img/9.jpg", "https://cssdeals.com/product-detail.html?itemid=9")

        message = format_message(product)

        self.assertIn("Tênis de corrente", message)
        self.assertIn("¥132.86", message)
        self.assertIn("Preto 41", message)
        self.assertIn(product.url, message)

    @patch("sniper_deals.request.urlopen")
    def test_translates_text_with_free_google_endpoint(self, urlopen):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = '[[["Tênis de corrente","Chain Sneakers",null,null,1]]]'.encode()
        urlopen.return_value = response

        self.assertEqual("Tênis de corrente", translate_text("Chain Sneakers"))


class HistoryTest(unittest.TestCase):
    def test_prepends_new_entry_and_removes_previous_duplicate(self):
        product = Product("9", "Tênis", "132.86", "Preto 41", "https://img/9.jpg", "https://cssdeals.com/9")
        existing = [{"id": "9", "title": "antigo", "sent_at": "2026-01-01T00:00:00Z"}]

        history = append_history(existing, product, "2026-09-08T12:00:00Z")

        self.assertEqual(1, len(history))
        self.assertEqual("Tênis", history[0]["title"])
        self.assertEqual("2026-09-08T12:00:00Z", history[0]["sent_at"])

    def test_caps_history_at_max_items(self):
        product = Product("new", "Novo", "1", "u", "https://img", "https://cssdeals.com/new")
        existing = [{"id": str(i), "sent_at": "x"} for i in range(100)]

        history = append_history(existing, product, "now", max_items=100)

        self.assertEqual(100, len(history))
        self.assertEqual("new", history[0]["id"])


class DashboardTest(unittest.TestCase):
    def test_renders_card_for_each_history_entry(self):
        history = [
            {
                "id": "9",
                "title": "Tênis de corrente",
                "price": "132.86",
                "sku": "Preto 41",
                "image": "https://img/9.jpg",
                "url": "https://cssdeals.com/9",
                "sent_at": "2026-09-08T12:00:00Z",
            }
        ]

        html = render_dashboard(history)

        self.assertIn("Tênis de corrente", html)
        self.assertIn("¥132.86", html)
        self.assertIn("Preto 41", html)
        self.assertIn("https://img/9.jpg", html)
        self.assertIn("https://cssdeals.com/9", html)
        self.assertIn("2026-09-08T12:00:00Z", html)

    def test_renders_empty_state_message_without_entries(self):
        html = render_dashboard([])

        self.assertIn("Nenhum item enviado ainda", html)


if __name__ == "__main__":
    unittest.main()
