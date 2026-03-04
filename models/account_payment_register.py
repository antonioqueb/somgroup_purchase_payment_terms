from odoo import models, fields
import logging

_logger = logging.getLogger(__name__)


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    purchase_schedule_id = fields.Many2one(
        'purchase.payment.schedule',
        string='Hito de Pago OC',
    )

    def _create_payment_vals_from_wizard(self, batch_result):
        vals = super()._create_payment_vals_from_wizard(batch_result)
        if self.purchase_schedule_id:
            vals['purchase_schedule_id'] = self.purchase_schedule_id.id
        return vals

    def action_create_payments(self):
        res = super().action_create_payments()
        # En este punto los pagos ya están creados, posteados Y reconciliados
        try:
            orders = self.env['purchase.order']
            active_ids = self.env.context.get('active_ids', [])
            if active_ids and self.env.context.get('active_model') == 'account.move':
                invoices = self.env['account.move'].browse(active_ids)
                for inv in invoices:
                    orders |= inv.invoice_line_ids.mapped('purchase_line_id.order_id').filtered(
                        lambda o: o.is_import_order and o.payment_schedule_ids
                    )
            if self.purchase_schedule_id:
                orders |= self.purchase_schedule_id.order_id
            if orders:
                orders.mapped('payment_schedule_ids')._recompute_from_payments_by_order()
        except Exception as e:
            _logger.warning('[SOMGROUP] Error en sync post-pago: %s', e)
        return res