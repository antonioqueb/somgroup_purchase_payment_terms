from odoo import models, fields
import logging

_logger = logging.getLogger(__name__)


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    purchase_schedule_id = fields.Many2one(
        'purchase.payment.schedule',
        string='Hito de Pago OC',
        help='Hito del calendario de importación al que pertenece este pago'
    )

    def _create_payment_vals_from_wizard(self, batch_result):
        vals = super()._create_payment_vals_from_wizard(batch_result)
        if self.purchase_schedule_id:
            vals['purchase_schedule_id'] = self.purchase_schedule_id.id
        return vals

    def action_create_payments(self):
        """
        Override para sincronizar hitos DESPUÉS de que los pagos se crean y reconcilian.
        En este punto la reconciliación ya ocurrió dentro de super().
        """
        res = super().action_create_payments()

        # Detectar OC afectadas via las facturas que se estaban pagando
        try:
            orders = self.env['purchase.order']
            active_ids = self.env.context.get('active_ids', [])
            if active_ids and self.env.context.get('active_model') == 'account.move':
                invoices = self.env['account.move'].browse(active_ids)
                for inv in invoices:
                    orders |= inv.invoice_line_ids.mapped('purchase_line_id.order_id').filtered(
                        lambda o: o.is_import_order and o.payment_schedule_ids
                    )

            # También via purchase_schedule_id directo
            if self.purchase_schedule_id:
                orders |= self.purchase_schedule_id.order_id

            if orders:
                _logger.info('[SOMGROUP] action_create_payments post-sync for orders: %s', orders.ids)
                schedules = orders.mapped('payment_schedule_ids')
                if schedules:
                    schedules._recompute_from_payments_by_order()
        except Exception as e:
            _logger.warning('[SOMGROUP] Error en sync post-pago: %s', e)

        return res