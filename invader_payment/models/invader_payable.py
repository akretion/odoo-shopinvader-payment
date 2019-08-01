# Copyright 2019 ACSONE SA/NV
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import models


class InvaderPayable(models.AbstractModel):

    _name = "invader.payable"
    _description = "Provides base methods for payable models"

    def _invader_prepare_payment_transaction_data(self, payment_mode):
        """

        :return:
        """

    def _invader_get_available_payment_methods(self):
        """
        Should be implemented on payable models level
        :return: recordset (account.payment.method)
        """
        raise NotImplementedError

    def _invader_after_payment(self, transaction):
        """

        :param transaction:
        :return:
        """
        raise NotImplementedError

    def _invader_attach_transaction(self, transaction, payment_mode):
        raise NotImplementedError

    def _invader_payment_start(self, transaction):
        """ Called just after the transaction has been created. """
        pass

    def _invader_payment_success(self, transaction):
        """ Called when the payment transaction succeeded. """
        pass
