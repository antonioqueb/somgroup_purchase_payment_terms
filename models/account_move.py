from odoo import models
import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_post(self):
        res = super().action_post()
        _logger.info('[SOMGROUP] account.move action_post triggered for moves: %s', self.ids)
        self._sync_import_payment_schedules()
        return res

    def button_draft(self):
        res = super().button_draft()
        self._sync_import_payment_schedules()
        return res

    def button_cancel(self):
        res = super().button_cancel()
        self._sync_import_payment_schedules()
        return res

    def _sync_import_payment_schedules(self):
        orders = self.env['purchase.order']
        for move in self.filtered(lambda m: m.move_type == 'in_invoice'):
            found = move.invoice_line_ids.mapped('purchase_line_id.order_id')
            _logger.info('[SOMGROUP] move %s linked to orders: %s', move.id, found.ids)
            orders |= found.filtered(
                lambda o: o.is_import_order
                and o.payment_schedule_ids
                and o.payment_term_id.somgroup_term_type != 'standard'
            )
        _logger.info('[SOMGROUP] Orders to sync: %s', orders.ids)
        if orders:
            schedules = orders.mapped('payment_schedule_ids')
            _logger.info('[SOMGROUP] Schedules to recompute: %s', schedules.ids)
            if schedules:
                schedules._recompute_from_payments_by_order()