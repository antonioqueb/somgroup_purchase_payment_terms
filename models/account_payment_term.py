from datetime import timedelta

from odoo import models, fields, api
from odoo.exceptions import UserError


class AccountPaymentTerm(models.Model):
    _inherit = 'account.payment.term'

    somgroup_scope = fields.Selection([
        ('both', 'Ambos'),
        ('import', 'Importación'),
        ('national', 'Nacional'),
    ], string='Aplica a', default='both',
       help='Permite separar términos para compras de importación, nacionales o ambos flujos.')

    som_usage = fields.Selection([
        ('both', 'Compras y Ventas'),
        ('purchase', 'Solo Compras'),
        ('sale', 'Solo Ventas'),
    ], string='Visible en', default='both', required=True,
       help='Dónde se ofrece este término de pago: solo en órdenes de compra, '
            'solo en órdenes de venta, o en ambas. Los documentos existentes '
            'no se alteran; el filtro aplica al elegir el término.')

    somgroup_term_type = fields.Selection([
        ('advance_balance', 'Importación: Anticipo + Balance (% fijo)'),
        ('days_after_bl', 'Importación: N días después de BL'),
        ('days_after_invoice', 'Importación: N días después de Fecha Factura'),
        ('against_delivery', 'Importación: Contra Entrega / CAD / Contra BL'),
        ('full_advance', '100% Pago Anticipado'),
        ('advance_days_invoice', 'Importación: Anticipo + Saldo a N días Factura'),
        ('advance_days_arrival', 'Importación: Anticipo + Saldo N días después Arribo'),

        ('national_days_after_base', 'Nacional: N días después de base seleccionada'),
        ('national_against_receipt', 'Nacional: Contra recepción / entrega'),
        ('national_advance_balance', 'Nacional: Anticipo + saldo'),

        ('standard', 'Estándar Odoo'),
    ], string='Tipo Término SOMGROUP', default='standard',
       help='Define cómo se calculan los vencimientos SOMGROUP.')

    advance_percent = fields.Float(
        string='% Anticipo',
        digits=(5, 2),
        help='Porcentaje del anticipo.'
    )

    second_advance_percent = fields.Float(
        string='% Segundo Tramo',
        digits=(5, 2),
        help='Para términos de 3 tramos.'
    )

    balance_days = fields.Integer(
        string='Días para Balance',
        help='Días para calcular vencimiento del balance según la base del término.'
    )

    days_before_eta = fields.Integer(
        string='Días Antes de ETA / Recepción',
        default=7,
        help='Para contra entrega: días antes de ETA o recepción para programar pago.'
    )

    national_due_base = fields.Selection([
        ('order_date', 'Fecha de OC'),
        ('confirmation_date', 'Fecha de Confirmación OC'),
        ('supplier_invoice_date', 'Fecha Factura Proveedor'),
        ('expected_receipt_date', 'Fecha Recepción Esperada'),
        ('receipt_date', 'Fecha Recepción Real / Entrega'),
        ('manual_date', 'Fecha Manual de Referencia'),
    ], string='Base Vencimiento Nacional',
       default='supplier_invoice_date',
       help='Base usada para calcular vencimientos de compras nacionales.')

    requires_bl_date = fields.Boolean(
        string='Requiere Fecha BL',
        compute='_compute_requires_bl_date',
        store=False,
        help='Indica si este término necesita Fecha BL.'
    )

    requires_eta = fields.Boolean(
        string='Requiere ETA',
        compute='_compute_requires_eta',
        store=False,
        help='Indica si este término requiere ETA.'
    )

    requires_supplier_invoice_date = fields.Boolean(
        string='Requiere Fecha Factura Proveedor',
        compute='_compute_national_required_dates',
        store=False,
    )

    requires_national_receipt_date = fields.Boolean(
        string='Requiere Fecha Recepción Nacional',
        compute='_compute_national_required_dates',
        store=False,
    )

    requires_national_reference_date = fields.Boolean(
        string='Requiere Fecha Referencia Nacional',
        compute='_compute_national_required_dates',
        store=False,
    )

    is_manual_scheduling = fields.Boolean(
        string='Programación Manual',
        compute='_compute_is_manual',
        store=False,
        help='Indica si el término requiere seguimiento manual.'
    )

    payment_term_note = fields.Text(
        string='Nota Operativa',
        help='Instrucciones específicas para Compras / Tesorería.'
    )

    @api.depends('somgroup_term_type')
    def _compute_requires_bl_date(self):
        for rec in self:
            rec.requires_bl_date = rec.somgroup_term_type in ['days_after_bl']

    @api.depends('somgroup_term_type')
    def _compute_requires_eta(self):
        eta_types = ['against_delivery', 'advance_balance', 'advance_days_arrival']
        for rec in self:
            rec.requires_eta = rec.somgroup_term_type in eta_types

    @api.depends('somgroup_term_type', 'national_due_base')
    def _compute_national_required_dates(self):
        for rec in self:
            base = rec.national_due_base or 'supplier_invoice_date'
            is_national_base = rec.somgroup_term_type in [
                'national_days_after_base',
                'national_advance_balance',
            ]

            rec.requires_supplier_invoice_date = (
                is_national_base and base == 'supplier_invoice_date'
            )

            rec.requires_national_reference_date = (
                is_national_base and base == 'manual_date'
            )

            rec.requires_national_receipt_date = (
                rec.somgroup_term_type == 'national_against_receipt'
                or (
                    is_national_base
                    and base in ['expected_receipt_date', 'receipt_date']
                )
            )

    @api.depends('somgroup_term_type')
    def _compute_is_manual(self):
        manual_types = [
            'against_delivery',
            'full_advance',
            'advance_days_arrival',
            'national_against_receipt',
        ]
        for rec in self:
            rec.is_manual_scheduling = rec.somgroup_term_type in manual_types

    def _get_national_base_label(self, base):
        labels = dict(self._fields['national_due_base'].selection)
        return labels.get(base or 'supplier_invoice_date', 'Fecha Factura Proveedor')

    def _get_order_date(self, purchase_order):
        if purchase_order.date_order:
            return fields.Date.to_date(purchase_order.date_order)
        return fields.Date.today()

    def _get_invoice_date(self, purchase_order):
        if 'supplier_invoice_date' in purchase_order._fields and purchase_order.supplier_invoice_date:
            return purchase_order.supplier_invoice_date
        if 'effective_date' in purchase_order._fields and purchase_order.effective_date:
            return purchase_order.effective_date
        return self._get_order_date(purchase_order)

    def _get_national_base_date(self, purchase_order, base):
        if hasattr(purchase_order, '_get_national_base_date'):
            return purchase_order._get_national_base_date(base)

        if base == 'order_date':
            return self._get_order_date(purchase_order)

        if base == 'confirmation_date':
            if 'date_approve' in purchase_order._fields and purchase_order.date_approve:
                return fields.Date.to_date(purchase_order.date_approve)
            return self._get_order_date(purchase_order)

        if base == 'supplier_invoice_date':
            return self._get_invoice_date(purchase_order)

        return False

    def _append_advance_line(self, result, purchase_order, percent, note=None):
        amount = purchase_order.amount_total or 0.0
        order_date = self._get_order_date(purchase_order)

        result.append({
            'type': 'advance',
            'percent': percent,
            'amount': round(amount * percent / 100, 2),
            'due_date': order_date,
            'note': note or f'Anticipo {percent:.0f}% al confirmar OC.',
            'is_manual': True,
        })

    def compute_due_dates(self, purchase_order):
        """
        Calcula fechas de pago para compras SOMGROUP.

        Soporta:
        - Importación: BL, ETA, CAD, contra BL, arribo.
        - Nacional: fecha OC, confirmación, factura proveedor, recepción esperada,
          recepción real o fecha manual de referencia.
        """
        self.ensure_one()

        result = []
        amount = purchase_order.amount_total or 0.0
        bl_date = purchase_order.bl_date
        eta_date = purchase_order.eta_date
        order_date = self._get_order_date(purchase_order)
        invoice_date = self._get_invoice_date(purchase_order)
        term_type = self.somgroup_term_type

        if term_type == 'full_advance':
            result.append({
                'type': 'advance',
                'percent': 100.0,
                'amount': amount,
                'due_date': order_date,
                'note': 'Pago total anticipado antes de producción / surtido.',
                'is_manual': True,
            })

        elif term_type == 'days_after_bl':
            due_date = False
            if bl_date and self.balance_days:
                due_date = bl_date + timedelta(days=self.balance_days)

            result.append({
                'type': 'balance',
                'percent': 100.0,
                'amount': amount,
                'due_date': due_date,
                'note': f'{self.balance_days} días después de fecha BL.' + (
                    '' if due_date else ' Ingrese Fecha BL para calcular vencimiento.'
                ),
                'is_manual': not bool(due_date),
            })

        elif term_type == 'days_after_invoice':
            due_date = False
            if invoice_date and self.balance_days:
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
                self._append_advance_line(
                    result,
                    purchase_order,
                    advance_pct,
                    f'Anticipo {advance_pct:.0f}% al confirmar proforma.'
                )

            due_date = False
            note = f'Balance {balance_pct:.0f}% — Contra Entrega / CAD. '
            if eta_date:
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

            self._append_advance_line(
                result,
                purchase_order,
                advance_pct,
                f'Anticipo {advance_pct:.0f}% al confirmar proforma.'
            )

            due_date = False
            note = f'Balance {balance_pct:.0f}%. '
            if bl_date and self.balance_days:
                due_date = bl_date + timedelta(days=self.balance_days)
                note += f'Vence {self.balance_days} días después de BL.'
            elif eta_date:
                days_before = self.days_before_eta or 7
                due_date = eta_date - timedelta(days=days_before)
                note += f'Pagar antes de ETA. Requiere Telex Release.'
            else:
                note += 'Ingrese Fecha BL o ETA para calcular vencimiento.'

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

            self._append_advance_line(
                result,
                purchase_order,
                advance_pct,
                f'Anticipo {advance_pct:.0f}% al confirmar proforma.'
            )

            due_date = False
            if invoice_date and self.balance_days:
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

            if balance_pct < 0:
                raise UserError(
                    f'El término de pago "{self.name}" está mal capturado: '
                    f'anticipo {advance_pct:.0f}% + segundo anticipo '
                    f'{second_pct:.0f}% suman más de 100%. Corrígelo antes de '
                    'generar el calendario.'
                )

            self._append_advance_line(
                result,
                purchase_order,
                advance_pct,
                f'Anticipo {advance_pct:.0f}%.'
            )

            if second_pct > 0:
                due_date = False
                note = f'Contra entrega {second_pct:.0f}%. '
                if eta_date:
                    due_date = eta_date - timedelta(days=self.days_before_eta or 7)
                    note += f'Pagar antes de ETA ({eta_date}).'
                else:
                    note += 'Ingrese ETA para calcular vencimiento.'

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
                due_date = eta_date + timedelta(days=self.balance_days)
            else:
                note += ' Ingrese ETA para calcular vencimiento.'

            result.append({
                'type': 'balance',
                'percent': balance_pct,
                'amount': round(amount * balance_pct / 100, 2),
                'due_date': due_date,
                'note': note,
                'is_manual': not bool(due_date),
            })

        elif term_type == 'national_days_after_base':
            base = (
                purchase_order.national_due_base
                if 'national_due_base' in purchase_order._fields and purchase_order.national_due_base
                else self.national_due_base
            ) or 'supplier_invoice_date'

            base_date = self._get_national_base_date(purchase_order, base)
            due_date = False
            if base_date:
                due_date = base_date + timedelta(days=self.balance_days or 0)

            base_label = self._get_national_base_label(base)

            result.append({
                'type': 'balance',
                'percent': 100.0,
                'amount': amount,
                'due_date': due_date,
                'note': f'Pago nacional a {self.balance_days or 0} días de {base_label}.' + (
                    '' if due_date else f' Capture {base_label} para calcular vencimiento.'
                ),
                'is_manual': not bool(due_date),
            })

        elif term_type == 'national_against_receipt':
            advance_pct = self.advance_percent or 0.0
            balance_pct = 100.0 - advance_pct

            if advance_pct > 0:
                self._append_advance_line(
                    result,
                    purchase_order,
                    advance_pct,
                    f'Anticipo nacional {advance_pct:.0f}% al confirmar OC.'
                )

            receipt_date = False
            if 'national_receipt_date' in purchase_order._fields and purchase_order.national_receipt_date:
                receipt_date = purchase_order.national_receipt_date
            elif (
                'national_expected_receipt_date' in purchase_order._fields
                and purchase_order.national_expected_receipt_date
            ):
                receipt_date = purchase_order.national_expected_receipt_date

            due_date = False
            note = f'Balance nacional {balance_pct:.0f}% contra recepción / entrega.'
            if receipt_date:
                days_before = self.days_before_eta or 0
                due_date = receipt_date - timedelta(days=days_before)
                if days_before:
                    note += f' Programar {days_before} días antes de recepción ({receipt_date}).'
                else:
                    note += f' Programar el día de recepción ({receipt_date}).'
            else:
                note += ' Capture recepción esperada o real para calcular vencimiento.'

            result.append({
                'type': 'balance',
                'percent': balance_pct,
                'amount': round(amount * balance_pct / 100, 2),
                'due_date': due_date,
                'note': note,
                'is_manual': not bool(due_date),
            })

        elif term_type == 'national_advance_balance':
            advance_pct = self.advance_percent or 30.0
            balance_pct = 100.0 - advance_pct

            self._append_advance_line(
                result,
                purchase_order,
                advance_pct,
                f'Anticipo nacional {advance_pct:.0f}% al confirmar OC.'
            )

            base = (
                purchase_order.national_due_base
                if 'national_due_base' in purchase_order._fields and purchase_order.national_due_base
                else self.national_due_base
            ) or 'supplier_invoice_date'

            base_date = self._get_national_base_date(purchase_order, base)
            due_date = False
            if base_date:
                due_date = base_date + timedelta(days=self.balance_days or 0)

            base_label = self._get_national_base_label(base)

            result.append({
                'type': 'balance',
                'percent': balance_pct,
                'amount': round(amount * balance_pct / 100, 2),
                'due_date': due_date,
                'note': f'Saldo nacional {balance_pct:.0f}% a {self.balance_days or 0} días de {base_label}.' + (
                    '' if due_date else f' Capture {base_label} para calcular vencimiento.'
                ),
                'is_manual': not bool(due_date),
            })

        else:
            result.append({
                'type': 'balance',
                'percent': 100.0,
                'amount': amount,
                'due_date': False,
                'note': 'Término estándar Odoo.',
                'is_manual': False,
            })

        return result