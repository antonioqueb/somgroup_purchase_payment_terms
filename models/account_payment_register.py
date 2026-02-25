from odoo import models, fields


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    purchase_schedule_id = fields.Many2one(
        'purchase.payment.schedule',
        string='Hito de Pago OC',
        help='Hito del calendario de importación al que pertenece este pago'
    )

    def _create_payment_vals_from_wizard(self, batch_result):
        """Propagar purchase_schedule_id al pago creado."""
        vals = super()._create_payment_vals_from_wizard(batch_result)
        if self.purchase_schedule_id:
            vals['purchase_schedule_id'] = self.purchase_schedule_id.id
        return vals