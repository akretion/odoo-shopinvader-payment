# Copyright 2017 Akretion (http://www.akretion.com).
# Copyright 2019 ACSONE SA/NV (http://acsone.eu).
# @author Sébastien BEAU <sebastien.beau@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import logging

import stripe

from odoo.addons.component.core import Component
from odoo.addons.payment_stripe.models.payment import INT_CURRENCIES
from odoo.tools.float_utils import float_round

_logger = logging.getLogger(__name__)

# map Stripe transaction statuses to Odoo payment.transaction statuses
STRIPE_TRANSACTION_STATUSES = {
    "canceled": "cancel",
    "processing": "pending",
    "requires_action": "pending",
    "requiresauthorization": "pending",
    "requirescapture": "pending",
    "requiresconfirmation": "pending",
    "requirespaymentmethod": "pending",
    "succeeded": "done",
}


class PaymentServiceStripe(Component):

    _name = "payment.service.stripe"
    _inherit = "base.rest.service"
    _usage = "payment_stripe"
    _description = ""

    def _validator_confirm_payment(self):
        """
        Validator of confirm_payment service
        target: see _allowed_payment_target()
        payment_mode: The payment mode used to pay
        stripe_payment_intent_id: The previously created intent
        stripe_payment_method_id: The Stripe card created on client side
        :return: dict
        """
        res = self.component(
            usage="invader.payment"
        )._invader_get_target_validator()
        res.update(
            {
                # payment_mode cannot be integer here, because
                # it can be an empty string from the form
                "payment_mode": {"type": "string"},
                "stripe_payment_intent_id": {"type": "string"},
                "stripe_payment_method_id": {"type": "string"},
            }
        )
        return res

    def _validator_return_confirm_payment(self):
        return {
            "requires_action": {"type": "boolean"},
            "payment_intent_client_secret": {"type": "string"},
            "success": {"type": "boolean"},
            "error": {"type": "string"},
            "data": {"type": "string"},
            # TODO these two must go away
            "set_session": {"type": "string"},
            "store_cache": {"type": "string"},
        }

    def _get_formatted_amount(self, currency, amount):
        """
        The expected amount format by Stripe
        :param amount: float
        :return: int
        """
        res = int(
            amount
            if currency.name in INT_CURRENCIES
            else float_round(amount * 100, 2)
        )
        return res

    def _get_stripe_transaction_from_intent(self, intent):
        """
        Retrieve the transaction from intent string
        :param intent: string
        :return: payment.transaction
        """
        transaction = self.env["payment.transaction"].search(
            [
                ("acquirer_reference", "=", intent),
                ("acquirer_id.provider", "=", "stripe"),
            ],
            limit=1,
        )
        return transaction

    def _get_stripe_private_key(self, transaction):
        """
        Return stripe private key depending on payment.transaction recordset
        :param transaction: payment.transaction
        :return: string
        """

        acquirer = transaction.acquirer_id
        return acquirer.filtered(
            lambda a: a.provider == "stripe"
        ).stripe_secret_key

    def confirm_payment(self, target, **params):
        """
        This is the rest service exposed to locomotive and called on
        payment confirmation.
        The steps here depend on how the card is managed on Stripe side.
        * One step:
            * The stripe_payment_method_id is passed
            * The intent state is 'succeeded'
        * Two steps:
            * The stripe_payment_method_id is passed
            * The intent state is 'requires_action'
            * The stripe_payment_intent_id is passed
            * The intent state is 'succeeded'
        :param target: string (authorized value is checked by service)
        :param payment_mode: string (The Odoo payment mode id)
        :param stripe_payment_method_id:
        :param stripe_payment_intent_id:
        :return:
        """
        payment_mode = params.get("payment_mode")
        stripe_payment_method_id = params.get("stripe_payment_method_id")
        stripe_payment_intent_id = params.get("stripe_payment_intent_id")
        transaction_obj = self.env["payment.transaction"]
        payable_target = self.component(
            usage="invader.payment"
        )._invader_find_payable(target, **params)
        # Stripe part
        transaction = None
        try:
            if stripe_payment_method_id:
                # First step
                payment_mode_id = self.env["account.payment.mode"].browse(
                    int(payment_mode)
                )
                transaction = transaction_obj.create(
                    payable_target._invader_prepare_payment_transaction_data(
                        payment_mode_id
                    )
                )
                payable_target._invader_payment_start(
                    transaction, payment_mode_id
                )
                intent = self._prepare_stripe_intent(
                    transaction, stripe_payment_method_id
                )
                transaction.write({"acquirer_reference": intent.id})
            elif stripe_payment_intent_id:
                # Second step if applicable
                transaction = self._get_stripe_transaction_from_intent(
                    stripe_payment_intent_id
                )
                intent = self._confirm_stripe_intent(
                    transaction, stripe_payment_intent_id
                )
            if intent.status == "succeeded":
                transaction._set_transaction_done()
                # TODO: Manage session_id/store_cache return
                payable_target._invader_payment_success(
                    transaction, payment_mode
                )
            else:
                transaction.write(
                    {"state": STRIPE_TRANSACTION_STATUSES[intent.status]}
                )
            return self._generate_stripe_response(intent)

        except Exception as e:
            _logger.exception("Error confirming stripe payment")
            error_message = "Transaction Error : {}".format(e)
            if transaction:
                # Odoo does not like to change not draft transaction to error
                transaction.write({"state": "draft"})
                transaction._set_transaction_error(error_message)
            return {"error": error_message}

    def _prepare_stripe_intent(self, transaction, stripe_payment_method_id):
        """
        Prepare a StripeIntent with payment.transaction data
        :param tx_data:
        :param stripe_payment_method_id:
        :return: StripeIntent
        """
        metadata = {"reference": transaction.reference}
        currency = transaction.currency_id
        intent = stripe.PaymentIntent.create(
            payment_method=stripe_payment_method_id,
            amount=self._get_formatted_amount(currency, transaction.amount),
            currency=currency.name,
            confirmation_method="manual",
            confirm=True,
            description=transaction.reference,
            metadata=metadata,
            api_key=self._get_stripe_private_key(transaction),
        )
        return intent

    def _confirm_stripe_intent(self, transaction, stripe_payment_intent_id):
        """
        Confirm the Stripe Intent and return it
        :param stripe_payment_intent_id:
        :return: StripeIntent
        """
        return stripe.PaymentIntent.confirm(
            stripe_payment_intent_id,
            api_key=self._get_stripe_private_key(transaction),
        )

    def _generate_stripe_response(self, intent):
        """
        This is the message returned to client
        :param intent: StripeIntent
        :param error_message: string
        :return: dict
        """
        if (
            intent.status == "requires_action"
            and intent.next_action.type == "use_stripe_sdk"
        ):
            # Tell the client to handle the action
            return {
                "requires_action": True,
                "payment_intent_client_secret": intent.client_secret,
            }
        elif intent.status == "succeeded":
            # The payment didn’t need any additional actions and completed!
            # Handle post-payment fulfillment
            return {"success": True}
        else:
            # Invalid status
            return {"error": "Invalid PaymentIntent status"}
