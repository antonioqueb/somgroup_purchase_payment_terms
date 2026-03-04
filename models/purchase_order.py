from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    bl_date = fields.Date(string='Fecha BL')
    bl_number = fields.Char(string='Número BL')
    eta_date = fields.Date(string='ETA')
    container_ids = fields.One2many('purchase.order.container', 'order_id', string='Contenedores')
    container_count = fields.Integer(string='# Contenedores', compute='_compute_container_count')

    payment_schedule_ids = fields.One2many(
        'purchase.payment.schedule', 'order_id', string='Calendario de Pagos')
    payment_schedule_warning = fields.Char(
        string='Aviso de Pago', compute='_compute_payment_warning', store=False)
    requires_bl_date = fields.Boolean(compute='_compute_term_flags', store=False)
    requires_eta = fields.Boolean(compute='_compute_term_flags', store=False)
    is_import_order = fields.Boolean(string='Es Orden de Importación', default=False)
    telex_release_required = fields.Boolean(compute='_compute_term_flags', store=False)
    advance_amount = fields.Monetary(
        string='Monto Anticipo', compute='_compute_advance_amount',
        store=False, currency_field='currency_id')
    balance_amount = fields.Monetary(
        string='Monto Balance', compute='_compute_advance_amount',
        store=False, currency_field='currency_id')
    next_payment_date = fields.Date(compute='_compute_next_payment_date', store=False)
    overdue_payments = fields.Boolean(compute='_compute_next_payment_date', store=False)

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
            advances = rec.payment_schedule_ids.filtered(lambda l: l.payment_type == 'advance')
            balances = rec.payment_schedule_ids.filtered(lambda l: l.payment_type != 'advance')
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
            rec.next_payment_date = min(upcoming.mapped('due_date')) if upcoming else False

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
                    today <= l.due_date <= today + timedelta(days=7))
                if upcoming:
                    warnings.append(f'🟡 Vence en 7 días: {upcoming[0].due_date}')
            rec.payment_schedule_warning = ' | '.join(warnings) if warnings else ''

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
                'message': _('El término "%s" requiere la Fecha BL.') % self.payment_term_id.name,
            }}
        if term_type in ['against_delivery', 'advance_days_arrival'] and not self.eta_date:
            return {'warning': {
                'title': _('ETA requerida'),
                'message': _('El término "%s" requiere la ETA.') % self.payment_term_id.name,
            }}

    def action_calculate_payment_schedule(self):
        for order in self:
            if not order.payment_term_id:
                raise UserError(_('Seleccione un término de pago antes de calcular.'))
            if order.payment_term_id.somgroup_term_type == 'standard':
                raise UserError(_('Este término usa el motor estándar de Odoo.'))
            order._recalculate_payment_schedule()

    def _recalculate_payment_schedule(self):
        self.ensure_one()
        pending = self.payment_schedule_ids.filtered(
            lambda l: l.state == 'pending' and not l.payment_ids)
        pending.unlink()
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

    def write(self, vals):
        res = super().write(vals)
        if {'bl_date', 'eta_date', 'payment_term_id'}.intersection(vals.keys()):
            for order in self.filtered(
                lambda o: o.is_import_order and o.payment_term_id and
                o.payment_term_id.somgroup_term_type != 'standard'
            ):
                order._recalculate_payment_schedule()
        return res


class PurchaseOrderContainer(models.Model):
    _name = 'purchase.order.container'
    _description = 'Contenedor de Importación'
    _order = 'order_id, name'

    order_id = fields.Many2one('purchase.order', string='Orden de Compra', ondelete='cascade', required=True)
    name = fields.Char(string='No. Contenedor', required=True)
    container_type = fields.Selection([
        ('20', '20\''), ('40', '40\''), ('40hc', '40\' HC'),
    ], string='Tipo', default='20')
    seal_number = fields.Char(string='Sello')
    tax_amount = fields.Monetary(string='Impuestos MXN', currency_field='currency_id')
    tax_state = fields.Selection([
        ('pending', 'Pendiente'), ('paid', 'Pagado'),
    ], string='Estado Impuesto', default='pending')
    tax_paid_date = fields.Date(string='Fecha Pago Imp.')
    pedimento = fields.Char(string='Pedimento')
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.ref('base.MXN'), string='Moneda')
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

    payment_ids = fields.One2many(
        'account.payment', 'purchase_schedule_id', string='Pagos Contables', readonly=True)

    # Factura de anticipo generada automáticamente para este hito
    advance_invoice_id = fields.Many2one(
        'account.move',
        string='Factura de Anticipo',
        readonly=True,
        ondelete='set null',
        help='Vendor bill de anticipo generada para este hito. Se reconcilia con la factura final.',
    )

    state = fields.Selection([
        ('pending', 'Pendiente'),
        ('partial', 'Pago Parcial'),
        ('paid', 'Pagado'),
        ('overdue', 'Vencido'),
    ], string='Estado', default='pending', store=True)

    paid_amount = fields.Monetary(
        string='Monto Pagado', store=True, default=0.0, currency_field='currency_id')
    remaining_amount = fields.Monetary(
        string='Saldo Pendiente', store=True, default=0.0, currency_field='currency_id')
    paid_date = fields.Date(string='Fecha Pago Real', store=True)
    payment_reference = fields.Char(string='Referencia Pago / SPEI')

    days_until_due = fields.Integer(
        string='Días para Vencer', compute='_compute_days_until_due', store=False)
    alert_color = fields.Char(
        string='Color Alerta', compute='_compute_days_until_due', store=False)

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

    def _recompute_from_payments(self):
        self._recompute_from_payments_by_order()

    def _recompute_from_payments_by_order(self, extra_payments=None):
        """
        Sincroniza state/paid_amount desde contabilidad.

        Fuentes de pago que considera (por orden de prioridad):
          1. Pagos reconciliados contra facturas de la OC (in_invoice posted)
          2. Pagos vinculados directamente via purchase_schedule_id (DB)
          3. Pagos reconciliados contra advance_invoice_id del hito
          4. extra_payments: recién creados en la misma transacción (mismo cursor)
        """
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

            # ── 1. Pagos via facturas normales reconciliadas ──────────────────
            all_payments = Payment

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

            # ── 2. Pagos directamente vinculados via purchase_schedule_id (DB) ──
            direct_payments_db = Payment.search([
                ('purchase_schedule_id', 'in', order_schedules.ids),
                ('state', '=', 'posted'),
            ])
            all_payments |= direct_payments_db

            # ── 3. Pagos reconciliados contra advance_invoice_id de cada hito ──
            for schedule in order_schedules:
                if schedule.advance_invoice_id and schedule.advance_invoice_id.state == 'posted':
                    adv_inv = schedule.advance_invoice_id
                    for line in adv_inv.line_ids.filtered(
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

            # ── 4. extra_payments: recién creados en esta transacción ─────────
            extra_for_order = extra_payments.filtered(
                lambda p: p.purchase_schedule_id and
                p.purchase_schedule_id in order_schedules
            )
            all_payments |= extra_for_order

            for p in extra_payments.filtered(
                lambda p: not p.purchase_schedule_id and
                p.partner_id == order.partner_id
            ):
                all_payments |= p

            direct_payments = direct_payments_db | extra_for_order

            total_paid = sum(all_payments.mapped('amount'))
            _logger.info('[SOMGROUP] order %s | payments=%s | total_paid=%s',
                         order.name, all_payments.ids, total_paid)

            remaining_to_distribute = total_paid

            for schedule in order_schedules:
                direct = direct_payments.filtered(
                    lambda p: p.purchase_schedule_id == schedule
                )
                direct_amount = sum(direct.mapped('amount'))

                # También incluir pagos reconciliados contra advance_invoice de este hito
                adv_inv_payments = Payment
                if schedule.advance_invoice_id and schedule.advance_invoice_id.state == 'posted':
                    adv_inv = schedule.advance_invoice_id
                    for line in adv_inv.line_ids.filtered(
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
                                adv_inv_payments |= payment

                adv_inv_amount = sum(adv_inv_payments.mapped('amount'))

                if direct_amount > 0 or adv_inv_amount > 0:
                    schedule_paid = min(direct_amount + adv_inv_amount, schedule.amount)
                    remaining_to_distribute = max(
                        0.0, remaining_to_distribute - (direct_amount + adv_inv_amount)
                    )
                elif remaining_to_distribute > 0:
                    schedule_paid = min(remaining_to_distribute, schedule.amount)
                    remaining_to_distribute -= schedule_paid
                else:
                    schedule_paid = 0.0

                all_direct = direct | adv_inv_payments
                if all_direct:
                    paid_date = all_direct.sorted('date')[-1].date
                elif schedule_paid > 0 and all_payments:
                    paid_date = all_payments.sorted('date')[-1].date
                else:
                    paid_date = schedule.paid_date

                new_state = self._resolve_state(schedule_paid, schedule.amount, schedule.due_date)

                _logger.info('[SOMGROUP] schedule %s (%s) | paid=%s | state=%s',
                             schedule.id, schedule.payment_type, schedule_paid, new_state)

                vals = {
                    'paid_amount': schedule_paid,
                    'remaining_amount': max(0.0, (schedule.amount or 0.0) - schedule_paid),
                    'state': new_state,
                }
                if paid_date:
                    vals['paid_date'] = paid_date

                schedule.sudo().write(vals)

    # ──────────────────────────────────────────────────────────────────────────
    # Producto de anticipo — buscado/creado una sola vez por compañía
    # ──────────────────────────────────────────────────────────────────────────
    def _get_advance_product(self):
        """Devuelve (o crea) el producto de servicio usado para facturas de anticipo."""
        Product = self.env['product.product']

        # 1. Buscar por referencia interna estándar de Odoo (purchase_stock lo crea a veces)
        product = self.env.ref('purchase.product_product_advance', raise_if_not_found=False)
        if product:
            return product

        # 2. Buscar por nombre
        product = Product.search(
            [('name', '=', 'Anticipo a Proveedor'), ('type', '=', 'service')], limit=1
        )
        if product:
            return product

        # 3. Crear
        return Product.create({
            'name': 'Anticipo a Proveedor',
            'type': 'service',
            'purchase_ok': True,
            'sale_ok': False,
            'description': 'Producto para registrar anticipos a proveedores en importaciones.',
        })

    def _get_advance_expense_account(self, product):
        """Devuelve la cuenta de gastos/anticipos para la línea de la factura de anticipo.
        
        NOTA Odoo 19: account.account ya no tiene campo company_id.
        La restricción por compañía se maneja a nivel de account.chart.template
        y account.company. No filtrar por company_id en el search.
        """
        # Primero intentar la cuenta del producto
        account = (
            product.property_account_expense_id
            or product.categ_id.property_account_expense_categ_id
        )
        if account:
            return account

        # Fallback: buscar cuenta de anticipos a proveedores por código
        # Código típico en México: 1140 Anticipos a proveedores
        account = self.env['account.account'].search([
            ('code', 'like', '1140'),
            ('deprecated', '=', False),
        ], limit=1)
        if account:
            return account

        # Último fallback: cualquier cuenta de gastos o activo circulante activa
        account = self.env['account.account'].search([
            ('account_type', 'in', ['expense', 'asset_current']),
            ('deprecated', '=', False),
        ], limit=1)
        return account

    def _create_advance_invoice(self):
        """
        Crea una vendor bill (in_invoice) de anticipo para este hito y la postea.
        La factura queda lista para recibir un pago via account.payment.register.
        Al llegar la factura real del proveedor, el contador deberá aplicar
        el crédito de anticipo manualmente o via 'add outstanding credits'.
        """
        self.ensure_one()
        order = self.order_id

        if self.advance_invoice_id:
            # Ya existe — no crear duplicado
            _logger.info(
                '[SOMGROUP] schedule %s ya tiene advance_invoice_id=%s, reutilizando.',
                self.id, self.advance_invoice_id.id
            )
            return self.advance_invoice_id

        product = self._get_advance_product()
        account = self._get_advance_expense_account(product)

        if not account:
            raise UserError(_(
                'No se encontró una cuenta contable para la línea del anticipo. '
                'Configure la cuenta de gastos en el producto "Anticipo a Proveedor" '
                'o en su categoría.'
            ))

        type_label = dict(self._fields['payment_type'].selection).get(self.payment_type, '')
        ref = '{} — {} ({:.0f}%)'.format(order.name, type_label, self.percent)

        invoice_vals = {
            'move_type': 'in_invoice',
            'partner_id': order.partner_id.id,
            'currency_id': order.currency_id.id,
            'invoice_date': fields.Date.today(),
            # NO se asigna purchase_id para evitar que Odoo jale todas las líneas de la OC
            'narration': 'Anticipo OC: {} | {}'.format(order.name, self.note or ''),
            'ref': ref,
            'invoice_line_ids': [(0, 0, {
                'name': '[ANTICIPO] {}'.format(ref),
                'product_id': product.id,
                'quantity': 1.0,
                'price_unit': self.amount,
                'account_id': account.id,
            })],
        }

        invoice = self.env['account.move'].create(invoice_vals)
        invoice.action_post()

        self.write({'advance_invoice_id': invoice.id})

        _logger.info(
            '[SOMGROUP] Creada factura de anticipo %s (id=%s) para schedule %s de OC %s',
            invoice.name, invoice.id, self.id, order.name
        )
        return invoice

    def action_register_payment(self):
        self.ensure_one()
        if self.state == 'paid':
            raise UserError(_('Este hito ya está completamente pagado.'))

        order = self.order_id

        # ── Caso 1: hay facturas reales pendientes de pago ───────────────────
        real_invoices = order.invoice_ids.filtered(
            lambda inv: inv.move_type == 'in_invoice'
            and inv.state == 'posted'
            and inv.payment_state in ('not_paid', 'partial')
            # Excluir advance_invoice_id de otros hitos para no mezclar
            and inv.id != (self.advance_invoice_id.id if self.advance_invoice_id else False)
        )

        if real_invoices:
            return {
                'name': _('Registrar Pago'),
                'type': 'ir.actions.act_window',
                'res_model': 'account.payment.register',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'active_model': 'account.move',
                    'active_ids': real_invoices.ids,
                    'default_amount': min(
                        self.remaining_amount or self.amount,
                        sum(real_invoices.mapped('amount_residual'))
                    ),
                    'default_purchase_schedule_id': self.id,
                },
            }

        # ── Caso 2: anticipo — crear (o reutilizar) factura de anticipo ──────
        # Esto garantiza que el pago quede contablemente reconciliado
        advance_invoice = self._create_advance_invoice()

        # Si la factura ya estaba pagada (edge case), marcar y salir
        if advance_invoice.payment_state == 'paid':
            self.sudo().write({
                'paid_amount': self.amount,
                'remaining_amount': 0.0,
                'state': 'paid',
                'paid_date': fields.Date.today(),
            })
            return {'type': 'ir.actions.client', 'tag': 'reload'}

        return {
            'name': _('Registrar Anticipo'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment.register',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_model': 'account.move',
                'active_ids': [advance_invoice.id],
                'default_amount': min(
                    self.remaining_amount or self.amount,
                    advance_invoice.amount_residual,
                ),
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
        """Botón manual de resync — útil para registros históricos."""
        self._recompute_from_payments_by_order()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_view_payments(self):
        self.ensure_one()
        return {
            'name': _('Pagos Contables'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'list,form',
            'domain': [('purchase_schedule_id', '=', self.id)],
        }

    def action_view_advance_invoice(self):
        """Botón para abrir la factura de anticipo del hito."""
        self.ensure_one()
        if not self.advance_invoice_id:
            raise UserError(_('Este hito no tiene factura de anticipo generada.'))
        return {
            'name': _('Factura de Anticipo'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.advance_invoice_id.id,
        }