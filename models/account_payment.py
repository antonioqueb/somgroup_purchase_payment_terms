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
        # Post-post: la reconciliación ya ocurrió dentro de super()
        # (account.payment.register reconcilia en _reconcile_payments dentro de action_create_payments)
        # Pero si se llama directo desde account.payment, la reconciliación puede no haber ocurrido aún.
        # Usamos invalidate_recordset para forzar releer desde DB antes de buscar conciliaciones.
        self.invalidate_recordset()
        self._sync_purchase_schedules()
        return res

    def action_cancel(self):
        purchase_orders = self._get_related_purchase_orders()
        schedules = self.mapped('purchase_schedule_id')
        res = super().action_cancel()
        for schedule in schedules:
            schedule._recompute_from_payments_by_order()
        self._recompute_schedules_for_orders(purchase_orders)
        return res

    def _get_related_purchase_orders(self):
        orders = self.env['purchase.order']
        for payment in self:
            invoices = payment._get_reconciled_invoices()
            for inv in invoices:
                orders |= inv.invoice_line_ids.mapped('purchase_line_id.order_id')
        return orders

    def _get_reconciled_invoices(self):
        self.ensure_one()
        # reconciled_bill_ids es el campo correcto en Odoo 17+ para pagos a proveedores
        if hasattr(self, 'reconciled_bill_ids') and self.reconciled_bill_ids:
            return self.reconciled_bill_ids
        if hasattr(self, 'reconciled_invoice_ids') and self.reconciled_invoice_ids:
            return self.reconciled_invoice_ids
        # Fallback manual via matched_debit/credit
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
        """
        Punto de sincronización principal.
        Combina dos rutas:
        1. Pagos con purchase_schedule_id directo → recompute por OC
        2. Pagos sin vínculo directo → detectar OC via facturas reconciliadas
        """
        # Recolectar todas las OC afectadas
        purchase_orders = self.env['purchase.order']

        # Ruta 1: purchase_schedule_id directo
        for payment in self:
            if payment.purchase_schedule_id:
                purchase_orders |= payment.purchase_schedule_id.order_id

        # Ruta 2: facturas reconciliadas
        purchase_orders |= self._get_related_purchase_orders()

        _logger.info('[SOMGROUP] _sync_purchase_schedules - orders to sync: %s', purchase_orders.ids)

        if purchase_orders:
            schedules = purchase_orders.mapped('payment_schedule_ids')
            if schedules:
                schedules._recompute_from_payments_by_order()

    def _recompute_schedules_for_orders(self, purchase_orders):
        if not purchase_orders:
            return
        schedules = purchase_orders.mapped('payment_schedule_ids')
        if schedules:
            schedules._recompute_from_payments_by_order()