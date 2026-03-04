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

    # ── Estado y montos — campos regulares (sin compute) ─────────────────────
    # IMPORTANTE: No usar compute+store aquí porque _recompute_from_payments_by_order
    # escribe directamente y los computes asíncronos pisarían los valores calculados.
    state = fields.Selection([
        ('pending', 'Pendiente'),
        ('partial', 'Pago Parcial'),
        ('paid', 'Pagado'),
        ('overdue', 'Vencido'),
    ], string='Estado', default='pending', store=True, tracking=True)

    paid_amount = fields.Monetary(
        string='Monto Pagado',
        store=True,
        default=0.0,
        currency_field='currency_id',
    )
    remaining_amount = fields.Monetary(
        string='Saldo Pendiente',
        store=True,
        default=0.0,
        currency_field='currency_id',
    )
    paid_date = fields.Date(
        string='Fecha Pago Real',
        store=True,
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

    # ─── Compute días restantes (no conflictivo, no store) ───────────────────

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

    # ─── Helper interno ──────────────────────────────────────────────────────

    def _resolve_state(self, paid_amount, amount, due_date):
        from datetime import date
        today = date.today()
        if paid_amount and paid_amount >= (amount - 0.01):
            return 'paid'
        elif paid_amount and paid_amount > 0:
            return 'partial'
        elif due_date and due_date < today:
            return 'overdue'
        return 'pending'

    # ─── Métodos de recálculo desde contabilidad ─────────────────────────────

    def _recompute_from_payments(self):
        """Punto de entrada unificado."""
        self._recompute_from_payments_by_order()

    def _recompute_from_payments_by_order(self):
        """
        Busca todos los pagos posted vinculados a facturas de la OC via
        conciliaciones contables y escribe directamente los campos de estado.
        """
        from datetime import date

        orders = self.mapped('order_id')
        for order in orders:
            order_schedules = self.filtered(lambda s: s.order_id == order).sorted(
                key=lambda s: (s.due_date or date.max)
            )
            if not order_schedules:
                continue

            # ── Recolectar pagos via conciliaciones ───────────────────────
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

            # Pagos directamente vinculados vía purchase_schedule_id
            direct_payments = self.env['account.payment'].search([
                ('purchase_schedule_id', 'in', order_schedules.ids),
                ('state', '=', 'posted'),
            ])
            all_payments |= direct_payments

            remaining_to_distribute = sum(all_payments.mapped('amount'))

            # ── Distribuir cronológicamente ───────────────────────────────
            for schedule in order_schedules:
                direct = direct_payments.filtered(
                    lambda p: p.purchase_schedule_id == schedule
                )
                direct_amount = sum(direct.mapped('amount'))

                if direct_amount > 0:
                    schedule_paid = min(direct_amount, schedule.amount)
                    remaining_to_distribute = max(0.0, remaining_to_distribute - direct_amount)
                elif remaining_to_distribute > 0:
                    schedule_paid = min(remaining_to_distribute, schedule.amount)
                    remaining_to_distribute -= schedule_paid
                else:
                    schedule_paid = 0.0

                if direct:
                    paid_date = direct.sorted('date')[-1].date
                elif schedule_paid > 0 and all_payments:
                    paid_date = all_payments.sorted('date')[-1].date
                else:
                    paid_date = schedule.paid_date

                new_state = self._resolve_state(schedule_paid, schedule.amount, schedule.due_date)

                vals = {
                    'paid_amount': schedule_paid,
                    'remaining_amount': max(0.0, (schedule.amount or 0.0) - schedule_paid),
                    'state': new_state,
                }
                if paid_date:
                    vals['paid_date'] = paid_date

                # sudo() para evitar bloqueos de acceso en contextos de pago
                schedule.sudo().write(vals)

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

    # ─── Acción legacy: Marcar pagado manualmente ────────────────────────────

    def action_mark_paid(self):
        from datetime import date
        for rec in self:
            if rec.state != 'paid':
                rec.write({
                    'paid_amount': rec.amount,
                    'remaining_amount': 0.0,
                    'paid_date': rec.paid_date or date.today(),
                    'state': 'paid',
                })

    def action_mark_overdue(self):
        from datetime import date
        today = date.today()
        pending = self.search([
            ('state', 'in', ['pending', 'partial']),
            ('due_date', '<', today),
            ('due_date', '!=', False),
        ])
        for rec in pending:
            rec.write({'state': 'overdue'})
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    # ─── Acción: Forzar sincronización manual ────────────────────────────────

    def action_sync_from_accounting(self):
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
        }