from odoo import models, fields, api
from odoo.exceptions import ValidationError


class AccountPaymentTerm(models.Model):
    _inherit = 'account.payment.term'

    # Tipo de término para lógica de negocio SOMGROUP
    somgroup_term_type = fields.Selection([
        ('advance_balance', 'Anticipo + Balance (% fijo)'),
        ('days_after_bl', 'N días después de BL'),
        ('days_after_invoice', 'N días después de Fecha Factura'),
        ('against_delivery', 'Contra Entrega / CAD / Contra BL'),
        ('full_advance', '100% Pago Anticipado'),
        ('advance_days_invoice', 'Anticipo + Saldo a N días Factura'),
        ('advance_days_arrival', 'Anticipo + Saldo N días después Arribo'),
        ('standard', 'Estándar Odoo'),
    ], string='Tipo Término SOMGROUP', default='standard',
       help="Define cómo se calcula la fecha de vencimiento del balance")

    advance_percent = fields.Float(
        string='% Anticipo',
        digits=(5, 2),
        help="Porcentaje del anticipo (ej: 30 para 30%)"
    )
    second_advance_percent = fields.Float(
        string='% Segundo Tramo',
        digits=(5, 2),
        help="Para términos de 3 tramos (ej: 25%)"
    )
    balance_days = fields.Integer(
        string='Días para Balance',
        help="Días para calcular vencimiento del balance (desde BL, factura o arribo según tipo)"
    )
    requires_bl_date = fields.Boolean(
        string='Requiere Fecha BL',
        compute='_compute_requires_bl_date',
        store=True,
        help="Indica si este término necesita la fecha BL para calcular vencimientos"
    )
    requires_eta = fields.Boolean(
        string='Requiere ETA',
        compute='_compute_requires_eta',
        store=True,
        help="Indica si este término requiere seguimiento manual de ETA"
    )
    is_manual_scheduling = fields.Boolean(
        string='Programación Manual',
        compute='_compute_is_manual',
        store=True,
        help="El pago debe programarse manualmente por el área de Compras"
    )
    days_before_eta = fields.Integer(
        string='Días Antes de ETA para Pagar',
        default=7,
        help="Para términos contra entrega: cuántos días antes del arribo se programa el pago (default 7)"
    )
    payment_term_note = fields.Text(
        string='Nota Operativa',
        help="Instrucciones específicas para el área de Compras"
    )

    @api.depends('somgroup_term_type')
    def _compute_requires_bl_date(self):
        bl_types = ['days_after_bl']
        for rec in self:
            rec.requires_bl_date = rec.somgroup_term_type in bl_types

    @api.depends('somgroup_term_type')
    def _compute_requires_eta(self):
        eta_types = ['against_delivery', 'advance_balance', 'advance_days_arrival']
        for rec in self:
            rec.requires_eta = rec.somgroup_term_type in eta_types

    @api.depends('somgroup_term_type')
    def _compute_is_manual(self):
        manual_types = ['against_delivery', 'full_advance', 'advance_days_arrival']
        for rec in self:
            rec.is_manual_scheduling = rec.somgroup_term_type in manual_types

    def compute_due_dates(self, purchase_order):
        """
        Calcula las fechas de pago según el tipo de término y los datos de la OC.
        Retorna lista de dicts: [{
            'type': 'advance'|'balance'|'second_advance',
            'percent': float,
            'amount': float,
            'due_date': date,
            'note': str,
            'is_manual': bool,
        }]
        """
        self.ensure_one()
        result = []
        amount = purchase_order.amount_total
        bl_date = purchase_order.bl_date
        eta_date = purchase_order.eta_date
        order_date = purchase_order.date_order.date() if purchase_order.date_order else False
        invoice_date = purchase_order.effective_date or order_date

        term_type = self.somgroup_term_type

        if term_type == 'full_advance':
            result.append({
                'type': 'advance',
                'percent': 100.0,
                'amount': amount,
                'due_date': order_date,
                'note': 'Pago total anticipado antes de producción. Sin pago no hay carga.',
                'is_manual': True,
            })

        elif term_type == 'days_after_bl':
            due_date = False
            if bl_date and self.balance_days:
                from datetime import timedelta
                due_date = bl_date + timedelta(days=self.balance_days)
            result.append({
                'type': 'balance',
                'percent': 100.0,
                'amount': amount,
                'due_date': due_date,
                'note': f'{self.balance_days} días después de fecha BL.' + (
                    '' if due_date else ' Ingrese fecha BL para calcular vencimiento.'),
                'is_manual': not bool(due_date),
            })

        elif term_type == 'days_after_invoice':
            due_date = False
            if invoice_date and self.balance_days:
                from datetime import timedelta
                due_date = invoice_date + timedelta(days=self.balance_days)
            result.append({
                'type': 'balance',
                'percent': 100.0,
                'amount': amount,
                'due_date': due_date,
                'note': f'{self.balance_days} días después de fecha de factura.',
                'is_manual': not bool(due_date),
            })

        elif term_type == 'against_delivery':
            advance_pct = self.advance_percent or 0.0
            balance_pct = 100.0 - advance_pct

            if advance_pct > 0:
                result.append({
                    'type': 'advance',
                    'percent': advance_pct,
                    'amount': round(amount * advance_pct / 100, 2),
                    'due_date': order_date,
                    'note': f'Anticipo {advance_pct:.0f}% al confirmar proforma.',
                    'is_manual': True,
                })

            due_date = False
            note = f'Balance {balance_pct:.0f}% — Contra Entrega/CAD. '
            if eta_date:
                from datetime import timedelta
                days_before = self.days_before_eta or 7
                due_date = eta_date - timedelta(days=days_before)
                note += f'Pagar {days_before} días antes de ETA ({eta_date}). Necesario para Telex Release.'
            else:
                note += 'Programar 5-10 días antes de ETA. Requiere seguimiento manual.'

            result.append({
                'type': 'balance',
                'percent': balance_pct,
                'amount': round(amount * balance_pct / 100, 2),
                'due_date': due_date,
                'note': note,
                'is_manual': True,
            })

        elif term_type == 'advance_balance':
            advance_pct = self.advance_percent or 30.0
            balance_pct = 100.0 - advance_pct

            result.append({
                'type': 'advance',
                'percent': advance_pct,
                'amount': round(amount * advance_pct / 100, 2),
                'due_date': order_date,
                'note': f'Anticipo {advance_pct:.0f}% al confirmar proforma.',
                'is_manual': True,
            })

            due_date = False
            note = f'Balance {balance_pct:.0f}%. '
            if bl_date and self.balance_days:
                from datetime import timedelta
                due_date = bl_date + timedelta(days=self.balance_days)
                note += f'Vence {self.balance_days} días después de BL.'
            elif eta_date:
                from datetime import timedelta
                days_before = self.days_before_eta or 7
                due_date = eta_date - timedelta(days=days_before)
                note += f'Pagar antes de ETA. Requiere Telex Release.'

            result.append({
                'type': 'balance',
                'percent': balance_pct,
                'amount': round(amount * balance_pct / 100, 2),
                'due_date': due_date,
                'note': note,
                'is_manual': not bool(due_date),
            })

        elif term_type == 'advance_days_invoice':
            advance_pct = self.advance_percent or 50.0
            balance_pct = 100.0 - advance_pct

            result.append({
                'type': 'advance',
                'percent': advance_pct,
                'amount': round(amount * advance_pct / 100, 2),
                'due_date': order_date,
                'note': f'Anticipo {advance_pct:.0f}% al confirmar proforma.',
                'is_manual': True,
            })

            due_date = False
            if invoice_date and self.balance_days:
                from datetime import timedelta
                due_date = invoice_date + timedelta(days=self.balance_days)

            result.append({
                'type': 'balance',
                'percent': balance_pct,
                'amount': round(amount * balance_pct / 100, 2),
                'due_date': due_date,
                'note': f'Balance {balance_pct:.0f}% a {self.balance_days} días de fecha factura.',
                'is_manual': not bool(due_date),
            })

        elif term_type == 'advance_days_arrival':
            advance_pct = self.advance_percent or 30.0
            second_pct = self.second_advance_percent or 0.0
            balance_pct = 100.0 - advance_pct - second_pct

            result.append({
                'type': 'advance',
                'percent': advance_pct,
                'amount': round(amount * advance_pct / 100, 2),
                'due_date': order_date,
                'note': f'Anticipo {advance_pct:.0f}%.',
                'is_manual': True,
            })

            if second_pct > 0:
                due_date = False
                note = f'Contra entrega {second_pct:.0f}%. '
                if eta_date:
                    from datetime import timedelta
                    due_date = eta_date - timedelta(days=self.days_before_eta or 7)
                    note += f'Pagar antes de ETA ({eta_date}).'
                result.append({
                    'type': 'second_advance',
                    'percent': second_pct,
                    'amount': round(amount * second_pct / 100, 2),
                    'due_date': due_date,
                    'note': note,
                    'is_manual': True,
                })

            due_date = False
            note = f'Balance {balance_pct:.0f}% a {self.balance_days} días de arribo.'
            if eta_date and self.balance_days:
                from datetime import timedelta
                due_date = eta_date + timedelta(days=self.balance_days)

            result.append({
                'type': 'balance',
                'percent': balance_pct,
                'amount': round(amount * balance_pct / 100, 2),
                'due_date': due_date,
                'note': note,
                'is_manual': not bool(due_date),
            })

        else:
            # Standard — usa el motor nativo de Odoo
            result.append({
                'type': 'balance',
                'percent': 100.0,
                'amount': amount,
                'due_date': False,
                'note': 'Término estándar Odoo.',
                'is_manual': False,
            })

        return result
