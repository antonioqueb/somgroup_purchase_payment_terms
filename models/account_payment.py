from odoo import models, fields
import logging

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    purchase_schedule_id = fields.Many2one(
        'purchase.payment.schedule',
        string='Hito de Pago OC',
        ondelete='set null',
    )

    def action_post(self):
        res = super().action_post()
        self._sync_purchase_schedules()
        return res

    def action_cancel(self):
        purchase_orders = self._get_related_purchase_orders()
        schedules = self.mapped('purchase_schedule_id')
        res = super().action_cancel()
        orders = purchase_orders
        for s in schedules:
            orders |= s.order_id
        if orders:
            orders.mapped('payment_schedule_ids')._recompute_from_payments_by_order()
        return res

    def _get_related_purchase_orders(self):
        orders = self.env['purchase.order']
        for payment in self:
            for inv in payment._get_reconciled_invoices():
                orders |= inv.invoice_line_ids.mapped('purchase_line_id.order_id')
        return orders

    def _get_reconciled_invoices(self):
        self.ensure_one()
        if hasattr(self, 'reconciled_bill_ids') and self.reconciled_bill_ids:
            return self.reconciled_bill_ids
        if hasattr(self, 'reconciled_invoice_ids') and self.reconciled_invoice_ids:
            return self.reconciled_invoice_ids
        moves = self.env['account.move']
        for line in self.line_ids.filtered(
            lambda l: l.account_id.account_type == 'liability_payable'
        ):
            for matched in (line.matched_debit_ids | line.matched_credit_ids):
                counterpart = (
                    matched.debit_move_id
                    if line == matched.credit_move_id
                    else matched.credit_move_id
                )
                if counterpart.move_id.move_type in ('in_invoice', 'in_refund'):
                    moves |= counterpart.move_id
        return moves

    def _sync_purchase_schedules(self):
        """Recopila todas las OC afectadas y dispara resync pasando self como extra."""
        orders = self.env['purchase.order']

        for payment in self:
            if payment.purchase_schedule_id:
                orders |= payment.purchase_schedule_id.order_id

        orders |= self._get_related_purchase_orders()

        if orders:
            schedules = orders.mapped('payment_schedule_ids')
            if schedules:
                # Pasar self como extra_payments para que se incluya aunque no esté en DB search aún
                schedules._recompute_from_payments_by_order(extra_payments=self)