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
        related='payment_term_id.requires_bl_date',
        string='Requiere Fecha BL',
        readonly=True
    )
    requires_eta = fields.Boolean(
        related='payment_term_id.requires_eta',
        string='Requiere ETA',
        readonly=True
    )
    is_import_order = fields.Boolean(
        string='Es Orden de Importación',
        default=False,
        help="Activa los campos de BL, ETA y calendario de pagos de importación"
    )
    telex_release_required = fields.Boolean(
        string='Requiere Telex Release',
        compute='_compute_telex_release',
        store=True,
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
    def _compute_telex_release(self):
        manual_types = ['against_delivery', 'advance_balance', 'advance_days_arrival']
        for rec in self:
            rec.telex_release_required = (
                rec.payment_term_id and
                rec.payment_term_id.somgroup_term_type in manual_types
            )

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
        """Recalcula el calendario de pagos al cambiar término, BL o ETA."""
        if not self.is_import_order or not self.payment_term_id:
            return
        if self.payment_term_id.somgroup_term_type == 'standard':
            return
        # Solo aviso — el cálculo real se hace al confirmar o con el botón
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
        """Botón: Calcular / Recalcular calendario de pagos."""
        for order in self:
            if not order.payment_term_id:
                raise UserError(_('Seleccione un término de pago antes de calcular.'))
            if order.payment_term_id.somgroup_term_type == 'standard':
                raise UserError(_('Este término usa el motor estándar de Odoo. El calendario se gestiona en las facturas.'))
            order._recalculate_payment_schedule()

    def _recalculate_payment_schedule(self):
        """Elimina y recrea las líneas del calendario de pagos."""
        self.ensure_one()
        # Borrar pendientes (no borrar los ya pagados)
        pending = self.payment_schedule_ids.filtered(lambda l: l.state == 'pending')
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
        # Recalcular si cambia BL o ETA en órdenes de importación
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
    """Contenedores asociados a una orden de compra/importación."""
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
    """Calendario de pagos calculado para una orden de importación."""
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
    state = fields.Selection([
        ('pending', 'Pendiente'),
        ('paid', 'Pagado'),
        ('overdue', 'Vencido'),
    ], string='Estado', default='pending', tracking=True)
    paid_date = fields.Date(string='Fecha Pago Real')
    paid_amount = fields.Monetary(string='Monto Pagado', currency_field='currency_id')
    remaining_amount = fields.Monetary(
        string='Saldo Pendiente',
        compute='_compute_remaining',
        store=True,
        currency_field='currency_id'
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

    @api.depends('amount', 'paid_amount')
    def _compute_remaining(self):
        for rec in self:
            rec.remaining_amount = (rec.amount or 0.0) - (rec.paid_amount or 0.0)

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
                    rec.alert_color = 'red'   # Vencido
                elif delta <= 7:
                    rec.alert_color = 'orange'  # Próximo a vencer
                else:
                    rec.alert_color = 'gray'   # Sin alerta
            else:
                rec.days_until_due = 0
                rec.alert_color = 'blue'  # Manual / sin fecha

    def action_mark_paid(self):
        """Marcar como pagado desde el calendario."""
        from datetime import date
        for rec in self:
            rec.write({
                'state': 'paid',
                'paid_date': rec.paid_date or date.today(),
                'paid_amount': rec.paid_amount or rec.amount,
            })

    def action_mark_overdue(self):
        from datetime import date
        today = date.today()
        pending = self.search([
            ('state', '=', 'pending'),
            ('due_date', '<', today),
            ('due_date', '!=', False),
        ])
        pending.write({'state': 'overdue'})
        return {'type': 'ir.actions.client', 'tag': 'reload'}
