# -*- coding: utf-8 -*-
"""remaining_amount pasa a ser calculado (monto − pagado): recomputar los
hitos existentes (antes nacía en 0 y los pendientes mostraban Saldo $0.00) y
marcar vencidos los que ya lo están (antes dependía de una acción manual)."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Schedule = env['purchase.payment.schedule']
    records = Schedule.with_context(active_test=False).search([])
    env.add_to_compute(Schedule._fields['remaining_amount'], records)
    records._recompute_recordset(['remaining_amount'])
    Schedule.action_mark_overdue()
