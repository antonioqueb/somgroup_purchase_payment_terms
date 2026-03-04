from odoo import models, fields, api
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
        """Al confirmar el pago, sincronizar hitos de todas las OC vinculadas."""
        res = super().action_post()
        self._sync_purchase_schedules()
        return res

    def action_cancel(self):
        """Al cancelar el pago, revertir hitos vinculados."""
        # Recolectar OC antes de cancelar
        purchase_orders = self._get_related_purchase_orders()
        schedules = self.mapped('purchase_schedule_id')
        res = super().action_cancel()
        # Recomputar hitos directamente vinculados
        for schedule in schedules:
            schedule._recompute_from_payments()
        # Recomputar hitos detectados por OC
        self._recompute_schedules_for_orders(purchase_orders)
        return res

    def _get_related_purchase_orders(self):
        """Obtiene las OC relacionadas via líneas de factura."""
        orders = self.env['purchase.order']
        for payment in self:
            # Buscar facturas conciliadas con este pago
            invoices = payment._get_reconciled_invoices()
            for inv in invoices:
                orders |= inv.invoice_line_ids.mapped('purchase_line_id.order_id')
        return orders

    def _get_reconciled_invoices(self):
        """Retorna las facturas (account.move) conciliadas con este pago."""
        self.ensure_one()
        moves = self.env['account.move']
        # Buscar via reconciled_invoice_ids si existe (Odoo 17+)
        if hasattr(self, 'reconciled_invoice_ids'):
            return self.reconciled_invoice_ids
        # Fallback: buscar via líneas de diario conciliadas
        reconciled_lines = self.line_ids.filtered(
            lambda l: l.account_id.account_type in (
                'asset_receivable', 'liability_payable'
            )
        )
        for line in reconciled_lines:
            for matched in (line.matched_debit_ids | line.matched_credit_ids):
                counterpart = matched.debit_move_id if line == matched.credit_move_id else matched.credit_move_id
                if counterpart.move_id.move_type in ('in_invoice', 'in_refund', 'out_invoice', 'out_refund'):
                    moves |= counterpart.move_id
        return moves

    def _sync_purchase_schedules(self):
        """
        Sincronización automática: detecta OC vinculadas via facturas y
        recalcula el estado de todos sus hitos de pago.
        No requiere que el usuario haya usado el botón 'Pagar' del hito.
        """
        purchase_orders = self._get_related_purchase_orders()

        # También procesar hitos directamente vinculados (vía botón Pagar)
        direct_schedules = self.mapped('purchase_schedule_id')
        for schedule in direct_schedules:
            schedule._recompute_from_payments()
            purchase_orders |= schedule.order_id

        # Recomputar todos los hitos de las OC detectadas
        self._recompute_schedules_for_orders(purchase_orders)

    def _recompute_schedules_for_orders(self, purchase_orders):
        """Recomputa hitos de pago para un conjunto de OC."""
        if not purchase_orders:
            return
        schedules = purchase_orders.mapped('payment_schedule_ids').filtered(
            lambda s: s.state != 'paid'
        )
        if schedules:
            schedules._recompute_from_payments_by_order()