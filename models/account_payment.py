from odoo import models, fields
import logging

_logger = logging.getLogger(__name__)

POSTED_STATES = ('posted', 'in_process', 'paid')


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
        orders = self.env['purchase.order']
        for p in self:
            if p.purchase_schedule_id:
                orders |= p.purchase_schedule_id.order_id
        orders |= self._get_related_purchase_orders()
        res = super().action_cancel()
        if orders:
            orders.mapped('payment_schedule_ids')._recompute_from_payments_by_order()
        return res

    def _get_related_purchase_orders(self):
        orders = self.env['purchase.order']
        for payment in self.filtered(lambda p: p.state in POSTED_STATES):
            for inv in payment._get_reconciled_invoices():
                orders |= inv.invoice_line_ids.mapped('purchase_line_id.order_id')
        return orders

    def _get_payment_move(self):
        """Obtener el asiento contable del pago de forma robusta."""
        self.ensure_one()
        if self.move_id:
            return self.move_id
        if hasattr(self, 'move_ids') and self.move_ids:
            return self.move_ids[0]
        if self.name:
            move = self.env['account.move'].search([
                ('name', '=', self.name),
            ], limit=1)
            if move:
                return move
        return self.env['account.move']

    def _get_reconciled_invoices(self):
        """
        Odoo 19: account.payment puede no tener move_id accesible en estado paid.
        Usa _get_payment_move como fallback robusto.
        """
        self.ensure_one()
        if hasattr(self, 'reconciled_bill_ids') and self.reconciled_bill_ids:
            return self.reconciled_bill_ids
        if hasattr(self, 'reconciled_invoice_ids') and self.reconciled_invoice_ids:
            return self.reconciled_invoice_ids
        moves = self.env['account.move']
        pay_move = self._get_payment_move()
        if not pay_move:
            return moves
        for line in pay_move.line_ids.filtered(
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
        orders = self.env['purchase.order']

        for payment in self:
            if payment.purchase_schedule_id:
                orders |= payment.purchase_schedule_id.order_id

        orders |= self._get_related_purchase_orders()

        if orders:
            schedules = orders.mapped('payment_schedule_ids')
            if schedules:
                schedules._recompute_from_payments_by_order(extra_payments=self)