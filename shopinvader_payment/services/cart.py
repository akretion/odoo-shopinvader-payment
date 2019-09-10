# Copyright 2017 Akretion (http://www.akretion.com).
# @author Sébastien BEAU <sebastien.beau@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).


from odoo.addons.component.core import Component


class CartService(Component):

    _inherit = "shopinvader.cart.service"

    def _convert_one_sale(self, sale):
        """
        Add Payment information into cart
        :return:
        """
        values = super()._convert_one_sale(sale)
        values.update({"payment": self._get_shopinvader_payment_data(sale)})
        return values

    def _get_shopinvader_payment_data(self, sale):
        """
        Specific method to shopinvader to retrieve the payment dict information
        to pass to the front-end
        * Available methods
        * The payment mode
        * The amount
        :return:
        """
        self.ensure_one()
        payment_methods = sale._invader_get_available_payment_methods()
        selected_method = payment_methods.filtered(
            lambda m: m.payment_mode_id == self.payment_mode_id
        )
        values = {
            "available_methods": {
                "count": len(payment_methods),
                "items": [
                    {
                        "id": method.payment_mode_id.id,
                        "name": method.payment_mode_id.name,
                        "provider": method.payment_mode_id.payment_acquirer_id.provider,
                        "code": method.code,
                        "description": method.description,
                    }
                    for method in payment_methods
                ],
            },
            "selected_method": self._get_payment_method_data(selected_method),
            "amount": sale.amount_total,
        }
        return values
