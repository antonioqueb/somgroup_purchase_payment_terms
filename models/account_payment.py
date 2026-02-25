from odoo import models, fields, api


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    purchase_schedule_id = fields.Many2one(
        'purchase.payment.schedule',
        string='Hito de Pago OC',
        ondelete='set null',
        help='Enlace automático con el calendario de pagos de importación'
    )

    def action_post(self):
        """Al confirmar/publicar el pago, actualizar el hito del calendario."""
        res = super().action_post()
        for payment in self:
            if payment.purchase_schedule_id:
                payment.purchase_schedule_id._recompute_from_payments()
        return res

    def action_cancel(self):
        """Al cancelar el pago, revertir el hito del calendario."""
        schedules = self.mapped('purchase_schedule_id')
        res = super().action_cancel()
        for schedule in schedules:
            schedule._recompute_from_payments()
        return res