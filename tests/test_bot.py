import json
import unittest
from unittest.mock import Mock, patch

from sniper_deals import (
    Product, apply_filters, fetch_products, find_new_products, format_message,
    get_price_drops, handle_command, load_health, mark_daily_report_if_due, poll_commands,
    record_failure, record_success, retry, send_telegram, should_alert_failure, status_report,
    translate_text,
)
from history import append_history, render_dashboard


class RetryTest(unittest.TestCase):
    def test_retries_with_exponential_backoff(self):
        calls = []
        sleeps = []

        def operation():
            calls.append(1)
            if len(calls) < 3:
                raise OSError("temporary")
            return "ok"

        self.assertEqual("ok", retry(operation, attempts=3, base_delay=2, sleep=sleeps.append))
        self.assertEqual([2, 4], sleeps)


class ProductFeaturesTest(unittest.TestCase):
    def product(self, id="1", title="Nike shoe", price="80", platform="Taobao"):
        return Product(id, title, price, "Black 42", "https://img", "https://css/1",
                       "https://original/1", platform, "3")

    def test_alert_contains_source_platform_and_quantity(self):
        message = format_message(self.product())
        self.assertIn("https://original/1", message)
        self.assertIn("Taobao", message)
        self.assertIn("3", message)

    def test_filters_products_from_environment_style_values(self):
        products = [self.product(), self.product("2", "Adidas shoe", "120", "Weidian")]
        result = apply_filters(products, include="nike", exclude="used", max_price="100", platforms="taobao")
        self.assertEqual([products[0]], result)

    def test_detects_price_drops_and_updates_prices(self):
        prices = {"1": "100", "2": "20"}
        products = [self.product(price="80"), self.product("2", price="25")]
        drops = get_price_drops(products, prices)
        self.assertEqual([(products[0], "100")], drops)
        self.assertEqual({"1": "80", "2": "25"}, prices)


class TelegramTest(unittest.TestCase):
    @patch("sniper_deals.time.sleep")
    @patch("sniper_deals.request.urlopen")
    def test_send_photo_retries_then_falls_back_to_message(self, urlopen, _sleep):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"ok":true}'
        urlopen.side_effect = [OSError("photo"), OSError("photo"), OSError("photo"), response]
        send_telegram(Product("1", "Shoe", "10", "42", "img", "url"), "token", "chat")
        self.assertEqual(4, urlopen.call_count)
        self.assertTrue(urlopen.call_args.args[0].full_url.endswith("/sendMessage"))


class PaginationTest(unittest.TestCase):
    @patch("sniper_deals.time.sleep")
    @patch("sniper_deals.request.urlopen")
    def test_fetch_retries_transient_cssdeals_failure(self, urlopen, _sleep):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"data":{"records":[]}}'
        urlopen.side_effect = [OSError("temporary"), response]
        self.assertEqual([], fetch_products())
        self.assertEqual(2, urlopen.call_count)

    @patch("sniper_deals.time.sleep")
    @patch("sniper_deals.request.urlopen")
    def test_fetches_pages_until_page_contains_only_seen_ids(self, urlopen, _sleep):
        def response(records):
            value = Mock()
            value.__enter__ = Mock(return_value=value)
            value.__exit__ = Mock(return_value=False)
            value.read.return_value = json.dumps({"data": {"records": records}}).encode()
            return value
        def record(id):
            return {"id": id, "title": id, "skus": [{"price": 1, "skuNames": "x", "image": "i"}]}
        first_page = [record("new")] + [record(f"new-{i}") for i in range(19)]
        urlopen.side_effect = [response(first_page), response([record("old")])]
        products = fetch_products(max_pages=100, seen_ids={"old"})
        self.assertEqual("new", products[0].id)
        self.assertEqual("old", products[-1].id)
        self.assertEqual(2, urlopen.call_count)


class HealthTest(unittest.TestCase):
    def test_tracks_failures_success_and_formats_report(self):
        state = load_health("missing-health-test.json")
        record_failure(state, "boom", "2026-09-08T10:00:00Z")
        self.assertEqual(1, state["failure_count"])
        record_success(state, "2026-09-08T11:00:00Z")
        self.assertEqual(0, state["failure_count"])
        self.assertIn("2026-09-08T11:00:00Z", status_report(state))


    def test_failure_threshold_alerts_once(self):
        state = {"failure_count": 3, "last_alerted_failure": 0}
        self.assertTrue(should_alert_failure(state, threshold=3))
        self.assertFalse(should_alert_failure(state, threshold=3))

    def test_daily_report_is_due_once_per_utc_day(self):
        state = {"last_report_date": "2026-09-07"}
        self.assertTrue(mark_daily_report_if_due(state, "2026-09-08T11:00:00+00:00"))
        self.assertFalse(mark_daily_report_if_due(state, "2026-09-08T18:00:00+00:00"))


class CommandTest(unittest.TestCase):
    def test_status_command_returns_health(self):
        state = {"failure_count": 0, "last_success": "2026-09-08T11:00:00Z", "last_failure": None}
        self.assertIn("Último sucesso", handle_command("/status", state, [], {}))

    def test_pause_and_resume_commands_update_settings(self):
        settings = {"paused": False}
        self.assertIn("pausado", handle_command("/pausar", {}, [], settings).lower())
        self.assertTrue(settings["paused"])
        self.assertIn("retomado", handle_command("/retomar", {}, [], settings).lower())
        self.assertFalse(settings["paused"])

    def test_latest_command_lists_recent_products(self):
        history = [{"title": "Tênis", "price": "50", "url": "https://css/1"}]
        message = handle_command("/ultimos", {}, history, {})
        self.assertIn("Tênis", message)
        self.assertIn("https://css/1", message)

    def test_filter_commands_update_settings(self):
        settings = {}
        handle_command("/incluir nike,adidas", {}, [], settings)
        handle_command("/excluir used", {}, [], settings)
        handle_command("/precomax 100", {}, [], settings)
        handle_command("/plataformas 1,2", {}, [], settings)
        self.assertEqual("nike,adidas", settings["filter_include"])
        self.assertEqual("used", settings["filter_exclude"])
        self.assertEqual("100", settings["filter_max_price"])
        self.assertEqual("1,2", settings["filter_platforms"])

    @patch("sniper_deals._telegram_call")
    @patch("sniper_deals.request.urlopen")
    def test_polls_only_authorized_chat_and_advances_offset(self, urlopen, telegram_call):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps({"ok": True, "result": [
            {"update_id": 10, "message": {"chat": {"id": 999}, "text": "/pausar"}},
            {"update_id": 11, "message": {"chat": {"id": 123}, "text": "/pausar"}},
        ]}).encode()
        urlopen.return_value = response
        settings = {"paused": False}

        offset = poll_commands("token", "123", {}, [], settings, offset=5)

        self.assertEqual(12, offset)
        self.assertTrue(settings["paused"])
        telegram_call.assert_called_once()


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

        self.assertEqual(Product("9", "Chain Sneakers", "132.86", "Black 41", "https://img/9.jpg", "https://cssdeals.com/detail/9"), products[0])

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

    @patch("sniper_deals.request.urlopen")
    def test_translate_prefers_local_libretranslate_over_google(self, urlopen):
        def fake_open(req, *a, **kw):
            if req.host.startswith("127.0.0.1"):
                response = Mock()
                response.__enter__ = Mock(return_value=response)
                response.__exit__ = Mock(return_value=False)
                response.read.return_value = '{"translatedText": "Tênis de corrente"}'.encode()
                return response
            raise AssertionError("não deveria chamar o Google quando LibreTranslate funciona")

        urlopen.side_effect = fake_open
        urlopen.return_value = Mock()

        self.assertEqual("Tênis de corrente", translate_text("Chain Sneakers"))

    @patch("sniper_deals.request.urlopen")
    def test_translate_falls_back_to_google_when_local_fails(self, urlopen):
        def fake_open(req, *a, **kw):
            if req.host.startswith("127.0.0.1"):
                raise ConnectionError("LibreTranslate fora do ar")
            response = Mock()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            response.read.return_value = '[[["Tênis de corrente","Chain Sneakers",null,null,1]]]'.encode()
            return response

        urlopen.side_effect = fake_open

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

    def test_escapes_untrusted_product_markup(self):
        history = [{"id": "x", "title": "<script>alert(1)</script>", "price": "1",
                    "sku": "x", "image": "javascript:alert(1)",
                    "url": "javascript:alert(1)", "sent_at": "now"}]
        page = render_dashboard(history)
        self.assertNotIn("<script>", page)
        self.assertNotIn("javascript:alert", page)
        self.assertIn("&lt;script&gt;", page)

    def test_renders_empty_state_message_without_entries(self):
        html = render_dashboard([])

        self.assertIn("Nenhum item enviado ainda", html)


if __name__ == "__main__":
    unittest.main()
