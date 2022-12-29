# Copyright (C) 2022 Akretion (<http://www.akretion.com>).
# @author Kévin Roche <kevin.roche@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.addons.base_rest import restapi
from odoo.addons.component.core import AbstractComponent, Component
from odoo.addons.datamodel import fields
from odoo.addons.datamodel.core import Datamodel
from odoo.addons.shopinvader_gift_card.services.gift_card import (
    JSONIFY_GIFT_CARD,
    JSONIFY_GIFT_CARD_LINE,
)


class GiftCardCodeInput(Datamodel):
    _name = "gift.card.code.input"
    code = fields.String(required=True)


class GiftCardLineInput(Datamodel):
    _name = "gift.card.line.input"
    line_id = fields.Integer()


class GiftCardPaymentInput(Datamodel):
    _name = "gift.card.payment.input"
    target = fields.String(required=True)
    code = fields.String(required=True)
    amount = fields.Float()


class PaymentServiceGiftCard(AbstractComponent):

    _name = "payment.service.gift.card"
    _inherit = "base.rest.service"
    _usage = "payment_gift_card"
    _description = "REST Services for Gift Card payments"

    @property
    def payment_service(self):
        return self.component(usage="invader.payment")

    def _parser_giftcard(self):
        return JSONIFY_GIFT_CARD

    def _parser_giftcard_line(self):
        return JSONIFY_GIFT_CARD_LINE

    @restapi.method(
        routes=[(["/confirm_payment"], "POST")],
        input_param=restapi.Datamodel("gift.card.payment.input"),
    )
    def confirm_payment(self, params):
        payable = self.payment_service._invader_find_payable_from_target(
            params.target
        )
        acquirer = self.env.ref("account_payment_gift_card.payment_acquirer_gift_card")
        transaction = self.env["payment.transaction"].create(
            payable._invader_prepare_payment_transaction_data(acquirer)
        )
        gift_card = self.env["gift.card"].check_gift_card_code(params.code)
        if params.amount:
            transaction.amount = min(params.amount, transaction.amount)
        line = self.env["gift.card.line"].create(
                {
                "gift_card_id": gift_card.id,
                "name": gift_card.name,
                "beneficiary_id": transaction.partner_id.id,
                "code": params.code,
                "amount_used": transaction.amount,
                "transaction_id": transaction.id,
                "payment_id": transaction.payment_id.id,
                    }
        )
        transaction._set_transaction_done()
        return line.jsonify(self._parser_giftcard_line())

    @restapi.method(
        routes=[(["/get_by_code"], "GET")],
        input_param=restapi.Datamodel("gift.card.code.input"),
    )
    def get_by_code(self, params):
        params = params.dump()
        code = params.get("code", " no_code ")
        gift_card = self.env["gift.card"].search([("code", "=", code)])
        if gift_card:
            self.env["gift.card"].check_gift_card_code(gift_card.code)
            if gift_card.state == "active":
                return gift_card.jsonify(self._parser_giftcard())


    @restapi.method(
        routes=[(["/cancel_payment"], "POST")],
        input_param=restapi.Datamodel("gift.card.line.input"),
    )
    def cancel_payment(self, params):
        line = self.env["gift.card.line"].browse(params.line_id)
        line.transaction_id.state = "cancel"
        line.unlink()
        return {}


class PaymentServiceGiftCardShopinvader(Component):
    _name = "payment.service.gift.card.shopinvader"
    _inherit = ["base.shopinvader.service", "payment.service.gift.card"]
    _usage = "payment_gift_card"
    _collection = "shopinvader.backend"
