import os
import tempfile
import unittest

from users import UserStore


class UserStoreTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.store = UserStore(self.path)

    def tearDown(self):
        self.store.close()
        os.remove(self.path)

    def test_registers_user_and_returns_active_users(self):
        self.store.register("123", "Paulo")

        users = self.store.active_users()

        self.assertEqual("123", users[0]["chat_id"])
        self.assertEqual("Paulo", users[0]["name"])
        self.assertFalse(users[0]["paused"])

    def test_updates_filters_and_pause_state(self):
        self.store.register("123", "Paulo")
        self.store.update("123", include="nike", exclude="used", max_price="100", platforms="1,2")
        self.store.set_paused("123", True)

        user = self.store.get("123")

        self.assertEqual("nike", user["include"])
        self.assertEqual("used", user["exclude"])
        self.assertEqual("100", user["max_price"])
        self.assertEqual("1,2", user["platforms"])
        self.assertTrue(user["paused"])

    def test_unsubscribes_user(self):
        self.store.register("123", "Paulo")
        self.store.unsubscribe("123")

        self.assertEqual([], self.store.active_users())

    def test_persists_users_after_reopening_database(self):
        self.store.register("1", "Alice")
        self.store.close()

        reopened = UserStore(self.path)
        self.assertEqual("Alice", reopened.get("1")["name"])
        reopened.close()
        self.store = UserStore(self.path)

    def test_tracks_alerts_per_user_and_product(self):
        self.store.register("123", "Paulo")

        self.store.mark_sent("123", "product-1", "10")

        self.assertTrue(self.store.was_sent("123", "product-1"))
        self.assertEqual("10", self.store.last_price("123", "product-1"))


if __name__ == "__main__":
    unittest.main()
