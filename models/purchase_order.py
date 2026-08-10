# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare
import logging

_logger = logging.getLogger(__name__)

POSTED_STATES = ('posted', 'in_process', 'paid')


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    purchase_payment_scope = fields.Selection([
        ('import', 'Importación'),
        ('national', 'Nacional'),
    ], string='Tipo de Compra',
       compute='_compute_purchase_payment_scope',
       inverse='_inverse_purchase_payment_scope',
       store=True,
       readonly=False,
       help='Clasificación SOMGROUP para separar compras de importación y compras nacionales.')

    is_import_order = fields.Boolean(
        string='Es Orden de Importación',
        default=False,
    )

    is_national_order = fields.Boolean(
        string='Es Compra Nacional',
        compute='_compute_is_national_order',
        store=False,
    )

    bl_date = fields.Date(string='Fecha BL')
    bl_number = fields.Char(string='Número BL')
    eta_date = fields.Date(string='ETA')

    supplier_invoice_date = fields.Date(
        string='Fecha Factura Proveedor',
        help='Fecha de factura del proveedor para compras nacionales.'
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
       help='Base usada para calcular vencimientos en compras nacionales.')

    national_expected_receipt_date = fields.Date(
        string='Recepción Esperada',
        help='Fecha estimada de entrega/recepción para compras nacionales.'
    )

    national_receipt_date = fields.Date(
        string='Recepción Real / Entrega',
        help='Fecha real de recepción o entrega para compras nacionales.'
    )

    national_reference_date = fields.Date(
        string='Fecha Referencia Nacional',
        help='Fecha manual usada cuando el término nacional se calcula desde una referencia especial.'
    )

    national_payment_note = fields.Char(
        string='Nota Pago Nacional',
        help='Observación operativa para pagos de compra nacional.'
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

    payment_schedule_ids = fields.One2many(
        'purchase.payment.schedule',
        'order_id',
        string='Calendario de Pagos'
    )

    payment_schedule_warning = fields.Char(
        string='Aviso de Pago',
        compute='_compute_payment_warning',
        store=False
    )

    requires_bl_date = fields.Boolean(
        compute='_compute_term_flags',
        store=False
    )

    requires_eta = fields.Boolean(
        compute='_compute_term_flags',
        store=False
    )

    requires_supplier_invoice_date = fields.Boolean(
        compute='_compute_term_flags',
        store=False
    )

    requires_national_receipt_date = fields.Boolean(
        compute='_compute_term_flags',
        store=False
    )

    requires_national_reference_date = fields.Boolean(
        compute='_compute_term_flags',
        store=False
    )

    telex_release_required = fields.Boolean(
        compute='_compute_term_flags',
        store=False
    )

    advance_amount = fields.Monetary(
        string='Monto Anticipo',
        compute='_compute_advance_amount',
        store=False,
        currency_field='currency_id'
    )

    balance_amount = fields.Monetary(
        string='Monto Balance',
        compute='_compute_advance_amount',
        store=False,
        currency_field='currency_id'
    )

    next_payment_date = fields.Date(
        compute='_compute_next_payment_date',
        store=False
    )

    overdue_payments = fields.Boolean(
        compute='_compute_next_payment_date',
        store=False
    )

    @api.depends('is_import_order')
    def _compute_purchase_payment_scope(self):
        for rec in self:
            rec.purchase_payment_scope = 'import' if rec.is_import_order else 'national'

    def _inverse_purchase_payment_scope(self):
        for rec in self:
            rec.is_import_order = rec.purchase_payment_scope == 'import'

    @api.depends('purchase_payment_scope')
    def _compute_is_national_order(self):
        for rec in self:
            rec.is_national_order = rec.purchase_payment_scope == 'national'

    @api.depends('container_ids')
    def _compute_container_count(self):
        for rec in self:
            rec.container_count = len(rec.container_ids)

    def _get_order_date(self):
        self.ensure_one()
        if self.date_order:
            return fields.Date.to_date(self.date_order)
        return fields.Date.today()

    def _get_national_base_label(self, base=None):
        labels = dict(self._fields['national_due_base'].selection)
        return labels.get(base or self.national_due_base or 'supplier_invoice_date')

    def _get_national_base_date(self, base=None):
        self.ensure_one()

        base = base or self.national_due_base or 'supplier_invoice_date'

        if base == 'order_date':
            return self._get_order_date()

        if base == 'confirmation_date':
            if 'date_approve' in self._fields and self.date_approve:
                return fields.Date.to_date(self.date_approve)
            return self._get_order_date()

        if base == 'supplier_invoice_date':
            if self.supplier_invoice_date:
                return self.supplier_invoice_date
            if 'effective_date' in self._fields and self.effective_date:
                return self.effective_date
            return False

        if base == 'expected_receipt_date':
            return self.national_expected_receipt_date

        if base == 'receipt_date':
            return self.national_receipt_date or self.national_expected_receipt_date

        if base == 'manual_date':
            return self.national_reference_date

        return False

    def _get_missing_national_base_label(self, base=None):
        self.ensure_one()
        base = base or self.national_due_base or 'supplier_invoice_date'
        if self._get_national_base_date(base):
            return False
        return self._get_national_base_label(base)

    @api.depends(
        'purchase_payment_scope',
        'payment_term_id',
        'payment_term_id.somgroup_term_type',
        'payment_term_id.national_due_base',
        'national_due_base',
    )
    def _compute_term_flags(self):
        for rec in self:
            term = rec.payment_term_id
            term_type = term.somgroup_term_type if term else False
            scope = rec.purchase_payment_scope or ('import' if rec.is_import_order else 'national')

            rec.requires_bl_date = False
            rec.requires_eta = False
            rec.requires_supplier_invoice_date = False
            rec.requires_national_receipt_date = False
            rec.requires_national_reference_date = False
            rec.telex_release_required = False

            if not term or term_type == 'standard':
                continue

            if scope == 'import':
                rec.requires_bl_date = term_type in ['days_after_bl']
                rec.requires_eta = term_type in [
                    'against_delivery',
                    'advance_balance',
                    'advance_days_arrival',
                ]
                rec.telex_release_required = term_type in [
                    'against_delivery',
                    'advance_balance',
                    'advance_days_arrival',
                ]
                continue

            if scope == 'national':
                base = rec.national_due_base or term.national_due_base or 'supplier_invoice_date'
                uses_base = term_type in ['national_days_after_base', 'national_advance_balance']

                rec.requires_supplier_invoice_date = (
                    uses_base and base == 'supplier_invoice_date'
                )

                rec.requires_national_reference_date = (
                    uses_base and base == 'manual_date'
                )

                rec.requires_national_receipt_date = (
                    term_type == 'national_against_receipt'
                    or (
                        uses_base
                        and base in ['expected_receipt_date', 'receipt_date']
                    )
                )

    @api.depends(
        'payment_schedule_ids',
        'payment_schedule_ids.amount',
        'payment_schedule_ids.payment_type'
    )
    def _compute_advance_amount(self):
        for rec in self:
            advances = rec.payment_schedule_ids.filtered(
                lambda l: l.payment_type in ('advance', 'second_advance')
            )
            balances = rec.payment_schedule_ids.filtered(
                lambda l: l.payment_type == 'balance'
            )
            rec.advance_amount = sum(advances.mapped('amount'))
            rec.balance_amount = sum(balances.mapped('amount'))

    @api.depends(
        'payment_schedule_ids',
        'payment_schedule_ids.due_date',
        'payment_schedule_ids.state'
    )
    def _compute_next_payment_date(self):
        from datetime import date

        today = date.today()

        for rec in self:
            pending = rec.payment_schedule_ids.filtered(
                lambda l: l.state == 'pending' and l.due_date
            )
            overdue = pending.filtered(lambda l: l.due_date < today)

            rec.overdue_payments = bool(overdue)

            upcoming = pending.filtered(lambda l: l.due_date >= today)
            rec.next_payment_date = min(upcoming.mapped('due_date')) if upcoming else False

    @api.depends(
        'purchase_payment_scope',
        'payment_term_id',
        'payment_term_id.somgroup_term_type',
        'payment_term_id.national_due_base',
        'bl_date',
        'eta_date',
        'supplier_invoice_date',
        'national_due_base',
        'national_expected_receipt_date',
        'national_receipt_date',
        'national_reference_date',
        'payment_schedule_ids',
        'payment_schedule_ids.due_date',
        'payment_schedule_ids.state'
    )
    def _compute_payment_warning(self):
        from datetime import date, timedelta

        today = date.today()

        for rec in self:
            warnings = []
            term = rec.payment_term_id
            term_type = term.somgroup_term_type if term else False
            scope = rec.purchase_payment_scope or ('import' if rec.is_import_order else 'national')

            if term and term_type != 'standard':
                if scope == 'import':
                    if rec.requires_bl_date and not rec.bl_date:
                        warnings.append('⚠ Ingrese Fecha BL para calcular vencimientos automáticamente.')
                    if rec.requires_eta and not rec.eta_date:
                        warnings.append('⚠ Ingrese ETA para programar pagos contra entrega / Telex Release.')

                elif scope == 'national':
                    if term_type in ['national_days_after_base', 'national_advance_balance']:
                        base = rec.national_due_base or term.national_due_base or 'supplier_invoice_date'
                        missing_label = rec._get_missing_national_base_label(base)
                        if missing_label:
                            warnings.append(
                                f'⚠ Capture {missing_label} para calcular vencimientos nacionales.'
                            )

                    if term_type == 'national_against_receipt':
                        if not rec.national_receipt_date and not rec.national_expected_receipt_date:
                            warnings.append(
                                '⚠ Capture recepción esperada o recepción real para programar pago contra entrega.'
                            )

            if rec.overdue_payments:
                warnings.append('🔴 VENCIDO: Hay pagos vencidos en este pedido.')
            else:
                upcoming = rec.payment_schedule_ids.filtered(
                    lambda l: l.state == 'pending'
                    and l.due_date
                    and today <= l.due_date <= today + timedelta(days=7)
                )
                if upcoming:
                    warnings.append(f'🟡 Vence en 7 días: {upcoming[0].due_date}')

            rec.payment_schedule_warning = ' | '.join(warnings) if warnings else ''

    @api.onchange('purchase_payment_scope')
    def _onchange_purchase_payment_scope(self):
        for rec in self:
            rec.is_import_order = rec.purchase_payment_scope == 'import'

    @api.onchange('payment_schedule_ids', 'amount_total')
    def _onchange_som_autobalance_payment_schedule(self):
        """El BALANCE se cuadra solo.

        Al ajustar % o monto de cualquier tramo (anticipo/segundo tramo) —
        p. ej. se pagó de más o de menos — la línea Balance/Liquidación NO
        pagada absorbe el remanente: su monto y su % se recalculan para que
        el calendario siempre cierre contra el total de la orden.
        """
        total = self.amount_total or 0.0
        if not total or not self.payment_schedule_ids:
            return
        balances = self.payment_schedule_ids.filtered(
            lambda l: l.payment_type == 'balance' and l.state != 'paid')
        if not balances:
            return
        target = balances[-1]
        others = self.payment_schedule_ids - target
        remaining = max(0.0, total - sum(others.mapped('amount')))
        target.amount = self.currency_id.round(remaining) \
            if self.currency_id else remaining
        target.percent = round(remaining / total * 100.0, 2)

    @api.onchange('payment_term_id', 'purchase_payment_scope')
    def _onchange_payment_term_defaults(self):
        for rec in self:
            term = rec.payment_term_id
            if (
                rec.purchase_payment_scope == 'national'
                and term
                and term.somgroup_term_type in ['national_days_after_base', 'national_advance_balance']
                and term.national_due_base
            ):
                rec.national_due_base = term.national_due_base

    @api.onchange(
        'purchase_payment_scope',
        'payment_term_id',
        'bl_date',
        'eta_date',
        'supplier_invoice_date',
        'national_due_base',
        'national_expected_receipt_date',
        'national_receipt_date',
        'national_reference_date',
        'amount_total',
    )
    def _onchange_recalculate_schedule(self):
        if not self.payment_term_id:
            return

        if self.payment_term_id.somgroup_term_type == 'standard':
            return

        term_type = self.payment_term_id.somgroup_term_type
        scope = self.purchase_payment_scope or ('import' if self.is_import_order else 'national')

        if scope == 'import':
            if term_type in ['days_after_bl'] and not self.bl_date:
                return {
                    'warning': {
                        'title': _('Fecha BL requerida'),
                        'message': _('El término "%s" requiere Fecha BL.') % self.payment_term_id.name,
                    }
                }

            if term_type in ['against_delivery', 'advance_balance', 'advance_days_arrival'] and not self.eta_date:
                return {
                    'warning': {
                        'title': _('ETA recomendada'),
                        'message': _(
                            'El término "%s" usa ETA para programar pagos contra entrega / Telex Release.'
                        ) % self.payment_term_id.name,
                    }
                }

        if scope == 'national':
            if term_type in ['national_days_after_base', 'national_advance_balance']:
                base = self.national_due_base or self.payment_term_id.national_due_base or 'supplier_invoice_date'
                missing_label = self._get_missing_national_base_label(base)
                if missing_label:
                    return {
                        'warning': {
                            'title': _('Fecha base nacional requerida'),
                            'message': _(
                                'El término "%s" requiere capturar: %s.'
                            ) % (self.payment_term_id.name, missing_label),
                        }
                    }

            if term_type == 'national_against_receipt':
                if not self.national_receipt_date and not self.national_expected_receipt_date:
                    return {
                        'warning': {
                            'title': _('Recepción requerida'),
                            'message': _(
                                'El término "%s" requiere recepción esperada o recepción real.'
                            ) % self.payment_term_id.name,
                        }
                    }

    def button_cancel(self):
        """Al cancelar la OC, los hitos limpios (sin pago/factura) se eliminan
        para que no queden 'por pagar' de una compra cancelada. Los hitos con
        pagos/facturas se conservan como historial (y el dashboard ya filtra
        OCs canceladas)."""
        res = super().button_cancel()
        for order in self:
            clean = order.payment_schedule_ids.filtered(
                lambda s: not s.payment_ids
                and not s.schedule_invoice_id
                and not s.advance_payment_id
            )
            if clean:
                clean.unlink()
        return res

    def action_calculate_payment_schedule(self):
        for order in self:
            if not order.payment_term_id:
                raise UserError(_('Seleccione un término de pago antes de calcular.'))

            if order.payment_term_id.somgroup_term_type == 'standard':
                raise UserError(_('Este término usa el motor estándar de Odoo.'))

            order._recalculate_payment_schedule()

    def _recalculate_payment_schedule(self):
        self.ensure_one()

        # GUARD ANTES de borrar: si ya hay hitos comprometidos (pago/factura),
        # recalcular borraría los hitos limpios (p. ej. el saldo del 70%) y el
        # return de abajo impediría regenerarlos — el saldo por pagar
        # desaparecía del calendario en silencio.
        committed = self.payment_schedule_ids.filtered(
            lambda l: l.payment_ids or l.schedule_invoice_id or l.advance_payment_id
        )
        if committed:
            raise UserError(_(
                'La OC %(order)s ya tiene hitos con pagos o facturas vinculados '
                '(%(names)s). No se puede recalcular el calendario automáticamente: '
                'ajusta los hitos pendientes de forma manual.'
            ) % {
                'order': self.name,
                'names': ', '.join(committed.mapped('display_name')),
            })

        pending_clean = self.payment_schedule_ids.filtered(
            lambda l: l.state == 'pending'
            and not l.payment_ids
            and not l.schedule_invoice_id
            and not l.advance_payment_id
        )
        pending_clean.unlink()

        if self.payment_schedule_ids:
            _logger.info(
                '[SOMGROUP] OC %s ya tiene hitos con factura/pago, omitiendo recalculo.',
                self.name
            )
            return

        vals_list = [{
            'order_id': self.id,
            'payment_type': l['type'],
            'percent': l['percent'],
            'amount': l['amount'],
            'due_date': l['due_date'],
            'note': l['note'],
            'is_manual': l['is_manual'],
            'state': 'pending',
        } for l in self.payment_term_id.compute_due_dates(self)]

        if vals_list:
            self.env['purchase.payment.schedule'].create(vals_list)

    @api.model_create_multi
    def create(self, vals_list):
        records = super(PurchaseOrder, self).create(vals_list)
        
        # SINCRONIZACIÓN AUTOMÁTICA AL CREAR
        if not self.env.context.get('skip_date_sync'):
            for record in records:
                sync_fields = {'bl_date', 'bl_number', 'eta_date'}
                # Si en la creación venía alguno de los campos clave
                if any(field in self.env.context.get('default_vals', {}) or field in record for field in sync_fields):
                    record._sync_dates_to_others({'bl_date': record.bl_date, 'bl_number': record.bl_number, 'eta_date': record.eta_date})
                    
        return records

    def write(self, vals):
        res = super().write(vals)

        # ---------------------------------------------------------
        # SINCRONIZACIÓN BIDIRECCIONAL A TORRE DE CONTROL Y PORTAL
        # ---------------------------------------------------------
        if not self.env.context.get('skip_date_sync'):
            sync_fields = {'bl_date', 'bl_number', 'eta_date'}
            if sync_fields.intersection(vals.keys()):
                for order in self:
                    order._sync_dates_to_others(vals)

        # ---------------------------------------------------------
        # LÓGICA DE RECALCULO DE PAGOS SOMGROUP
        # ---------------------------------------------------------
        trigger_fields = {
            'purchase_payment_scope',
            'is_import_order',
            'bl_date',
            'eta_date',
            'payment_term_id',
            'supplier_invoice_date',
            'national_due_base',
            'national_expected_receipt_date',
            'national_receipt_date',
            'national_reference_date',
            # Editar líneas cambia amount_total: sin esto, agregar un
            # contenedor a la OC dejaba los hitos con montos viejos en
            # silencio (el anticipo se pagaba sobre el total anterior).
            'order_line',
        }

        if trigger_fields.intersection(vals.keys()):
            for order in self.filtered(
                lambda o: o.payment_term_id
                and o.payment_term_id.somgroup_term_type != 'standard'
            ):
                has_committed = any(
                    s.schedule_invoice_id or s.payment_ids or s.advance_payment_id
                    for s in order.payment_schedule_ids
                )
                if not has_committed:
                    order._recalculate_payment_schedule()
                elif 'order_line' in vals:
                    # Hay pagos/facturas: no se recalcula solo, pero el
                    # cambio de montos ya NO pasa desapercibido.
                    order.message_post(body=_(
                        '⚠ Se modificaron las líneas de la OC pero el calendario '
                        'de pagos tiene hitos con pagos/facturas y NO se recalculó. '
                        'Revisa y ajusta los hitos pendientes manualmente.'
                    ))

        return res

    def _sync_dates_to_others(self, vals):
        """Helper para sincronizar fechas logísticas con Torre de Control y Portal Proveedor"""
        for order in self:
            # Sincronizar hacia Torre de Control (Viaje)
            if 'stock.transit.voyage' in self.env.registry:
                voyages = self.env['stock.transit.voyage'].sudo().search([('purchase_id', '=', order.id)])
                v_vals = {}
                if 'bl_number' in vals: v_vals['bl_number'] = vals['bl_number']
                if 'eta_date' in vals: v_vals['eta'] = vals['eta_date']
                if v_vals:
                    voyages.with_context(skip_date_sync=True).write(v_vals)

            # Sincronizar hacia Portal (Embarque)
            if 'supplier.shipment' in self.env.registry:
                shipments = self.env['supplier.shipment'].sudo().search([('purchase_id', '=', order.id)])
                s_vals = {}
                if 'bl_number' in vals: s_vals['bl_number'] = vals['bl_number']
                if 'bl_date' in vals: s_vals['bl_date'] = vals['bl_date']
                if 'eta_date' in vals: s_vals['eta'] = vals['eta_date']
                if s_vals:
                    shipments.with_context(skip_date_sync=True).write(s_vals)


class PurchaseOrderContainer(models.Model):
    _name = 'purchase.order.container'
    _description = 'Contenedor de Importación'
    _order = 'order_id, name'

    order_id = fields.Many2one(
        'purchase.order',
        string='Orden de Compra',
        ondelete='cascade',
        required=True
    )

    purchase_payment_scope = fields.Selection(
        related='order_id.purchase_payment_scope',
        store=True,
        readonly=True,
        string='Tipo de Compra'
    )

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
    _description = 'Calendario de Pagos - Compras SOMGROUP'
    _order = 'due_date asc, id asc'
    _rec_name = 'display_name_computed'

    display_name_computed = fields.Char(
        string='Nombre',
        compute='_compute_display_name_computed',
        store=False
    )

    order_id = fields.Many2one(
        'purchase.order',
        string='Orden de Compra',
        ondelete='cascade',
        required=True
    )

    purchase_payment_scope = fields.Selection(
        related='order_id.purchase_payment_scope',
        store=True,
        readonly=True,
        string='Tipo de Compra'
    )

    partner_id = fields.Many2one(
        related='order_id.partner_id',
        store=True,
        readonly=True,
        string='Proveedor'
    )

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

    @api.depends('order_id.name', 'payment_type', 'amount', 'currency_id', 'percent')
    def _compute_display_name_computed(self):
        type_labels = dict(self._fields['payment_type'].selection)

        for rec in self:
            parts = []

            if rec.order_id:
                parts.append(rec.order_id.name or '')

            if rec.payment_type:
                parts.append(type_labels.get(rec.payment_type, ''))

            if rec.amount:
                currency = rec.currency_id.symbol if rec.currency_id else '$'
                parts.append('{}{:,.2f}'.format(currency, rec.amount))

            if rec.percent:
                parts.append('({}%)'.format(int(rec.percent)))

            rec.display_name_computed = ' — '.join(parts) if parts else 'Pago'

    payment_ids = fields.One2many(
        'account.payment',
        'purchase_schedule_id',
        string='Pagos Contables',
        readonly=True
    )

    advance_payment_id = fields.Many2one(
        'account.payment',
        string='Pago de Anticipo',
        readonly=True,
        ondelete='set null',
    )

    schedule_invoice_id = fields.Many2one(
        'account.move',
        string='Factura del Hito',
        readonly=True,
        ondelete='set null',
    )

    state = fields.Selection([
        ('pending', 'Pendiente'),
        ('partial', 'Pago Parcial'),
        ('paid', 'Pagado'),
        ('overdue', 'Vencido'),
    ], string='Estado', default='pending', store=True)

    paid_amount = fields.Monetary(
        string='Monto Pagado',
        store=True,
        default=0.0,
        currency_field='currency_id'
    )

    remaining_amount = fields.Monetary(
        string='Saldo Pendiente',
        store=True,
        default=0.0,
        currency_field='currency_id'
    )

    paid_date = fields.Date(string='Fecha Pago Real', store=True)

    # ── Sincronía % ⇄ monto: el usuario NUNCA calcula a mano ──────────────
    # Capturas % → se calcula el monto; ajustas el monto (pagaste de más o
    # de menos) → se recalcula el %. El cuadre de la línea Balance lo hace
    # _onchange_som_autobalance_payment_schedule en la orden.
    @api.onchange('percent')
    def _onchange_som_percent_sync_amount(self):
        total = self.order_id.amount_total or 0.0
        if total and self.state != 'paid':
            currency = self.currency_id or self.order_id.currency_id
            amount = total * (self.percent or 0.0) / 100.0
            self.amount = currency.round(amount) if currency else amount

    @api.onchange('amount')
    def _onchange_som_amount_sync_percent(self):
        total = self.order_id.amount_total or 0.0
        if total and self.state != 'paid':
            self.percent = round((self.amount or 0.0) / total * 100.0, 2)
    payment_reference = fields.Char(string='Referencia Pago / SPEI')

    def _somgroup_advance_paid_vals(self, payment):
        """Vals para registrar un anticipo con el MONTO REAL del pago.

        Convierte de moneda si el pago se hizo en otra divisa y marca
        'partial' cuando el pago no cubre el hito completo (antes cualquier
        pago posteado marcaba el hito 100% pagado).
        """
        self.ensure_one()

        paid = payment.amount or 0.0
        if (
            payment.currency_id
            and self.currency_id
            and payment.currency_id != self.currency_id
        ):
            paid = payment.currency_id._convert(
                paid,
                self.currency_id,
                payment.company_id or self.env.company,
                payment.date or fields.Date.today(),
            )

        paid = min(paid, self.amount or 0.0)
        rounding = (self.currency_id and self.currency_id.rounding) or 0.01
        fully_paid = float_compare(
            paid, self.amount or 0.0, precision_rounding=rounding
        ) >= 0

        return {
            'advance_payment_id': payment.id,
            'paid_amount': paid,
            'remaining_amount': max((self.amount or 0.0) - paid, 0.0),
            'state': 'paid' if fully_paid else 'partial',
            'paid_date': payment.date or fields.Date.today(),
        }

    days_until_due = fields.Integer(
        string='Días para Vencer',
        compute='_compute_days_until_due',
        store=False
    )

    alert_color = fields.Char(
        string='Color Alerta',
        compute='_compute_days_until_due',
        store=False
    )

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
                rec.alert_color = 'red' if delta < 0 else ('orange' if delta <= 7 else 'gray')
            else:
                rec.days_until_due = 0
                rec.alert_color = 'blue'

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

    @api.model
    def get_payment_report_data(self, month=None, year=None, scope=None):
        """
        Endpoint para dashboard de pagos.
        scope:
        - import
        - national
        - all / False
        """
        from datetime import date as date_cls

        today = date_cls.today()
        month = month or today.month
        year = year or today.year

        scope = scope if scope in ('import', 'national') else False
        scope_domain = [('purchase_payment_scope', '=', scope)] if scope else []
        # OCs canceladas fuera del dashboard: sus hitos pendientes seguían
        # sumando en tesorería y podían inducir el pago de algo cancelado.
        scope_domain += [('order_id.state', 'not in', ('cancel',))]

        start_date = date_cls(year, month, 1)
        if month == 12:
            end_date = date_cls(year + 1, 1, 1)
        else:
            end_date = date_cls(year, month + 1, 1)

        current_schedules = self.search([
            ('due_date', '>=', start_date),
            ('due_date', '<', end_date),
        ] + scope_domain, order='due_date asc, id asc')

        future_schedules = self.search([
            ('due_date', '>=', end_date),
            ('state', 'in', ['pending', 'partial', 'overdue']),
        ] + scope_domain, order='due_date asc', limit=200)

        all_pending = self.search([
            ('state', 'in', ['pending', 'partial', 'overdue']),
        ] + scope_domain)

        Container = self.env['purchase.order.container']

        if scope == 'national':
            container_domain = [('id', '=', 0)]
        elif scope == 'import':
            container_domain = [('purchase_payment_scope', '=', 'import')]
        else:
            container_domain = []

        containers = Container.search(
            container_domain,
            order='tax_paid_date desc, id desc',
            limit=100
        )

        usd_currency = self.env.ref('base.USD', raise_if_not_found=False)
        mxn_currency = self.env.ref('base.MXN', raise_if_not_found=False)

        rate = 17.33  # último recurso absoluto (sin monedas configuradas)
        if usd_currency and mxn_currency:
            try:
                rate = usd_currency._convert(
                    1.0,
                    mxn_currency,
                    self.env.company,
                    today,
                )
            except Exception:
                # Fallback con la tasa almacenada más reciente, no con un
                # número congelado de 2024; y el fallo queda en el log.
                _logger.exception(
                    '[SOMGROUP] Fallo al convertir USD→MXN para el dashboard; '
                    'usando tasa almacenada.'
                )
                if usd_currency.rate:
                    rate = 1.0 / usd_currency.rate

        def _amount_to_usd_mxn(amount, currency):
            amount = amount or 0.0

            if not currency:
                return amount, amount * rate

            if mxn_currency and currency == mxn_currency:
                return (amount / rate if rate else 0.0), amount

            if usd_currency and currency == usd_currency:
                return amount, amount * rate

            try:
                mxn_amount = currency._convert(
                    amount,
                    mxn_currency,
                    self.env.company,
                    today,
                ) if mxn_currency else amount * rate
                usd_amount = mxn_amount / rate if rate else 0.0
                return usd_amount, mxn_amount
            except Exception:
                return amount, amount * rate

        def _schedule_to_dict(s):
            return {
                'id': s.id,
                'order_id': [s.order_id.id, s.order_id.name] if s.order_id else False,
                'partner': s.order_id.partner_id.name if s.order_id and s.order_id.partner_id else '',
                'purchase_payment_scope': s.purchase_payment_scope,
                'payment_type': s.payment_type,
                'percent': s.percent,
                'amount': s.amount,
                'currency_name': s.currency_id.name if s.currency_id else 'USD',
                'due_date': str(s.due_date) if s.due_date else False,
                'state': s.state,
                'paid_amount': s.paid_amount,
                'remaining_amount': s.remaining_amount,
                'is_manual': s.is_manual,
                'note': s.note or '',
                'days_until_due': s.days_until_due,
                'alert_color': s.alert_color,
                'paid_date': str(s.paid_date) if s.paid_date else False,
                'payment_reference': s.payment_reference or '',
            }

        advance_lines = []
        balance_lines = []

        adv_usd = 0.0
        adv_mxn = 0.0
        bal_usd = 0.0
        bal_mxn = 0.0

        for s in current_schedules:
            line = _schedule_to_dict(s)
            usd_amount, mxn_amount = _amount_to_usd_mxn(s.amount, s.currency_id)

            if s.payment_type in ('advance', 'second_advance'):
                advance_lines.append(line)
                adv_usd += usd_amount
                adv_mxn += mxn_amount
            else:
                balance_lines.append(line)
                bal_usd += usd_amount
                bal_mxn += mxn_amount

        tax_lines = []
        total_taxes = 0.0

        for c in containers:
            tax_lines.append({
                'id': c.id,
                'container': c.name,
                'order': c.order_id.name if c.order_id else '',
                'order_id': c.order_id.id if c.order_id else False,
                'type': c.container_type,
                'tax_amount': c.tax_amount or 0,
                'state': c.tax_state,
                'paid_date': str(c.tax_paid_date) if c.tax_paid_date else False,
                'pedimento': c.pedimento or '',
                'notes': c.notes or '',
            })
            total_taxes += c.tax_amount or 0

        total_usd = adv_usd + bal_usd
        total_mxn = adv_mxn + bal_mxn + total_taxes

        summary = {
            'total_usd': total_usd,
            'total_mxn': total_mxn,
            'credit_usd': 0,
            'credit_mxn': 0,
            'freight_sea_usd': 0,
            'freight_sea_mxn': 0,
            'freight_land_mxn': 0,
            'advances_usd': adv_usd,
            'advances_mxn': adv_mxn,
            'balances_usd': bal_usd,
            'balances_mxn': bal_mxn,
            'taxes_mxn': total_taxes,
        }

        counters = {
            'total_schedules': len(all_pending),
            'pending': len(all_pending.filtered(lambda s: s.state == 'pending')),
            'partial': len(all_pending.filtered(lambda s: s.state == 'partial')),
            'overdue': len(all_pending.filtered(lambda s: s.state == 'overdue')),
            'paid': len(current_schedules.filtered(lambda s: s.state == 'paid')),
            'manual': len(all_pending.filtered(lambda s: s.is_manual)),
        }

        month_groups = {}

        for s in future_schedules:
            if not s.due_date:
                continue

            key = s.due_date.strftime('%Y-%m')
            if key not in month_groups:
                month_groups[key] = {
                    'month': key,
                    'lines': [],
                    'total_usd': 0,
                    'total_mxn': 0,
                }

            usd_amount, mxn_amount = _amount_to_usd_mxn(s.amount, s.currency_id)

            month_groups[key]['lines'].append(_schedule_to_dict(s))
            month_groups[key]['total_usd'] += usd_amount
            month_groups[key]['total_mxn'] += mxn_amount

        future_months = sorted(month_groups.values(), key=lambda x: x['month'])

        return {
            'summary': summary,
            'counters': counters,
            'advance_lines': advance_lines,
            'balance_lines': balance_lines,
            'credit_lines': [],
            'freight_sea_lines': [],
            'freight_land_lines': [],
            'tax_lines': tax_lines,
            'future_months': future_months,
            'exchange_rate': round(rate, 2),
            'scope': scope or 'all',
        }

    def _get_advance_memo(self):
        self.ensure_one()

        order = self.order_id
        type_label = dict(self._fields['payment_type'].selection).get(self.payment_type, '')

        return 'ANTICIPO {} — {} ({:.0f}%)'.format(order.name, type_label, self.percent)

    def _get_expense_account(self, product=None):
        if product:
            account = (
                product.property_account_expense_id
                or product.categ_id.property_account_expense_categ_id
            )
            if account:
                return account

        account = self.env['account.account'].search(
            [('code', 'like', '1140'), ('active', '=', True)],
            limit=1
        )
        if account:
            return account

        return self.env['account.account'].search(
            [('account_type', 'in', ['expense', 'asset_current']), ('active', '=', True)],
            limit=1
        )

    def _get_partner_payable_account(self, partner):
        account = partner.property_account_payable_id

        if account:
            _logger.info(
                '[SOMGROUP][PAYABLE] Partner %s payable account: %s (%s)',
                partner.name, account.code, account.name,
            )
            return account

        account = self.env['account.account'].search([
            ('account_type', '=', 'liability_payable'),
            ('active', '=', True),
        ], limit=1)

        _logger.warning(
            '[SOMGROUP][PAYABLE] Partner %s has NO payable account, using fallback: %s',
            partner.name, account.code if account else 'NONE',
        )

        return account

    def _get_payment_move(self, payment):
        if payment.move_id:
            return payment.move_id

        if hasattr(payment, 'move_ids') and payment.move_ids:
            return payment.move_ids[0]

        if payment.name:
            move = self.env['account.move'].search([
                ('name', '=', payment.name),
            ], limit=1)
            if move:
                return move

        _logger.warning(
            '[SOMGROUP][GET_MOVE] Could not find move for payment %s (id=%s, state=%s)',
            payment.name, payment.id, payment.state,
        )

        return self.env['account.move']

    def _get_payments_for_invoice(self, invoice):
        Payment = self.env['account.payment']

        if not invoice or invoice.state != 'posted':
            return Payment

        payments = Payment

        for line in invoice.line_ids.filtered(
            lambda l: l.account_id.account_type == 'liability_payable'
        ):
            for matched in (line.matched_debit_ids | line.matched_credit_ids):
                counterpart = (
                    matched.debit_move_id
                    if line == matched.credit_move_id
                    else matched.credit_move_id
                )

                payment = Payment.search([
                    ('move_id', '=', counterpart.move_id.id),
                    ('state', 'in', list(POSTED_STATES)),
                ], limit=1)

                if payment:
                    payments |= payment

        return payments

    def _ensure_payment_or_invoice_exists(self):
        self.ensure_one()

        if self.payment_type in ('advance', 'second_advance'):
            if self.advance_payment_id:
                return self.advance_payment_id
            return self._create_advance_payment()

        if self.schedule_invoice_id:
            return self.schedule_invoice_id

        return self._create_balance_invoice()

    def _create_advance_payment(self):
        self.ensure_one()

        order = self.order_id
        memo = self._get_advance_memo()

        _logger.info(
            '[SOMGROUP][ADVANCE] Creating advance payment for schedule %s | '
            'OC: %s | Partner: %s | Amount: %s %s | Memo: %s',
            self.id, order.name, order.partner_id.name,
            self.amount, order.currency_id.name, memo,
        )

        journal = self.env['account.journal'].search([
            ('type', 'in', ['bank', 'cash']),
            ('company_id', '=', order.company_id.id),
        ], limit=1)

        if not journal:
            raise UserError(_(
                'No se encontró un diario de banco o efectivo. '
                'Configure uno antes de registrar anticipos.'
            ))

        payable_account = self._get_partner_payable_account(order.partner_id)

        Payment = self.env['account.payment']

        payment_vals = {
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': order.partner_id.id,
            'amount': self.amount,
            'currency_id': order.currency_id.id,
            'journal_id': journal.id,
            'date': fields.Date.today(),
            'purchase_schedule_id': self.id,
        }

        if payable_account and 'destination_account_id' in Payment._fields:
            payment_vals['destination_account_id'] = payable_account.id

        if 'memo' in Payment._fields:
            payment_vals['memo'] = memo
        elif 'ref' in Payment._fields:
            payment_vals['ref'] = memo

        payment = Payment.create(payment_vals)

        pay_move = self._get_payment_move(payment)
        if pay_move:
            pay_move.write({'ref': memo})

        payment.action_post()

        if payment.state not in POSTED_STATES:
            _logger.warning(
                '[SOMGROUP][ADVANCE] Payment %s unexpected state: %s',
                payment.name, payment.state,
            )

        self.write({
            'advance_payment_id': payment.id,
            'paid_amount': self.amount,
            'remaining_amount': 0.0,
            'state': 'paid',
            'paid_date': fields.Date.today(),
        })

        return payment

    def _create_balance_invoice(self):
        self.ensure_one()

        order = self.order_id

        _logger.info(
            '[SOMGROUP][BALANCE] Creating balance invoice for schedule %s | '
            'OC: %s | Partner: %s | OC Total: %s %s',
            self.id, order.name, order.partner_id.name,
            order.amount_total, order.currency_id.name,
        )

        type_label = dict(self._fields['payment_type'].selection).get(self.payment_type, '')
        ref = '{} — {} (100%)'.format(order.name, type_label)

        vals = {
            'move_type': 'in_invoice',
            'partner_id': order.partner_id.id,
            'currency_id': order.currency_id.id,
            'invoice_date': fields.Date.today(),
            'purchase_id': order.id,
            'narration': 'OC: {} | Factura completa — anticipos se reconcilian automáticamente'.format(
                order.name
            ),
            'ref': ref,
        }

        invoice_lines = []
        po_lines = order.order_line.filtered(lambda l: l.product_qty > 0)

        if po_lines:
            for pol in po_lines:
                account = self._get_expense_account(pol.product_id)
                taxes = pol.tax_ids

                if order.fiscal_position_id:
                    taxes = order.fiscal_position_id.map_tax(taxes)

                invoice_lines.append((0, 0, {
                    'name': pol.name or pol.product_id.name,
                    'product_id': pol.product_id.id,
                    'quantity': pol.product_qty,
                    'price_unit': pol.price_unit,
                    'account_id': account.id if account else False,
                    'purchase_line_id': pol.id,
                    'tax_ids': [(6, 0, taxes.ids)] if taxes else [(5, 0, 0)],
                }))
        else:
            invoice_lines.append((0, 0, {
                'name': 'Factura completa — {}'.format(order.name),
                'quantity': 1.0,
                'price_unit': order.amount_untaxed or order.amount_total,
                'account_id': self._get_expense_account().id,
                'tax_ids': [(5, 0, 0)],
            }))

        vals['invoice_line_ids'] = invoice_lines

        invoice = self.env['account.move'].create(vals)

        self.write({'schedule_invoice_id': invoice.id})

        _logger.info(
            '[SOMGROUP][BALANCE] Invoice created: %s (id=%s, state=%s) → schedule %s OC %s',
            invoice.name or '(borrador)', invoice.id, invoice.state,
            self.id, order.name,
        )

        return invoice

    def _reconcile_advances_to_invoice(self, invoice):
        if not invoice:
            _logger.warning('[SOMGROUP][RECONCILE] No invoice provided.')
            return

        if invoice.state != 'posted':
            _logger.info(
                '[SOMGROUP][RECONCILE] Invoice %s state="%s", skipping.',
                invoice.name, invoice.state,
            )
            return

        order = self.order_id
        payable_account = self._get_partner_payable_account(order.partner_id)

        _logger.info(
            '[SOMGROUP][RECONCILE] Starting reconciliation for invoice %s (id=%s) | '
            'OC: %s | amount_total=%s | amount_residual=%s | payable_account=%s',
            invoice.name, invoice.id, order.name,
            invoice.amount_total, invoice.amount_residual,
            payable_account.code if payable_account else 'NONE',
        )

        if not payable_account:
            _logger.error('[SOMGROUP][RECONCILE] No payable account found. Cannot reconcile.')
            return

        invoice_payable_lines = invoice.line_ids.filtered(
            lambda l: l.account_id == payable_account
            and not l.reconciled
        )

        if not invoice_payable_lines:
            _logger.warning('[SOMGROUP][RECONCILE] No unreconciled payable lines in invoice.')
            return

        advance_schedules = order.payment_schedule_ids.filtered(
            lambda s: s.payment_type in ('advance', 'second_advance')
            and s.advance_payment_id
            and s.advance_payment_id.state in POSTED_STATES
        )

        expected_advance_amount = sum(advance_schedules.mapped('amount'))

        if expected_advance_amount <= 0:
            _logger.info('[SOMGROUP][RECONCILE] No confirmed advances. Nothing to reconcile.')
            return

        payment_debit_lines = self.env['account.move.line'].search([
            ('partner_id', '=', order.partner_id.id),
            ('account_id.account_type', '=', 'liability_payable'),
            ('reconciled', '=', False),
            ('parent_state', '=', 'posted'),
            ('move_id', '!=', invoice.id),
            ('amount_residual', '>', 0),
        ], order='date asc, id asc')

        matched_lines = self.env['account.move.line']
        remaining_to_match = expected_advance_amount

        for line in payment_debit_lines:
            if remaining_to_match <= 0.01:
                break

            is_our_advance = False

            if line.move_id.ref and order.name in line.move_id.ref:
                is_our_advance = True

            if not is_our_advance:
                for sched in advance_schedules:
                    pay = sched.advance_payment_id
                    if pay.name and line.move_id.name == pay.name:
                        is_our_advance = True
                        break

            if not is_our_advance:
                move_ref = line.move_id.ref or ''
                move_narration = line.move_id.narration or ''
                line_name = line.name or ''
                combined = f'{move_ref} {move_narration} {line_name}'.upper()
                if order.name.upper() in combined and 'ANTICIPO' in combined:
                    is_our_advance = True

            # ELIMINADO el 4º criterio (coincidencia por monto puro): marcaba
            # como "nuestro anticipo" cualquier apunte del proveedor cuyo
            # debit (en MXN) coincidiera con el monto del hito (en USD) —
            # podía reconciliar el anticipo de OTRA OC del mismo proveedor.
            # Solo se aceptan coincidencias con referencia explícita a esta OC
            # o al pago del hito.

            if is_our_advance:
                matched_lines |= line
                remaining_to_match -= line.amount_residual

        if not matched_lines:
            _logger.warning(
                '[SOMGROUP][RECONCILE] No matching advance debit lines found for OC %s.',
                order.name,
            )
            return

        inv_account = invoice_payable_lines[0].account_id
        same_account_lines = matched_lines.filtered(lambda l: l.account_id == inv_account)
        diff_account_lines = matched_lines.filtered(lambda l: l.account_id != inv_account)

        if same_account_lines:
            lines_to_reconcile = invoice_payable_lines | same_account_lines
            try:
                lines_to_reconcile.reconcile()
                invoice.invalidate_recordset(['amount_residual', 'payment_state'])
                _logger.info(
                    '[SOMGROUP][RECONCILE] Direct reconciliation SUCCESS | Invoice %s residual=%s',
                    invoice.name, invoice.amount_residual,
                )
            except Exception as e:
                _logger.error('[SOMGROUP][RECONCILE] Direct reconciliation FAILED: %s', e)

        if diff_account_lines:
            for line in diff_account_lines:
                try:
                    if hasattr(invoice, 'js_assign_outstanding_line'):
                        invoice.js_assign_outstanding_line(line.id)
                except Exception as e:
                    _logger.error(
                        '[SOMGROUP][RECONCILE] Failed to apply outstanding line %s: %s',
                        line.id, e,
                    )

        invoice.invalidate_recordset(['amount_residual', 'payment_state'])

    def _recompute_from_payments(self):
        self._recompute_from_payments_by_order()

    def _recompute_from_payments_by_order(self, extra_payments=None):
        from datetime import date

        Payment = self.env['account.payment']
        extra_payments = extra_payments or Payment

        orders = self.mapped('order_id')

        for order in orders:
            order_schedules = self.filtered(lambda s: s.order_id == order).sorted(
                key=lambda s: (s.due_date or date.max)
            )

            if not order_schedules:
                continue

            direct_payments_db = Payment.search([
                ('purchase_schedule_id', 'in', order_schedules.ids),
                ('state', 'in', list(POSTED_STATES)),
            ])

            extra_for_order = extra_payments.filtered(
                lambda p: p.purchase_schedule_id and p.purchase_schedule_id in order_schedules
            )

            direct_payments = direct_payments_db | extra_for_order

            loose_extra = extra_payments.filtered(
                lambda p: not p.purchase_schedule_id and p.partner_id == order.partner_id
            )

            remaining_cascade = sum(loose_extra.mapped('amount'))

            for schedule in order_schedules:
                if (
                    schedule.payment_type in ('advance', 'second_advance')
                    and schedule.advance_payment_id
                    and schedule.advance_payment_id.state in POSTED_STATES
                ):
                    # Monto REAL del pago (antes se forzaba pagado completo
                    # aunque el anticipo se hubiera pagado parcial).
                    vals = schedule._somgroup_advance_paid_vals(
                        schedule.advance_payment_id
                    )
                    vals.pop('advance_payment_id', None)
                    schedule.sudo().write(vals)
                    continue

                direct = direct_payments.filtered(
                    lambda p: p.purchase_schedule_id == schedule
                )

                direct_amount = sum(direct.mapped('amount'))

                # DEDUP: un pago hecho por el wizard queda vinculado al hito
                # (direct) Y reconciliado a su factura (inv). Sumarlo en ambos
                # lados marcaba pagado completo un hito pagado a la mitad.
                inv_payments = self._get_payments_for_invoice(schedule.schedule_invoice_id)
                inv_payments = inv_payments - direct
                inv_amount = sum(inv_payments.mapped('amount'))

                reconciled_advance_amount = 0.0

                if schedule.payment_type == 'balance' and schedule.schedule_invoice_id:
                    invoice = schedule.schedule_invoice_id
                    if invoice.state == 'posted':
                        reconciled_advance_amount = invoice.amount_total - invoice.amount_residual
                        reconciled_advance_amount = max(
                            0,
                            reconciled_advance_amount - inv_amount
                        )

                cascade_amount = 0.0

                if (
                    remaining_cascade > 0
                    and direct_amount == 0
                    and inv_amount == 0
                    and reconciled_advance_amount == 0
                ):
                    cascade_amount = min(remaining_cascade, schedule.amount)
                    remaining_cascade -= cascade_amount

                schedule_paid = min(
                    direct_amount + inv_amount + reconciled_advance_amount + cascade_amount,
                    schedule.amount
                )

                all_for_schedule = direct | inv_payments

                if all_for_schedule:
                    paid_date = all_for_schedule.sorted('date')[-1].date
                elif schedule_paid > 0:
                    paid_date = fields.Date.today()
                else:
                    paid_date = schedule.paid_date

                new_state = self._resolve_state(
                    schedule_paid,
                    schedule.amount,
                    schedule.due_date
                )

                write_vals = {
                    'paid_amount': schedule_paid,
                    'remaining_amount': max(0.0, (schedule.amount or 0.0) - schedule_paid),
                    'state': new_state,
                }

                if paid_date:
                    write_vals['paid_date'] = paid_date

                schedule.sudo().write(write_vals)

    def action_register_payment(self):
        self.ensure_one()

        if self.state == 'paid':
            raise UserError(_('Este hito ya está completamente pagado.'))

        if self.payment_type in ('advance', 'second_advance'):
            order = self.order_id
            memo = self._get_advance_memo()

            payment_vals = {
                'default_payment_type': 'outbound',
                'default_partner_type': 'supplier',
                'default_partner_id': order.partner_id.id,
                'default_amount': self.amount,
                'default_currency_id': order.currency_id.id,
                'default_date': fields.Date.today(),
                'default_purchase_schedule_id': self.id,
            }

            Payment = self.env['account.payment']
            if 'memo' in Payment._fields:
                payment_vals['default_memo'] = memo
            elif 'ref' in Payment._fields:
                payment_vals['default_ref'] = memo

            type_label = dict(self._fields['payment_type'].selection).get(self.payment_type, '')

            return {
                'name': _('Registrar Anticipo — {} — {}').format(order.name, type_label),
                'type': 'ir.actions.act_window',
                'res_model': 'account.payment',
                'view_mode': 'form',
                'target': 'current',
                'context': payment_vals,
            }

        invoice = self._ensure_payment_or_invoice_exists()

        if not isinstance(invoice, type(self.env['account.move'])):
            return {'type': 'ir.actions.client', 'tag': 'reload'}

        if invoice.state == 'draft':
            raise UserError(_(
                'La factura de balance está en BORRADOR.\n\n'
                'El contador debe abrirla con "Ver Documento", verificar los montos '
                'y confirmarla antes de registrar el pago.\n\n'
                'Al confirmar la factura, los anticipos previos se reconciliarán '
                'automáticamente reduciendo el saldo a pagar.'
            ))

        if invoice.payment_state == 'paid':
            self.sudo().write({
                'paid_amount': self.amount,
                'remaining_amount': 0.0,
                'state': 'paid',
                'paid_date': fields.Date.today(),
            })
            return {'type': 'ir.actions.client', 'tag': 'reload'}

        type_label = dict(self._fields['payment_type'].selection).get(self.payment_type, '')

        return {
            'name': _('Registrar Pago — {}').format(type_label),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment.register',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_model': 'account.move',
                'active_ids': [invoice.id],
                'default_amount': invoice.amount_residual,
                'default_purchase_schedule_id': self.id,
            },
        }

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

        for rec in self.search([
            ('state', 'in', ['pending', 'partial']),
            ('due_date', '<', today),
            ('due_date', '!=', False),
        ]):
            rec.write({'state': 'overdue'})

        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_sync_from_accounting(self):
        self._recompute_from_payments_by_order()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_view_payments(self):
        self.ensure_one()

        payment_ids = self.payment_ids.ids

        if self.advance_payment_id:
            payment_ids = list(set(payment_ids + [self.advance_payment_id.id]))

        return {
            'name': _('Pagos Contables'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'list,form',
            'domain': [('id', 'in', payment_ids)],
        }

    def action_view_schedule_invoice(self):
        self.ensure_one()

        if self.payment_type in ('advance', 'second_advance'):
            if self.advance_payment_id:
                return {
                    'name': _('Pago de Anticipo'),
                    'type': 'ir.actions.act_window',
                    'res_model': 'account.payment',
                    'view_mode': 'form',
                    'res_id': self.advance_payment_id.id,
                }

            raise UserError(_('Este hito es un anticipo. Use "Pagar" para crear el pago directo.'))

        invoice = self._ensure_payment_or_invoice_exists()

        return {
            'name': _('Factura del Hito'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': invoice.id,
        }