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
        schedules_direct = self.env['purchase.payment.schedule']

        for move in self.filtered(lambda m: m.move_type == 'in_invoice'):

            # ── Ruta 1: factura vinculada a líneas de OC (facturas reales) ──
            found = move.invoice_line_ids.mapped('purchase_line_id.order_id')
            _logger.info('[SOMGROUP] move %s linked to orders via lines: %s', move.id, found.ids)
            orders |= found.filtered(
                lambda o: o.is_import_order
                and o.payment_schedule_ids
                and o.payment_term_id.somgroup_term_type != 'standard'
            )

            # ── Ruta 2: factura es schedule_invoice_id de algún hito ──────────
            linked_schedules = self.env['purchase.payment.schedule'].search([
                ('schedule_invoice_id', '=', move.id)
            ])
            if linked_schedules:
                _logger.info(
                    '[SOMGROUP] move %s es schedule_invoice de hitos: %s',
                    move.id, linked_schedules.ids
                )
                schedules_direct |= linked_schedules
                orders |= linked_schedules.mapped('order_id').filtered(
                    lambda o: o.is_import_order and o.payment_schedule_ids
                )

            # ── Ruta 3: factura vinculada a la OC via purchase_id ────────────
            if move.purchase_id:
                order = move.purchase_id
                if (order.is_import_order
                        and order.payment_schedule_ids
                        and order.payment_term_id.somgroup_term_type != 'standard'):
                    orders |= order

        _logger.info('[SOMGROUP] Orders to sync: %s', orders.ids)

        all_schedules = orders.mapped('payment_schedule_ids') | schedules_direct
        _logger.info('[SOMGROUP] Schedules to recompute: %s', all_schedules.ids)

        if all_schedules:
            all_schedules._recompute_from_payments_by_order()