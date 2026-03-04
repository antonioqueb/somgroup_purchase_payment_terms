from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_post(self):
        """Al confirmar factura, sincronizar hitos de la OC si aplica."""
        res = super().action_post()
        self._sync_import_payment_schedules()
        return res

    def button_draft(self):
        """Al resetear a borrador, recomputar hitos."""
        res = super().button_draft()
        self._sync_import_payment_schedules()
        return res

    def button_cancel(self):
        res = super().button_cancel()
        self._sync_import_payment_schedules()
        return res

    def _sync_import_payment_schedules(self):
        """Detecta OC de importación vinculadas y recomputa sus hitos."""
        orders = self.env['purchase.order']
        for move in self.filtered(lambda m: m.move_type == 'in_invoice'):
            orders |= move.invoice_line_ids.mapped('purchase_line_id.order_id').filtered(
                lambda o: o.is_import_order
                and o.payment_schedule_ids
                and o.payment_term_id.somgroup_term_type != 'standard'
            )
        if orders:
            schedules = orders.mapped('payment_schedule_ids')
            if schedules:
                schedules._recompute_from_payments_by_order()