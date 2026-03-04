## ./__init__.py
```py
from . import models```

## ./__manifest__.py
```py
{
    'name': 'SOMGROUP - Términos de Pago Importaciones',
    'version': '19.0.1.1.0',
    'category': 'Purchase',
    'summary': 'Términos de pago especiales para importaciones con fecha BL y cálculo automático de vencimientos',
    'description': """
        Módulo para gestión de pagos a proveedores de importación:
        - Campo Fecha BL en orden de compra
        - Términos de pago con reglas de anticipos, balances y vencimientos
        - Cálculo automático de fechas basado en BL o ETA
        - Soporte para términos CAD, contra entrega, anticipos parciales
        - Integración con account.payment (pagos contables reales)
        - Estado del calendario actualizado automáticamente al confirmar pagos
    """,
    'author': 'Alphaqueb Consulting SAS',
    'depends': ['purchase', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'data/payment_term_data.xml',
        'views/purchase_order_views.xml',
        'views/payment_term_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}```

## ./data/payment_term_data.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <data noupdate="1">

        <!-- ═══════════════════════════════════════════════════════════════
             TÉRMINOS DE PAGO SOMGROUP — IMPORTACIONES
             Sesión #169 — Alphaqueb Consulting SAS — Febrero 2026
        ═══════════════════════════════════════════════════════════════ -->

        <!-- ─────────────────────────────────────────────────────────────────
             NOTA TÉCNICA — Odoo 17+:
             El campo 'value' en account.payment.term.line ya NO acepta
             'balance'. Los valores válidos son solo 'percent' y 'fixed'.
             La suma de value_amount de TODAS las líneas debe ser exactamente 100%.
             ───────────────────────────────────────────────────────────── -->

        <!-- 1. 30% ANTICIPO - 70% 90 DÍAS DESPUÉS DE BL -->
        <record id="payment_term_30_70_90bl" model="account.payment.term">
            <field name="name">30% Anticipo - 70% 90 días BL</field>
            <field name="note">30% al confirmar proforma. 70% a 90 días de la fecha BL.</field>
            <field name="somgroup_term_type">advance_balance</field>
            <field name="advance_percent">30.0</field>
            <field name="balance_days">90</field>
            <field name="payment_term_note">Anticipo al confirmar OC. Balance se calcula automáticamente al ingresar fecha BL.</field>
            <field name="line_ids" eval="[
                Command.create({'value': 'percent', 'value_amount': 30.0, 'nb_days': 0}),
                Command.create({'value': 'percent', 'value_amount': 70.0, 'nb_days': 90}),
            ]"/>
        </record>

        <!-- 2. 30% ANTICIPO - 70% CONTRAENTREGA -->
        <record id="payment_term_30_70_cad" model="account.payment.term">
            <field name="name">30% Anticipo - 70% Contraentrega</field>
            <field name="note">30% al confirmar proforma. 70% contra entrega / CAD antes de arribo.</field>
            <field name="somgroup_term_type">against_delivery</field>
            <field name="advance_percent">30.0</field>
            <field name="days_before_eta">7</field>
            <field name="payment_term_note">Programar pago del balance 7 días antes de ETA para asegurar Telex Release. Especialmente importante con proveedores en China o Turquía.</field>
            <field name="line_ids" eval="[
                Command.create({'value': 'percent', 'value_amount': 30.0, 'nb_days': 0}),
                Command.create({'value': 'percent', 'value_amount': 70.0, 'nb_days': 1}),
            ]"/>
        </record>

        <!-- 3. 50% ANTICIPO - 50% CONTRAENTREGA -->
        <record id="payment_term_50_50_cad" model="account.payment.term">
            <field name="name">50% Anticipo - 50% Contraentrega</field>
            <field name="note">50% al confirmar proforma. 50% contra entrega / CAD antes de arribo.</field>
            <field name="somgroup_term_type">against_delivery</field>
            <field name="advance_percent">50.0</field>
            <field name="days_before_eta">7</field>
            <field name="payment_term_note">Programar pago del balance 7 días antes de ETA para asegurar Telex Release.</field>
            <field name="line_ids" eval="[
                Command.create({'value': 'percent', 'value_amount': 50.0, 'nb_days': 0}),
                Command.create({'value': 'percent', 'value_amount': 50.0, 'nb_days': 1}),
            ]"/>
        </record>

        <!-- 4. 90 DÍAS DESPUÉS DE FECHA FACTURA -->
        <record id="payment_term_90_invoice" model="account.payment.term">
            <field name="name">90 días después de Fecha Factura</field>
            <field name="note">Pago total a 90 días de la fecha de factura comercial.</field>
            <field name="somgroup_term_type">days_after_invoice</field>
            <field name="balance_days">90</field>
            <field name="payment_term_note">Vencimiento calculado desde fecha de factura del proveedor.</field>
            <field name="line_ids" eval="[
                Command.create({'value': 'percent', 'value_amount': 100.0, 'nb_days': 90}),
            ]"/>
        </record>

        <!-- 5. 20% ANTICIPO - 80% CONTRAENTREGA -->
        <record id="payment_term_20_80_cad" model="account.payment.term">
            <field name="name">20% Anticipo - 80% Contraentrega</field>
            <field name="note">20% al confirmar proforma. 80% contra entrega / CAD antes de arribo.</field>
            <field name="somgroup_term_type">against_delivery</field>
            <field name="advance_percent">20.0</field>
            <field name="days_before_eta">7</field>
            <field name="payment_term_note">Programar pago del 80% 7 días antes de ETA. Sin pago no hay Telex Release.</field>
            <field name="line_ids" eval="[
                Command.create({'value': 'percent', 'value_amount': 20.0, 'nb_days': 0}),
                Command.create({'value': 'percent', 'value_amount': 80.0, 'nb_days': 1}),
            ]"/>
        </record>

        <!-- 6. 30% ANTICIPO - 70% 1 SEMANA DESPUÉS DEL ARRIBO -->
        <record id="payment_term_30_70_1week_arrival" model="account.payment.term">
            <field name="name">30% Anticipo - 70% 1 semana después Arribo</field>
            <field name="note">30% al confirmar proforma. 70% a 7 días del arribo (ETA + 7 días).</field>
            <field name="somgroup_term_type">advance_days_arrival</field>
            <field name="advance_percent">30.0</field>
            <field name="balance_days">7</field>
            <field name="payment_term_note">Verificar que el proveedor acepte pago posterior al arribo. Requiere negociación de Telex Release.</field>
            <field name="line_ids" eval="[
                Command.create({'value': 'percent', 'value_amount': 30.0, 'nb_days': 0}),
                Command.create({'value': 'percent', 'value_amount': 70.0, 'nb_days': 7}),
            ]"/>
        </record>

        <!-- 7. 30 DÍAS (crédito simple) -->
        <record id="payment_term_30_days" model="account.payment.term">
            <field name="name">30 días</field>
            <field name="note">Pago total a 30 días. Se aplica desde BL para importaciones o desde factura para fletes.</field>
            <field name="somgroup_term_type">days_after_bl</field>
            <field name="balance_days">30</field>
            <field name="payment_term_note">Para importaciones: 30 días desde fecha BL. Para fletes terrestres/marítimos: 30 días desde fecha factura.</field>
            <field name="line_ids" eval="[
                Command.create({'value': 'percent', 'value_amount': 100.0, 'nb_days': 30}),
            ]"/>
        </record>

        <!-- 8. 50% ANTICIPO - 50% 90 DÍAS FECHA FACTURA -->
        <record id="payment_term_50_50_90invoice" model="account.payment.term">
            <field name="name">50% Anticipo - 50% 90 días Factura</field>
            <field name="note">50% al confirmar proforma. 50% a 90 días de la fecha de factura.</field>
            <field name="somgroup_term_type">advance_days_invoice</field>
            <field name="advance_percent">50.0</field>
            <field name="balance_days">90</field>
            <field name="payment_term_note">Vencimiento del balance calculado desde fecha de factura comercial del proveedor.</field>
            <field name="line_ids" eval="[
                Command.create({'value': 'percent', 'value_amount': 50.0, 'nb_days': 0}),
                Command.create({'value': 'percent', 'value_amount': 50.0, 'nb_days': 90}),
            ]"/>
        </record>

        <!-- 9. 100% PAGO ANTICIPADO -->
        <record id="payment_term_100_advance" model="account.payment.term">
            <field name="name">100% Pago Anticipado</field>
            <field name="note">Pago total antes de inicio de producción. Sin pago no hay carga.</field>
            <field name="somgroup_term_type">full_advance</field>
            <field name="advance_percent">100.0</field>
            <field name="payment_term_note">Confirmar recepción del pago antes de solicitar al proveedor que inicie producción o reserve mercancía.</field>
            <field name="line_ids" eval="[
                Command.create({'value': 'percent', 'value_amount': 100.0, 'nb_days': 0}),
            ]"/>
        </record>

        <!-- 10. 150 DÍAS DESPUÉS DE BL -->
        <record id="payment_term_150_bl" model="account.payment.term">
            <field name="name">150 días después de BL</field>
            <field name="note">Pago total a 150 días de la fecha BL (Shipped on Board).</field>
            <field name="somgroup_term_type">days_after_bl</field>
            <field name="balance_days">150</field>
            <field name="payment_term_note">Ingresar fecha BL para cálculo automático del vencimiento.</field>
            <field name="line_ids" eval="[
                Command.create({'value': 'percent', 'value_amount': 100.0, 'nb_days': 150}),
            ]"/>
        </record>

        <!-- 11. 30% ANTICIPO - 70% CAD -->
        <record id="payment_term_30_70_cad2" model="account.payment.term">
            <field name="name">30% Anticipo - 70% CAD</field>
            <field name="note">30% al confirmar. 70% contra documentos (CAD) — equivale a contra entrega.</field>
            <field name="somgroup_term_type">against_delivery</field>
            <field name="advance_percent">30.0</field>
            <field name="days_before_eta">7</field>
            <field name="payment_term_note">CAD = Contra Documentos = Contra Entrega = Contra BL. Programar 7 días antes de ETA.</field>
            <field name="line_ids" eval="[
                Command.create({'value': 'percent', 'value_amount': 30.0, 'nb_days': 0}),
                Command.create({'value': 'percent', 'value_amount': 70.0, 'nb_days': 1}),
            ]"/>
        </record>

        <!-- 12. 90 DÍAS DESPUÉS DE BL -->
        <record id="payment_term_90_bl" model="account.payment.term">
            <field name="name">90 días después de BL</field>
            <field name="note">Pago total a 90 días de la fecha BL.</field>
            <field name="somgroup_term_type">days_after_bl</field>
            <field name="balance_days">90</field>
            <field name="payment_term_note">Ingresar fecha BL para cálculo automático del vencimiento.</field>
            <field name="line_ids" eval="[
                Command.create({'value': 'percent', 'value_amount': 100.0, 'nb_days': 90}),
            ]"/>
        </record>

        <!-- 13. 120 DÍAS DESPUÉS DE BL -->
        <record id="payment_term_120_bl" model="account.payment.term">
            <field name="name">120 días después de BL</field>
            <field name="note">Pago total a 120 días de la fecha BL.</field>
            <field name="somgroup_term_type">days_after_bl</field>
            <field name="balance_days">120</field>
            <field name="payment_term_note">Ingresar fecha BL para cálculo automático del vencimiento.</field>
            <field name="line_ids" eval="[
                Command.create({'value': 'percent', 'value_amount': 100.0, 'nb_days': 120}),
            ]"/>
        </record>

        <!-- 15. 50% ANTICIPO / 25% CONTRAENTREGA / 25% A 60 DÍAS -->
        <record id="payment_term_50_25_25" model="account.payment.term">
            <field name="name">50% Anticipo / 25% Contraentrega / 25% 60 días</field>
            <field name="note">50% anticipo, 25% contra entrega, 25% a 60 días de la fecha BL/arribo.</field>
            <field name="somgroup_term_type">advance_days_arrival</field>
            <field name="advance_percent">50.0</field>
            <field name="second_advance_percent">25.0</field>
            <field name="balance_days">60</field>
            <field name="days_before_eta">7</field>
            <field name="payment_term_note">3 tramos: 50% anticipo, 25% antes de arribo (Telex Release), 25% a 60 días de arribo.</field>
            <field name="line_ids" eval="[
                Command.create({'value': 'percent', 'value_amount': 50.0, 'nb_days': 0}),
                Command.create({'value': 'percent', 'value_amount': 25.0, 'nb_days': 1}),
                Command.create({'value': 'percent', 'value_amount': 25.0, 'nb_days': 60}),
            ]"/>
        </record>

        <!-- 16. CAD (Contra Documentos) — 100% -->
        <record id="payment_term_cad_full" model="account.payment.term">
            <field name="name">CAD - Contra Documentos (100%)</field>
            <field name="note">Pago total contra documentos / contra BL antes del arribo.</field>
            <field name="somgroup_term_type">against_delivery</field>
            <field name="advance_percent">0.0</field>
            <field name="days_before_eta">7</field>
            <field name="payment_term_note">CAD = Contra Documentos = Contra Entrega. Sin anticipo previo. Pagar 7 días antes de ETA para obtener Telex Release.</field>
            <field name="line_ids" eval="[
                Command.create({'value': 'percent', 'value_amount': 100.0, 'nb_days': 1}),
            ]"/>
        </record>

        <!-- 17. CL (Contra BL) — 100% -->
        <record id="payment_term_cl_full" model="account.payment.term">
            <field name="name">CL - Contra BL (100%)</field>
            <field name="note">Pago total contra BL antes del arribo al puerto mexicano.</field>
            <field name="somgroup_term_type">against_delivery</field>
            <field name="advance_percent">0.0</field>
            <field name="days_before_eta">7</field>
            <field name="payment_term_note">CL = Contra BL = Contra Documentos = CAD. Sin anticipo. Pagar antes de ETA para obtener Telex Release. Proveedores en Turquía/China: programar con 10 días de margen.</field>
            <field name="line_ids" eval="[
                Command.create({'value': 'percent', 'value_amount': 100.0, 'nb_days': 1}),
            ]"/>
        </record>

        <!-- EXTRA: 60 DÍAS DESPUÉS DE BL -->
        <record id="payment_term_60_bl" model="account.payment.term">
            <field name="name">60 días después de BL</field>
            <field name="note">Pago total a 60 días de la fecha BL.</field>
            <field name="somgroup_term_type">days_after_bl</field>
            <field name="balance_days">60</field>
            <field name="payment_term_note">Ingresar fecha BL para cálculo automático del vencimiento.</field>
            <field name="line_ids" eval="[
                Command.create({'value': 'percent', 'value_amount': 100.0, 'nb_days': 60}),
            ]"/>
        </record>

        <!-- EXTRA: 360 DÍAS DESPUÉS DE BL (Gramazini) -->
        <record id="payment_term_360_bl" model="account.payment.term">
            <field name="name">360 días después de BL</field>
            <field name="note">Crédito a 360 días de la fecha BL. Término largo plazo.</field>
            <field name="somgroup_term_type">days_after_bl</field>
            <field name="balance_days">360</field>
            <field name="payment_term_note">Verificar que proforma y factura comercial coincidan antes de la fecha de vencimiento.</field>
            <field name="line_ids" eval="[
                Command.create({'value': 'percent', 'value_amount': 100.0, 'nb_days': 360}),
            ]"/>
        </record>

    </data>
</odoo>```

## ./models/__init__.py
```py
from . import account_payment_term
from . import purchase_order
from . import account_payment
from . import account_payment_register```

## ./models/account_move.py
```py
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
                schedules._recompute_from_payments_by_order()```

## ./models/account_payment_register.py
```py
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
        return vals```

## ./models/account_payment_term.py
```py
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
        store=False,
        help="Indica si este término necesita la fecha BL para calcular vencimientos"
    )
    requires_eta = fields.Boolean(
        string='Requiere ETA',
        compute='_compute_requires_eta',
        store=False,
        help="Indica si este término requiere seguimiento manual de ETA"
    )
    is_manual_scheduling = fields.Boolean(
        string='Programación Manual',
        compute='_compute_is_manual',
        store=False,
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
```

## ./models/account_payment.py
```py
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    purchase_schedule_id = fields.Many2one(
        'purchase.payment.schedule',
        string='Hito de Pago OC',
        ondelete='set null',
        help='Enlace automático con el calendario de pagos de importación'
    )

    def action_post(self):
        """Al confirmar el pago, sincronizar hitos de todas las OC vinculadas."""
        res = super().action_post()
        self._sync_purchase_schedules()
        return res

    def action_cancel(self):
        """Al cancelar el pago, revertir hitos vinculados."""
        # Recolectar OC antes de cancelar
        purchase_orders = self._get_related_purchase_orders()
        schedules = self.mapped('purchase_schedule_id')
        res = super().action_cancel()
        # Recomputar hitos directamente vinculados
        for schedule in schedules:
            schedule._recompute_from_payments()
        # Recomputar hitos detectados por OC
        self._recompute_schedules_for_orders(purchase_orders)
        return res

    def _get_related_purchase_orders(self):
        """Obtiene las OC relacionadas via líneas de factura."""
        orders = self.env['purchase.order']
        for payment in self:
            # Buscar facturas conciliadas con este pago
            invoices = payment._get_reconciled_invoices()
            for inv in invoices:
                orders |= inv.invoice_line_ids.mapped('purchase_line_id.order_id')
        return orders

    def _get_reconciled_invoices(self):
        """Retorna las facturas (account.move) conciliadas con este pago."""
        self.ensure_one()
        moves = self.env['account.move']
        # Buscar via reconciled_invoice_ids si existe (Odoo 17+)
        if hasattr(self, 'reconciled_invoice_ids'):
            return self.reconciled_invoice_ids
        # Fallback: buscar via líneas de diario conciliadas
        reconciled_lines = self.line_ids.filtered(
            lambda l: l.account_id.account_type in (
                'asset_receivable', 'liability_payable'
            )
        )
        for line in reconciled_lines:
            for matched in (line.matched_debit_ids | line.matched_credit_ids):
                counterpart = matched.debit_move_id if line == matched.credit_move_id else matched.credit_move_id
                if counterpart.move_id.move_type in ('in_invoice', 'in_refund', 'out_invoice', 'out_refund'):
                    moves |= counterpart.move_id
        return moves

    def _sync_purchase_schedules(self):
        """
        Sincronización automática: detecta OC vinculadas via facturas y
        recalcula el estado de todos sus hitos de pago.
        No requiere que el usuario haya usado el botón 'Pagar' del hito.
        """
        purchase_orders = self._get_related_purchase_orders()

        # También procesar hitos directamente vinculados (vía botón Pagar)
        direct_schedules = self.mapped('purchase_schedule_id')
        for schedule in direct_schedules:
            schedule._recompute_from_payments()
            purchase_orders |= schedule.order_id

        # Recomputar todos los hitos de las OC detectadas
        self._recompute_schedules_for_orders(purchase_orders)

    def _recompute_schedules_for_orders(self, purchase_orders):
        """Recomputa hitos de pago para un conjunto de OC."""
        if not purchase_orders:
            return
        schedules = purchase_orders.mapped('payment_schedule_ids').filtered(
            lambda s: s.state != 'paid'
        )
        if schedules:
            schedules._recompute_from_payments_by_order()```

## ./models/purchase_order.py
```py
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    # ─── Campos de importación ───────────────────────────────────────────────

    bl_date = fields.Date(
        string='Fecha BL',
        help="Bill of Lading — Shipped on Board Date. Base para cálculo de vencimientos con crédito (N días después de BL)."
    )
    bl_number = fields.Char(
        string='Número BL',
        help="Número del Bill of Lading"
    )
    eta_date = fields.Date(
        string='ETA',
        help="Estimated Time of Arrival — fecha estimada de arribo al puerto mexicano. "
             "Necesaria para términos contra entrega / CAD."
    )
    container_ids = fields.One2many(
        'purchase.order.container',
        'order_id',
        string='Contenedores'
    )
    container_count = fields.Integer(
        string='# Contenedores',
        compute='_compute_container_count'
    )

    # ─── Campos de pago calculados ───────────────────────────────────────────

    payment_schedule_ids = fields.One2many(
        'purchase.payment.schedule',
        'order_id',
        string='Calendario de Pagos',
        help="Pagos calculados automáticamente según el término de pago y fecha BL/ETA"
    )
    payment_schedule_warning = fields.Char(
        string='Aviso de Pago',
        compute='_compute_payment_warning',
        store=False,
    )
    requires_bl_date = fields.Boolean(
        string='Requiere Fecha BL',
        compute='_compute_term_flags',
        store=False,
    )
    requires_eta = fields.Boolean(
        string='Requiere ETA',
        compute='_compute_term_flags',
        store=False,
    )
    is_import_order = fields.Boolean(
        string='Es Orden de Importación',
        default=False,
        help="Activa los campos de BL, ETA y calendario de pagos de importación"
    )
    telex_release_required = fields.Boolean(
        string='Requiere Telex Release',
        compute='_compute_term_flags',
        store=False,
        help="El pago del balance debe completarse antes del arribo para obtener Telex Release"
    )
    advance_amount = fields.Monetary(
        string='Monto Anticipo',
        compute='_compute_advance_amount',
        store=False,
        currency_field='currency_id',
    )
    balance_amount = fields.Monetary(
        string='Monto Balance',
        compute='_compute_advance_amount',
        store=False,
        currency_field='currency_id',
    )
    next_payment_date = fields.Date(
        string='Próximo Vencimiento',
        compute='_compute_next_payment_date',
        store=False,
    )
    overdue_payments = fields.Boolean(
        string='Tiene Pagos Vencidos',
        compute='_compute_next_payment_date',
        store=False,
    )

    # ─── Computes ────────────────────────────────────────────────────────────

    @api.depends('container_ids')
    def _compute_container_count(self):
        for rec in self:
            rec.container_count = len(rec.container_ids)

    @api.depends('payment_term_id', 'payment_term_id.somgroup_term_type')
    def _compute_term_flags(self):
        bl_types = ['days_after_bl']
        eta_types = ['against_delivery', 'advance_balance', 'advance_days_arrival']
        telex_types = ['against_delivery', 'advance_balance', 'advance_days_arrival']
        for rec in self:
            t = rec.payment_term_id.somgroup_term_type if rec.payment_term_id else False
            rec.requires_bl_date = t in bl_types
            rec.requires_eta = t in eta_types
            rec.telex_release_required = t in telex_types

    @api.depends('payment_schedule_ids', 'payment_schedule_ids.amount',
                 'payment_schedule_ids.payment_type')
    def _compute_advance_amount(self):
        for rec in self:
            advances = rec.payment_schedule_ids.filtered(
                lambda l: l.payment_type == 'advance')
            balances = rec.payment_schedule_ids.filtered(
                lambda l: l.payment_type != 'advance')
            rec.advance_amount = sum(advances.mapped('amount'))
            rec.balance_amount = sum(balances.mapped('amount'))

    @api.depends('payment_schedule_ids', 'payment_schedule_ids.due_date',
                 'payment_schedule_ids.state')
    def _compute_next_payment_date(self):
        from datetime import date
        today = date.today()
        for rec in self:
            pending = rec.payment_schedule_ids.filtered(
                lambda l: l.state == 'pending' and l.due_date)
            overdue = pending.filtered(lambda l: l.due_date < today)
            rec.overdue_payments = bool(overdue)
            upcoming = pending.filtered(lambda l: l.due_date >= today)
            if upcoming:
                rec.next_payment_date = min(upcoming.mapped('due_date'))
            else:
                rec.next_payment_date = False

    @api.depends('payment_term_id', 'bl_date', 'eta_date',
                 'payment_schedule_ids', 'payment_schedule_ids.due_date',
                 'payment_schedule_ids.state')
    def _compute_payment_warning(self):
        from datetime import date, timedelta
        today = date.today()
        for rec in self:
            warnings = []
            if rec.requires_bl_date and not rec.bl_date:
                warnings.append('⚠ Ingrese Fecha BL para calcular vencimientos automáticamente.')
            if rec.requires_eta and not rec.eta_date:
                warnings.append('⚠ Ingrese ETA para programar pagos contra entrega.')
            if rec.overdue_payments:
                warnings.append('🔴 VENCIDO: Hay pagos vencidos en este pedido.')
            else:
                upcoming = rec.payment_schedule_ids.filtered(
                    lambda l: l.state == 'pending' and l.due_date and
                    today <= l.due_date <= today + timedelta(days=7)
                )
                if upcoming:
                    warnings.append(f'🟡 Vence en 7 días: {upcoming[0].due_date}')
            rec.payment_schedule_warning = ' | '.join(warnings) if warnings else ''

    # ─── Onchange / Actions ──────────────────────────────────────────────────

    @api.onchange('payment_term_id', 'bl_date', 'eta_date', 'amount_total', 'is_import_order')
    def _onchange_recalculate_schedule(self):
        if not self.is_import_order or not self.payment_term_id:
            return
        if self.payment_term_id.somgroup_term_type == 'standard':
            return
        term_type = self.payment_term_id.somgroup_term_type
        if term_type in ['days_after_bl', 'advance_balance'] and not self.bl_date:
            return {'warning': {
                'title': _('Fecha BL requerida'),
                'message': _('El término "%s" requiere la Fecha BL para calcular el vencimiento del balance.') % self.payment_term_id.name,
            }}
        if term_type in ['against_delivery', 'advance_days_arrival'] and not self.eta_date:
            return {'warning': {
                'title': _('ETA requerida'),
                'message': _('El término "%s" requiere la ETA para programar el pago antes del arribo.') % self.payment_term_id.name,
            }}

    def action_calculate_payment_schedule(self):
        for order in self:
            if not order.payment_term_id:
                raise UserError(_('Seleccione un término de pago antes de calcular.'))
            if order.payment_term_id.somgroup_term_type == 'standard':
                raise UserError(_('Este término usa el motor estándar de Odoo. El calendario se gestiona en las facturas.'))
            order._recalculate_payment_schedule()

    def _recalculate_payment_schedule(self):
        self.ensure_one()
        # Solo borramos los pending que NO tengan pagos vinculados
        pending = self.payment_schedule_ids.filtered(
            lambda l: l.state == 'pending' and not l.payment_ids
        )
        pending.unlink()

        lines = self.payment_term_id.compute_due_dates(self)
        schedule_vals = []
        for line in lines:
            schedule_vals.append({
                'order_id': self.id,
                'payment_type': line['type'],
                'percent': line['percent'],
                'amount': line['amount'],
                'due_date': line['due_date'],
                'note': line['note'],
                'is_manual': line['is_manual'],
                'state': 'pending',
            })
        if schedule_vals:
            self.env['purchase.payment.schedule'].create(schedule_vals)

    def write(self, vals):
        res = super().write(vals)
        trigger_fields = {'bl_date', 'eta_date', 'payment_term_id'}
        if trigger_fields.intersection(vals.keys()):
            import_orders = self.filtered(
                lambda o: o.is_import_order and
                o.payment_term_id and
                o.payment_term_id.somgroup_term_type != 'standard'
            )
            for order in import_orders:
                order._recalculate_payment_schedule()
        return res


class PurchaseOrderContainer(models.Model):
    _name = 'purchase.order.container'
    _description = 'Contenedor de Importación'
    _order = 'order_id, name'

    order_id = fields.Many2one('purchase.order', string='Orden de Compra', ondelete='cascade', required=True)
    name = fields.Char(string='No. Contenedor', required=True)
    container_type = fields.Selection([
        ('20', '20\''),
        ('40', '40\''),
        ('40hc', '40\' HC'),
    ], string='Tipo', default='20')
    seal_number = fields.Char(string='Sello')
    tax_amount = fields.Monetary(string='Impuestos MXN', currency_field='currency_id')
    tax_state = fields.Selection([
        ('pending', 'Pendiente'),
        ('paid', 'Pagado'),
    ], string='Estado Impuesto', default='pending')
    tax_paid_date = fields.Date(string='Fecha Pago Imp.')
    pedimento = fields.Char(string='Pedimento')
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.ref('base.MXN'),
        string='Moneda'
    )
    notes = fields.Char(string='Notas')


class PurchasePaymentSchedule(models.Model):
    _name = 'purchase.payment.schedule'
    _description = 'Calendario de Pagos - Importación'
    _order = 'due_date asc, id asc'

    order_id = fields.Many2one('purchase.order', string='Orden de Compra', ondelete='cascade', required=True)
    payment_type = fields.Selection([
        ('advance', 'Anticipo'),
        ('second_advance', 'Segundo Tramo'),
        ('balance', 'Balance / Liquidación'),
    ], string='Tipo', required=True)
    percent = fields.Float(string='%', digits=(5, 2))
    amount = fields.Monetary(string='Monto', currency_field='currency_id')
    currency_id = fields.Many2one(related='order_id.currency_id', store=True)
    due_date = fields.Date(string='Fecha Vencimiento')
    note = fields.Char(string='Nota Operativa')
    is_manual = fields.Boolean(string='Programación Manual', default=False)

    # ── Relación con pagos contables reales ──────────────────────────────────
    payment_ids = fields.One2many(
        'account.payment',
        'purchase_schedule_id',
        string='Pagos Contables',
        readonly=True,
    )

    # ── Estado y montos calculados desde contabilidad ────────────────────────
    state = fields.Selection([
        ('pending', 'Pendiente'),
        ('partial', 'Pago Parcial'),
        ('paid', 'Pagado'),
        ('overdue', 'Vencido'),
    ], string='Estado', compute='_compute_state_from_accounting', store=True, tracking=True)

    paid_amount = fields.Monetary(
        string='Monto Pagado',
        compute='_compute_paid_amounts',
        store=True,
        currency_field='currency_id',
    )
    remaining_amount = fields.Monetary(
        string='Saldo Pendiente',
        compute='_compute_remaining',
        store=True,
        currency_field='currency_id',
    )

    # ── Campos informativos (aún editables para registro manual si se desea) ──
    paid_date = fields.Date(
        string='Fecha Pago Real',
        compute='_compute_paid_date',
        store=True,
        readonly=False,
    )
    payment_reference = fields.Char(string='Referencia Pago / SPEI')

    days_until_due = fields.Integer(
        string='Días para Vencer',
        compute='_compute_days_until_due',
        store=False,
    )
    alert_color = fields.Char(
        string='Color Alerta',
        compute='_compute_days_until_due',
        store=False,
    )

    # ─── Computes ─────────────────────────────────────────────────────────────

    @api.depends('payment_ids', 'payment_ids.state', 'payment_ids.amount')
    def _compute_paid_amounts(self):
        for rec in self:
            posted = rec.payment_ids.filtered(lambda p: p.state == 'posted')
            rec.paid_amount = sum(posted.mapped('amount'))

    @api.depends('amount', 'paid_amount')
    def _compute_remaining(self):
        for rec in self:
            rec.remaining_amount = max(0.0, (rec.amount or 0.0) - (rec.paid_amount or 0.0))

    @api.depends('payment_ids', 'payment_ids.state', 'payment_ids.date')
    def _compute_paid_date(self):
        for rec in self:
            posted = rec.payment_ids.filtered(lambda p: p.state == 'posted').sorted('date')
            if posted:
                rec.paid_date = posted[-1].date
            elif not rec.paid_date:
                rec.paid_date = False

    @api.depends('paid_amount', 'amount', 'due_date')
    def _compute_state_from_accounting(self):
        from datetime import date
        today = date.today()
        for rec in self:
            if rec.paid_amount and rec.paid_amount >= (rec.amount - 0.01):
                rec.state = 'paid'
            elif rec.paid_amount and rec.paid_amount > 0:
                rec.state = 'partial'
            elif rec.due_date and rec.due_date < today:
                rec.state = 'overdue'
            else:
                rec.state = 'pending'

    @api.depends('due_date', 'state')
    def _compute_days_until_due(self):
        from datetime import date
        today = date.today()
        for rec in self:
            if rec.state == 'paid':
                rec.days_until_due = 0
                rec.alert_color = 'green'
            elif rec.due_date:
                delta = (rec.due_date - today).days
                rec.days_until_due = delta
                if delta < 0:
                    rec.alert_color = 'red'
                elif delta <= 7:
                    rec.alert_color = 'orange'
                else:
                    rec.alert_color = 'gray'
            else:
                rec.days_until_due = 0
                rec.alert_color = 'blue'

    # ─── Métodos de recálculo desde contabilidad ─────────────────────────────

    def _recompute_from_payments(self):
        """
        Punto de entrada principal para actualizar hitos.
        Detecta si hay pagos directamente vinculados (purchase_schedule_id)
        o si hay que buscar por OC via conciliaciones contables.
        """
        direct = self.filtered(lambda s: s.payment_ids)
        indirect = self - direct

        if direct:
            direct._compute_paid_amounts()
            direct._compute_remaining()
            direct._compute_paid_date()
            direct._compute_state_from_accounting()

        if indirect:
            indirect._recompute_from_payments_by_order()

    def _recompute_from_payments_by_order(self):
        """
        Sincronización profunda con contabilidad:
        Busca TODOS los pagos posted asociados a facturas de la OC via
        conciliaciones contables, sin requerir purchase_schedule_id en el pago.
        Distribuye el total pagado en los hitos en orden cronológico.
        """
        from datetime import date
        today = date.today()

        orders = self.mapped('order_id')
        for order in orders:
            order_schedules = self.filtered(lambda s: s.order_id == order).sorted(
                key=lambda s: (s.due_date or date.max)
            )
            if not order_schedules:
                continue

            # ── Recolectar todos los pagos posted vinculados a facturas de la OC ──
            all_payments = self.env['account.payment']

            invoices = order.invoice_ids.filtered(
                lambda inv: inv.move_type == 'in_invoice' and inv.state == 'posted'
            )

            for inv in invoices:
                for line in inv.line_ids.filtered(
                    lambda l: l.account_id.account_type == 'liability_payable'
                ):
                    for matched in (line.matched_debit_ids | line.matched_credit_ids):
                        counterpart = (
                            matched.debit_move_id
                            if line == matched.credit_move_id
                            else matched.credit_move_id
                        )
                        payment = counterpart.move_id.payment_id
                        if payment and payment.state == 'posted':
                            all_payments |= payment

            # Incluir también pagos directamente vinculados vía purchase_schedule_id
            direct_payments = self.env['account.payment'].search([
                ('purchase_schedule_id', 'in', order_schedules.ids),
                ('state', '=', 'posted'),
            ])
            all_payments |= direct_payments

            total_paid = sum(all_payments.mapped('amount'))
            remaining_to_distribute = total_paid

            # ── Distribuir en hitos, en orden cronológico ──────────────────
            for schedule in order_schedules:
                # Pagos directamente vinculados a este hito específico
                direct = direct_payments.filtered(
                    lambda p: p.purchase_schedule_id == schedule
                )
                direct_amount = sum(direct.mapped('amount'))

                if direct_amount > 0:
                    # Usar monto exacto de pagos directos
                    schedule_paid = min(direct_amount, schedule.amount)
                    remaining_to_distribute = max(0.0, remaining_to_distribute - direct_amount)
                elif remaining_to_distribute > 0:
                    # Asignar del pool acumulado (pagos sin vínculo directo)
                    schedule_paid = min(remaining_to_distribute, schedule.amount)
                    remaining_to_distribute -= schedule_paid
                else:
                    schedule_paid = 0.0

                # Actualizar campos almacenados directamente
                schedule.paid_amount = schedule_paid
                schedule.remaining_amount = max(0.0, (schedule.amount or 0.0) - schedule_paid)

                # Determinar fecha de pago: último pago directo, o el más reciente del pool
                if direct:
                    schedule.paid_date = direct.sorted('date')[-1].date
                elif schedule_paid > 0 and all_payments:
                    schedule.paid_date = all_payments.sorted('date')[-1].date

                # Recalcular estado
                if schedule_paid >= (schedule.amount - 0.01):
                    schedule.state = 'paid'
                elif schedule_paid > 0:
                    schedule.state = 'partial'
                elif schedule.due_date and schedule.due_date < today:
                    schedule.state = 'overdue'
                else:
                    schedule.state = 'pending'

    # ─── Acción: Registrar pago sobre factura vinculada ─────────────────────

    def action_register_payment(self):
        self.ensure_one()
        if self.state == 'paid':
            raise UserError(_('Este hito ya está completamente pagado.'))

        order = self.order_id
        invoices = order.invoice_ids.filtered(
            lambda inv: inv.move_type == 'in_invoice'
            and inv.state == 'posted'
            and inv.payment_state in ('not_paid', 'partial')
        )

        if invoices:
            return {
                'name': _('Registrar Pago'),
                'type': 'ir.actions.act_window',
                'res_model': 'account.payment.register',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'active_model': 'account.move',
                    'active_ids': invoices.ids,
                    'default_amount': min(
                        self.remaining_amount or self.amount,
                        sum(invoices.mapped('amount_residual'))
                    ),
                    'default_purchase_schedule_id': self.id,
                },
            }
        else:
            return {
                'name': _('Registrar Anticipo al Proveedor'),
                'type': 'ir.actions.act_window',
                'res_model': 'account.payment',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_payment_type': 'outbound',
                    'default_partner_type': 'supplier',
                    'default_partner_id': order.partner_id.id,
                    'default_amount': self.remaining_amount or self.amount,
                    'default_currency_id': self.currency_id.id,
                    'default_purchase_schedule_id': self.id,
                    'default_date': fields.Date.today(),
                    'default_ref': '{} - {} ({:.0f}%)'.format(
                        order.name,
                        dict(self._fields['payment_type'].selection).get(self.payment_type, ''),
                        self.percent,
                    ),
                },
            }

    # ─── Acción legacy: Marcar pagado manualmente (sin contabilidad) ──────────

    def action_mark_paid(self):
        """Mantener para registros manuales sin integración contable."""
        from datetime import date
        for rec in self:
            if rec.state != 'paid':
                rec.write({
                    'paid_date': rec.paid_date or date.today(),
                })
                if not rec.payment_ids:
                    rec.write({'paid_amount': rec.amount})

    def action_mark_overdue(self):
        from datetime import date
        today = date.today()
        pending = self.search([
            ('state', 'in', ['pending', 'partial']),
            ('due_date', '<', today),
            ('due_date', '!=', False),
        ])
        pending._compute_state_from_accounting()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    # ─── Acción: Forzar sincronización manual con contabilidad ───────────────

    def action_sync_from_accounting(self):
        """Botón manual para forzar resync desde contabilidad."""
        self._recompute_from_payments_by_order()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    # ─── Smart button: ver pagos vinculados ──────────────────────────────────

    def action_view_payments(self):
        self.ensure_one()
        return {
            'name': _('Pagos Contables'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'list,form',
            'domain': [('purchase_schedule_id', '=', self.id)],
        }```

## ./views/payment_term_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>

    <!-- ── Heredar vista form de account.payment.term ───────────────────── -->
    <record id="view_payment_term_form_somgroup" model="ir.ui.view">
        <field name="name">account.payment.term.form.somgroup</field>
        <field name="model">account.payment.term</field>
        <field name="inherit_id" ref="account.view_payment_term_form"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='note']" position="after">
                <separator string="Configuración SOMGROUP — Importaciones"/>
                <group col="2">
                    <field name="somgroup_term_type" widget="radio"/>
                    <field name="payment_term_note" placeholder="Instrucciones para el área de Compras..."/>
                </group>

                <!-- Campos anticipo / tramos — visibles cuando aplica -->
                <group col="4"
                       invisible="somgroup_term_type in ['standard', 'days_after_bl', 'days_after_invoice', 'full_advance', 'against_delivery']">
                    <field name="advance_percent"/>
                    <field name="second_advance_percent"
                           invisible="somgroup_term_type != 'advance_days_arrival'"/>
                    <field name="balance_days"
                           invisible="somgroup_term_type in ['standard', 'full_advance', 'against_delivery']"/>
                </group>

                <!-- Campos contra entrega / ETA -->
                <group col="4"
                       invisible="somgroup_term_type in ['standard', 'days_after_bl', 'days_after_invoice', 'full_advance']">
                    <field name="advance_percent"
                           invisible="somgroup_term_type != 'against_delivery'"/>
                    <field name="days_before_eta"/>
                </group>

                <!-- Días para balance — solo para días después de BL/factura -->
                <group col="2"
                       invisible="somgroup_term_type not in ['days_after_bl', 'days_after_invoice']">
                    <field name="balance_days"/>
                </group>

                <!-- Indicadores de solo lectura -->
                <group col="2">
                    <field name="requires_bl_date" readonly="1"/>
                    <field name="requires_eta" readonly="1"/>
                    <field name="is_manual_scheduling" readonly="1"/>
                </group>
            </xpath>
        </field>
    </record>

</odoo>```

## ./views/purchase_order_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>

    <!-- ── Heredar vista form de purchase.order ─────────────────────────── -->
    <record id="view_purchase_order_form_somgroup" model="ir.ui.view">
        <field name="name">purchase.order.form.somgroup</field>
        <field name="model">purchase.order</field>
        <field name="inherit_id" ref="purchase.purchase_order_form"/>
        <field name="arch" type="xml">

            <!-- Toggle "Es Orden de Importación" junto al campo partner -->
            <xpath expr="//field[@name='partner_id']" position="after">
                <field name="is_import_order" widget="boolean_toggle"
                       string="¿Es Orden de Importación?"/>
            </xpath>

            <!-- Bloque BL/ETA debajo de payment_term_id -->
                <xpath expr="//field[@name='payment_term_id']/.." position="after">
                <!-- Aviso de pago (alerta dinámica) -->
                <div class="alert alert-warning mb-3"
                     invisible="not payment_schedule_warning">
                    <strong>⚠️ Aviso de Pago:</strong>
                    <field name="payment_schedule_warning" readonly="1" nolabel="1"/>
                </div>

                <!-- ── DATOS DE EMBARQUE ───────────────────────────────── -->
                <group string="📦 Datos de Embarque (BL / ETA)"
                       invisible="not is_import_order"
                       col="2">
                    <group string="Conocimiento de Embarque (BL)">
                        <field name="bl_number" placeholder="Ej. MAEU123456789"/>
                        <field name="bl_date"/>
                        <field name="requires_bl_date" invisible="1"/>
                    </group>
                    <group string="Estimado de Llegada">
                        <field name="eta_date"
                               widget="date"
                               placeholder="Fecha estimada de arribo"/>
                        <field name="requires_eta" invisible="1"/>
                        <field name="telex_release_required" readonly="1"
                               invisible="not telex_release_required"/>
                    </group>
                </group>

                <!-- ── RESUMEN FINANCIERO ─────────────────────────────── -->
                <group string="💰 Resumen Financiero"
                       invisible="not is_import_order"
                       col="4">
                    <field name="advance_amount"    readonly="1" string="Anticipo"/>
                    <field name="balance_amount"    readonly="1" string="Saldo Pendiente"/>
                    <field name="next_payment_date" readonly="1" string="Próx. Vencimiento"/>
                    <field name="overdue_payments"  invisible="1"/>
                </group>

            </xpath>

            <!-- ── TAB DE IMPORTACIÓN ─────────────────────────────────── -->
            <xpath expr="//notebook" position="inside">
                <page string="🚢 Importación / Pagos"
                      invisible="not is_import_order"
                      name="import_tab">

                    <!-- ── CALENDARIO DE PAGOS ──────────────────────── -->
                    <separator string="📅 Calendario de Pagos"/>

                    <div class="d-flex align-items-center mb-2 gap-2">
                        <button name="action_calculate_payment_schedule"
                                string="🔄 Calcular / Recalcular Calendario"
                                type="object"
                                class="btn btn-primary btn-sm"/>
                        <span class="text-muted small ms-2">
                            Genera automáticamente los hitos de pago según las
                            condiciones del proveedor.
                        </span>
                    </div>

                    <field name="payment_schedule_ids" nolabel="1">
                        <list editable="bottom"
                              decoration-danger="state == 'overdue'"
                              decoration-success="state == 'paid'"
                              decoration-warning="state in ('pending', 'partial')">
                            <field name="payment_type"      string="Tipo de Pago"/>
                            <field name="percent"           string="% Porcentaje"/>
                            <field name="amount"            string="Monto"/>
                            <field name="currency_id"       column_invisible="1"/>
                            <field name="due_date"          string="Fecha Límite"/>
                            <field name="days_until_due"    string="Días Restantes" readonly="1"/>
                            <field name="state" widget="badge"
                                   string="Estado"
                                   decoration-success="state == 'paid'"
                                   decoration-info="state == 'partial'"
                                   decoration-danger="state == 'overdue'"
                                   decoration-warning="state == 'pending'"/>
                            <field name="paid_date"         optional="show" string="Fecha Pago"/>
                            <field name="paid_amount"       optional="show" string="Monto Pagado" readonly="1"/>
                            <field name="remaining_amount"  optional="show" string="Saldo" readonly="1"/>
                            <field name="payment_reference" string="Referencia"/>
                            <field name="is_manual" widget="boolean" string="Manual"/>
                            <field name="note"              string="Nota"/>
                            <button name="action_register_payment"
                                    string="💵 Pagar"
                                    type="object"
                                    class="btn btn-sm btn-success"
                                    invisible="state == 'paid'"/>
                            <button name="action_view_payments"
                                    string="Ver Pagos"
                                    type="object"
                                    class="btn btn-sm btn-secondary"
                                    invisible="not payment_ids"/>
                            <field name="payment_ids"       column_invisible="1"/>
                        </list>
                    </field>

                    <!-- ── CONTENEDORES ──────────────────────────────── -->
                    <separator string="🏗️ Contenedores"/>

                    <field name="container_ids" nolabel="1">
                        <list editable="bottom"
                              decoration-success="tax_state == 'paid'"
                              decoration-muted="tax_state == 'pending'">
                            <field name="name"          string="No. Contenedor"
                                   placeholder="TCKU1234567"/>
                            <field name="container_type" string="Tipo"/>
                            <field name="seal_number"   string="No. Sello"/>
                            <field name="pedimento"     string="Pedimento"/>
                            <field name="tax_amount"    string="Monto Impuesto"/>
                            <field name="currency_id"   column_invisible="1"/>
                            <field name="tax_state" widget="badge"
                                   string="Estado Impuesto"
                                   decoration-success="tax_state == 'paid'"
                                   decoration-warning="tax_state == 'pending'"/>
                            <field name="tax_paid_date" optional="hide" string="Fecha Pago Imp."/>
                            <field name="notes"         string="Notas"/>
                        </list>
                    </field>

                    <group string="📊 Resumen" col="2">
                        <field name="container_count"
                               string="Total de Contenedores"
                               readonly="1"/>
                    </group>

                </page>
            </xpath>

        </field>
    </record>

    <!-- ── Vista list de purchase.order ─────────────────────────────────── -->
    <record id="view_purchase_order_tree_somgroup" model="ir.ui.view">
        <field name="name">purchase.order.tree.somgroup</field>
        <field name="model">purchase.order</field>
        <field name="inherit_id" ref="purchase.purchase_order_tree"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='date_order']" position="after">
                <field name="bl_date"           optional="show"  string="Fecha BL"/>
                <field name="eta_date"          optional="show"  string="ETA"/>
                <field name="next_payment_date" optional="show"  string="Próx. Vcto."/>
                <field name="overdue_payments"  column_invisible="1"/>
            </xpath>
        </field>
    </record>

    <!-- ── Vista form standalone de purchase.payment.schedule ───────────── -->
    <record id="view_purchase_payment_schedule_form" model="ir.ui.view">
        <field name="name">purchase.payment.schedule.form</field>
        <field name="model">purchase.payment.schedule</field>
        <field name="arch" type="xml">
            <form string="Pago Programado">
                <header>
                    <button name="action_register_payment"
                            string="💵 Registrar Pago Contable"
                            type="object"
                            class="btn-primary"
                            invisible="state == 'paid'"/>
                    <button name="action_mark_paid"
                            string="✓ Marcar Pagado (Manual)"
                            type="object"
                            class="btn-secondary"
                            invisible="state == 'paid'"/>
                    <field name="state" widget="statusbar"
                           statusbar_visible="pending,partial,paid"/>
                </header>
                <sheet>
                    <div class="oe_button_box" name="button_box">
                        <button name="action_view_payments"
                                type="object"
                                class="oe_stat_button"
                                icon="fa-credit-card"
                                invisible="not payment_ids">
                            <field name="payment_ids" widget="statinfo" string="Pagos"/>
                        </button>
                    </div>

                    <div class="o_form_title mb-3">
                        <field name="order_id" readonly="1"/>
                    </div>

                    <!-- Sección 1: Identificación del pago -->
                    <separator string="Datos del Pago"/>
                    <group col="2">
                        <group string="¿Qué se paga?">
                            <field name="payment_type" string="Tipo de Pago"/>
                            <field name="percent"      string="Porcentaje (%)"/>
                            <field name="amount"       string="Monto a Pagar"/>
                            <field name="currency_id"  string="Moneda"/>
                            <field name="is_manual"    string="Entrada Manual"/>
                        </group>
                        <group string="¿Cuándo se paga?">
                            <field name="due_date"      string="Fecha Límite"/>
                            <field name="days_until_due" string="Días Restantes" readonly="1"/>
                        </group>
                    </group>

                    <!-- Sección 2: Estado contable -->
                    <separator string="Estado Contable"/>
                    <group col="2">
                        <group string="Montos">
                            <field name="paid_amount"        string="Monto Pagado (Contable)" readonly="1"/>
                            <field name="remaining_amount"   string="Saldo Restante" readonly="1"/>
                            <field name="paid_date"          string="Fecha de Pago"/>
                            <field name="payment_reference"  string="Referencia / Folio"/>
                        </group>
                        <group string="Notas Adicionales">
                            <field name="note" nolabel="1"
                                   placeholder="Escribe aquí cualquier observación..."
                                   widget="text"/>
                        </group>
                    </group>

                    <!-- Sección 3: Pagos contables vinculados -->
                    <separator string="Pagos Contables Vinculados" invisible="not payment_ids"/>
                    <field name="payment_ids" readonly="1" invisible="not payment_ids">
                        <list>
                            <field name="name"          string="Referencia"/>
                            <field name="date"          string="Fecha"/>
                            <field name="amount"        string="Monto"/>
                            <field name="currency_id"/>
                            <field name="state" widget="badge"
                                   decoration-success="state == 'posted'"
                                   decoration-warning="state == 'draft'"
                                   decoration-danger="state == 'cancel'"/>
                        </list>
                    </field>
                </sheet>
            </form>
        </field>
    </record>

    <!-- ── Vista list de payment schedule ───────────────────────────────── -->
    <record id="view_purchase_payment_schedule_tree" model="ir.ui.view">
        <field name="name">purchase.payment.schedule.tree</field>
        <field name="model">purchase.payment.schedule</field>
        <field name="arch" type="xml">
            <list string="Calendario de Pagos"
                  decoration-danger="state == 'overdue'"
                  decoration-success="state == 'paid'"
                  decoration-info="state == 'partial'"
                  decoration-warning="state == 'pending'">
                <field name="order_id"          string="Orden de Compra"/>
                <field name="payment_type"      string="Tipo"/>
                <field name="percent"           string="%"/>
                <field name="amount"            string="Monto"/>
                <field name="currency_id"/>
                <field name="due_date"          string="Fecha Límite"/>
                <field name="days_until_due"    string="Días"/>
                <field name="state" widget="badge"
                       decoration-success="state == 'paid'"
                       decoration-info="state == 'partial'"
                       decoration-danger="state == 'overdue'"
                       decoration-warning="state == 'pending'"/>
                <field name="paid_date"         string="Fecha Pago"/>
                <field name="paid_amount"       string="Pagado" readonly="1"/>
                <field name="remaining_amount"  string="Saldo" readonly="1"/>
                <field name="payment_reference" string="Referencia"/>
                <field name="is_manual"         string="Manual"/>
                <field name="note"              string="Nota"/>
                <button name="action_register_payment"
                        string="💵 Pagar"
                        type="object"
                        class="btn btn-sm btn-success"
                        title="Registrar Pago Contable"
                        invisible="state == 'paid'"/>
            </list>
        </field>
    </record>

    <!-- ── Vista Calendar de payment schedule ───────────────────────────── -->
    <record id="view_purchase_payment_schedule_calendar" model="ir.ui.view">
        <field name="name">purchase.payment.schedule.calendar</field>
        <field name="model">purchase.payment.schedule</field>
        <field name="arch" type="xml">
            <calendar string="Calendario de Pagos"
                      date_start="due_date"
                      color="state"
                      quick_create="false"
                      event_limit="5">
                <field name="order_id"     filters="1"/>
                <field name="payment_type" filters="1"/>
                <field name="amount"       string="Monto"/>
                <field name="state"        string="Estado"/>
            </calendar>
        </field>
    </record>

    <!-- ── Vista Gantt de payment schedule ──────────────────────────────── -->
    <record id="view_purchase_payment_schedule_gantt" model="ir.ui.view">
        <field name="name">purchase.payment.schedule.gantt</field>
        <field name="model">purchase.payment.schedule</field>
        <field name="arch" type="xml">
            <gantt string="Gantt de Pagos"
                   date_start="due_date"
                   date_stop="due_date"
                   color="state"
                   default_group_by="order_id"
                   pill_label="true"
                   plan="false"
                   precision="{'day': 'day:half', 'week': 'day:half', 'month': 'day:half'}">
                <field name="order_id"/>
                <field name="payment_type"/>
                <field name="amount"/>
                <field name="state"/>
                <field name="due_date"/>
            </gantt>
        </field>
    </record>


    <record id="view_purchase_payment_schedule_search" model="ir.ui.view">
        <field name="name">purchase.payment.schedule.search</field>
        <field name="model">purchase.payment.schedule</field>
        <field name="arch" type="xml">
            <search string="Buscar Pagos">
                <field name="order_id"/>
                <field name="due_date"/>
                <filter string="Pendientes"        name="pending"     domain="[('state','=','pending')]"/>
                <filter string="Pago Parcial"      name="partial"     domain="[('state','=','partial')]"/>
                <filter string="Vencidos"          name="overdue"     domain="[('state','=','overdue')]"/>
                <filter string="Pagados"           name="paid"        domain="[('state','=','paid')]"/>
                <filter string="Vence esta semana" name="due_week"
                        domain="[
                            ('due_date', '!=', False),
                            ('due_date', '&gt;=', context_today().strftime('%Y-%m-%d')),
                            ('state', 'in', ['pending', 'partial'])
                        ]"/>
                <filter string="Manuales"          name="manual"      domain="[('is_manual','=',True)]"/>
                <separator/>
                <filter string="Por Proveedor"     name="group_partner" context="{'group_by': 'order_id'}"/>
                <filter string="Por Tipo"          name="group_type"    context="{'group_by': 'payment_type'}"/>
                <filter string="Por Estado"        name="group_state"   context="{'group_by': 'state'}"/>
                <filter string="Por Mes"           name="group_month"   context="{'group_by': 'due_date:month'}"/>
            </search>
        </field>
    </record>

    <!-- ── Acción / Menú Calendario de Pagos ────────────────────────────── -->
    <record id="action_purchase_payment_schedule" model="ir.actions.act_window">
        <field name="name">Calendario de Pagos — Importaciones</field>
        <field name="res_model">purchase.payment.schedule</field>
        <field name="view_mode">list,calendar,gantt,form</field>
        <field name="context">{'search_default_pending': 1}</field>
        <field name="help" type="html">
            <p class="o_view_nocontent_smiling_face">
                No hay pagos programados.
            </p>
            <p>Marca una Orden de Compra como "¿Es Orden de Importación?" y presiona
               "Calcular Calendario" para generar los compromisos de pago.</p>
        </field>
    </record>

    <menuitem id="menu_purchase_payment_schedule"
              name="Calendario de Pagos"
              parent="purchase.menu_purchase_root"
              action="action_purchase_payment_schedule"
              sequence="25"/>

</odoo>```

