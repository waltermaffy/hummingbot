from unittest import TestCase

from hummingbot.connector.exchange.changelly import changelly_constants as CONSTANTS, changelly_web_utils as web_utils


class WebUtilsTests(TestCase):
    def test_rest_url(self):
        url = web_utils.public_rest_url(path_url=CONSTANTS.ORDER_BOOK)
        self.assertEqual("https://api.pro.changelly.com/api/3/public/orderbook", url)
