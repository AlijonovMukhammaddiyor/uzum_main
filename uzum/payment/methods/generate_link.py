import base64
from dataclasses import dataclass
from decimal import Decimal

import requests

from config.settings.base import env


@dataclass
class GeneratePayLink:
    """
    GeneratePayLink dataclass
    That's used to generate pay lint for each order.

    Parameters
    ----------
    order_id: int — The order_id for paying
    amount: int — The amount belong to the order

    Returns str — pay link
    ----------------------

    Full method documentation
    -------------------------
    https://developer.help.paycom.uz/initsializatsiya-platezhey/
    """

    order_id: str
    amount: Decimal

    def __init__(self, order_id: str, amount: Decimal) -> None:
        self.order_id = order_id
        self.amount = self.to_tiyin(amount)

    def generate_link(self) -> str:
        """
        GeneratePayLink for each order.
        """
        PAYME_ID = env.str("PAYME_ID")
        PAYME_ACCOUNT = env.str("PAYME_ACCOUNT")
        PAYME_CALL_BACK_URL = env.str("PAYME_CALLBACK_URL")
        PAYME_URL = env.str("PAYME_URL")
        PAYME_KEY = env.str("PAYME_KEY")
        print("Your payme key is: ", PAYME_KEY)

        generated_pay_link: str = "{payme_url}/{encode_params}"
        params: str = "m={payme_id};ac.{payme_account}={order_id};a={amount};c={call_back_url}"
        # print(PAYME_URL, PAYME_ID, PAYME_ACCOUNT, self.order_id, self.amount, PAYME_CALL_BACK_URL)
        params = params.format(
            payme_id=PAYME_ID,
            payme_account=PAYME_ACCOUNT,
            order_id=self.order_id,
            amount=self.amount,
            call_back_url=PAYME_CALL_BACK_URL,
        )
        encode_params = base64.b64encode(params.encode("utf-8"))

        # res = requests.post(
        #     url=PAYME_URL,
        #     data={
        #         "merchant": PAYME_ID,
        #         # "merchant": "64d64878a3b6d0cc97f5fbcc",
        #         "amount": self.amount,
        #         "account[order_id]": self.order_id,
        #         "callback": PAYME_CALL_BACK_URL,
        #         "lang": "ru",
        #     },
        # )

        # data = res.text
        # print(data)
        return generated_pay_link.format(payme_url=PAYME_URL, encode_params=str(encode_params, "utf-8"))

    @staticmethod
    def to_tiyin(amount: Decimal) -> Decimal:
        """
        Convert from soum to tiyin.

        Parameters
        ----------
        amount: Decimal -> order amount
        """
        return amount * 100

    @staticmethod
    def to_soum(amount: Decimal) -> Decimal:
        """
        Convert from tiyin to soum.

        Parameters
        ----------
        amount: Decimal -> order amount
        """
        return amount / 100
