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
        for payment in self.filtered(lambda p: p.state == 'posted'):
            for inv in payment._get_reconciled_invoices():
                orders |= inv.invoice_line_ids.mapped('purchase_line_id.order_id')
        return orders

    def _get_reconciled_invoices(self):
        self.ensure_one()
        # Intentar primero los campos de alto nivel (más confiables)
        if hasattr(self, 'reconciled_bill_ids') and self.reconciled_bill_ids:
            return self.reconciled_bill_ids
        if hasattr(self, 'reconciled_invoice_ids') and self.reconciled_invoice_ids:
            return self.reconciled_invoice_ids
        # Fallback manual — solo si ya tiene line_ids (pago posteado)
        moves = self.env['account.move']
        if not self.line_ids:
            return moves
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
        orders = self.env['purchase.order']

        for payment in self:
            if payment.purchase_schedule_id:
                orders |= payment.purchase_schedule_id.order_id

        # Solo buscar facturas reconciliadas en pagos ya posteados
        orders |= self._get_related_purchase_orders()

        if orders:
            schedules = orders.mapped('payment_schedule_ids')
            if schedules:
                schedules._recompute_from_payments_by_order(extra_payments=self)