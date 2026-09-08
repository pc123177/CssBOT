import unittest
from unittest.mock import Mock, patch

from sniper_deals import Product, fetch_products, find_new_products, format_message, translate_text


class FindNewProductsTest(unittest.TestCase):
    def test_returns_only_unseen_products_in_source_order(self):
        products = [
            Product("3", "Novo", "50", "43", "https://img/3", "https://cssdeals.com/3"),
            Product("2", "Antigo", "40", "42", "https://img/2", "https://cssdeals.com/2"),
        ]

        self.assertEqual([products[0]], find_new_products(products, {"2"}))

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


if __name__ == "__main__":
    unittest.main()
