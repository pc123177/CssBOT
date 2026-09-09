import os
import tempfile
import unittest

from multiuser import MultiUserBot
from sniper_deals import Product
from users import UserStore


class MultiUserBotTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.store = UserStore(self.path)
        self.sent = []
        self.bot = MultiUserBot(self.store, "invite-123", "999", self.sent.append)

    def tearDown(self):
        self.store.close()
        os.remove(self.path)

    def test_start_requires_valid_invite_code(self):
        reply = self.bot.command("123", "Alice", "/start wrong")
        self.assertIn("inválido", reply.lower())
        self.assertIsNone(self.store.get("123"))

        reply = self.bot.command("123", "Alice", "/start invite-123")
        self.assertIn("cadastrado", reply.lower())
        self.assertIsNotNone(self.store.get("123"))

    def test_subscribed_user_can_list_own_recent_deliveries(self):
        self.store.register("123", "Alice")
        self.store.mark_sent("123", "p1", "80", title="Nike shoe", url="https://css/p1")

        reply = self.bot.command("123", "Alice", "/ultimos")

        self.assertIn("Nike shoe", reply)
        self.assertIn("https://css/p1", reply)

    def test_subscribed_user_can_manage_preferences_and_stop(self):
        self.store.register("123", "Alice")
        self.bot.command("123", "Alice", "/incluir nike")
        self.bot.command("123", "Alice", "/precomax 100")
        self.bot.command("123", "Alice", "/pausar")
        self.assertTrue(self.store.get("123")["paused"])
        self.bot.command("123", "Alice", "/retomar")
        self.assertFalse(self.store.get("123")["paused"])
        self.bot.command("123", "Alice", "/parar")
        self.assertFalse(self.store.get("123")["active"])

    def test_admin_commands_are_restricted(self):
        self.store.register("123", "Alice")
        self.assertIn("restrito", self.bot.command("123", "Alice", "/usuarios").lower())
        self.assertIn("Alice", self.bot.command("999", "Admin", "/usuarios"))

    def test_admin_broadcast_sends_to_all_active_users(self):
        self.store.register("1", "Alice")
        self.store.register("2", "Bob")

        reply = self.bot.command("999", "Admin", "/broadcast Manutenção hoje")

        self.assertIn("2", reply)
        self.assertEqual([("1", "Manutenção hoje"), ("2", "Manutenção hoje")], self.sent)

    def test_admin_keeps_original_alert_channel_without_duplicate_multiuser_delivery(self):
        self.store.register("999", "Admin")
        product = Product("p1", "Shoe", "80", "42", "img", "url")

        self.bot.deliver(product)

        self.assertEqual([], self.sent)

    def test_product_is_sent_once_only_to_matching_active_users(self):
        self.store.register("1", "Nike fan")
        self.store.update("1", include="nike", max_price="100")
        self.store.register("2", "Expensive")
        self.store.update("2", include="nike", max_price="50")
        product = Product("p1", "Nike shoe", "80", "42", "img", "url")

        self.bot.deliver(product)
        self.bot.deliver(product)

        self.assertEqual([("1", product, False, None)], self.sent)

    def test_existing_inventory_is_not_sent_to_new_user(self):
        self.store.register("1", "Alice")
        product = Product("old", "Old shoe", "80", "42", "img", "url")

        self.bot.deliver(product, allow_new=False)

        self.assertEqual([], self.sent)

    def test_price_drop_is_sent_to_user_who_received_product(self):
        self.store.register("1", "Alice")
        old = Product("p1", "Shoe", "100", "42", "img", "url")
        cheaper = Product("p1", "Shoe", "80", "42", "img", "url")
        self.bot.deliver(old)

        self.bot.deliver(cheaper)

        self.assertEqual(("1", cheaper, True, "100"), self.sent[-1])


if __name__ == "__main__":
    unittest.main()
