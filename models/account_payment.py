from odoo import models, fields
import logging

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    purchase_schedule_id = fields.Many2one(
        'purchase.payment.schedule',
        string='Hito de Pago OC',
        ondelete='set null',
        help='Enlace automático con el calendario de pagos de importación'
    )

    def action_post(self):
        res = super().action_post()
        _logger.info('[SOMGROUP] account.payment action_post triggered for payments: %s', self.ids)
        self._sync_purchase_schedules()
        return res

    def action_cancel(self):
        purchase_orders = self._get_related_purchase_orders()
        schedules = self.mapped('purchase_schedule_id')
        res = super().action_cancel()
        for schedule in schedules:
            schedule._recompute_from_payments()
        self._recompute_schedules_for_orders(purchase_orders)
        return res

    def _get_related_purchase_orders(self):
        orders = self.env['purchase.order']
        for payment in self:
            invoices = payment._get_reconciled_invoices()
            _logger.info('[SOMGROUP] payment %s reconciled invoices: %s', payment.id, invoices.ids)
            for inv in invoices:
                orders |= inv.invoice_line_ids.mapped('purchase_line_id.order_id')
        return orders

    def _get_reconciled_invoices(self):
        self.ensure_one()
        moves = self.env['account.move']
        if hasattr(self, 'reconciled_bill_ids'):
            _logger.info('[SOMGROUP] payment %s using reconciled_bill_ids: %s', self.id, self.reconciled_bill_ids.ids)
            return self.reconciled_bill_ids
        if hasattr(self, 'reconciled_invoice_ids'):
            _logger.info('[SOMGROUP] payment %s using reconciled_invoice_ids: %s', self.id, self.reconciled_invoice_ids.ids)
            return self.reconciled_invoice_ids
        # Fallback via conciliaciones contables
        reconciled_lines = self.line_ids.filtered(
            lambda l: l.account_id.account_type == 'liability_payable'
        )
        _logger.info('[SOMGROUP] payment %s payable lines: %s', self.id, reconciled_lines.ids)
        for line in reconciled_lines:
            for matched in (line.matched_debit_ids | line.matched_credit_ids):
                counterpart = (
                    matched.debit_move_id
                    if line == matched.credit_move_id
                    else matched.credit_move_id
                )
                if counterpart.move_id.move_type in ('in_invoice', 'in_refund', 'out_invoice', 'out_refund'):
                    moves |= counterpart.move_id
        _logger.info('[SOMGROUP] payment %s fallback invoices: %s', self.id, moves.ids)
        return moves

    def _sync_purchase_schedules(self):
        purchase_orders = self._get_related_purchase_orders()
        _logger.info('[SOMGROUP] _sync_purchase_schedules - related orders: %s', purchase_orders.ids)

        direct_schedules = self.mapped('purchase_schedule_id')
        _logger.info('[SOMGROUP] direct schedules via purchase_schedule_id: %s', direct_schedules.ids)
        for schedule in direct_schedules:
            schedule._recompute_from_payments()
            purchase_orders |= schedule.order_id

        self._recompute_schedules_for_orders(purchase_orders)

    def _recompute_schedules_for_orders(self, purchase_orders):
        if not purchase_orders:
            _logger.info('[SOMGROUP] _recompute_schedules_for_orders - no orders, skipping')
            return
        schedules = purchase_orders.mapped('payment_schedule_ids').filtered(
            lambda s: s.state != 'paid'
        )
        _logger.info('[SOMGROUP] schedules to recompute (not paid): %s', schedules.ids)
        if schedules:
            schedules._recompute_from_payments_by_order()