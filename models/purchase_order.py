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
        # Borrar SOLO hitos pendientes sin pago y sin factura/pago directo vinculado
        pending_clean = self.payment_schedule_ids.filtered(
            lambda l: l.state == 'pending'
            and not l.payment_ids
            and not l.schedule_invoice_id
            and not l.advance_payment_id
        )
        pending_clean.unlink()

        # Si quedan hitos (tienen pago o factura), no crear duplicados
        if self.payment_schedule_ids:
            _logger.info(
                '[SOMGROUP] OC %s ya tiene hitos con factura/pago, omitiendo recalculo.',
                self.name)
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

    def write(self, vals):
        res = super().write(vals)
        trigger_fields = {'bl_date', 'eta_date', 'payment_term_id'}
        if trigger_fields.intersection(vals.keys()):
            for order in self.filtered(
                lambda o: o.is_import_order and o.payment_term_id and
                o.payment_term_id.somgroup_term_type != 'standard'
            ):
                has_committed = any(
                    s.schedule_invoice_id or s.payment_ids or s.advance_payment_id
                    for s in order.payment_schedule_ids
                )
                if not has_committed:
                    order._recalculate_payment_schedule()
        return res


class PurchaseOrderContainer(models.Model):
    _name = 'purchase.order.container'
    _description = 'Contenedor de Importación'
    _order = 'order_id, name'

    order_id = fields.Many2one(
        'purchase.order', string='Orden de Compra', ondelete='cascade', required=True)
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

    order_id = fields.Many2one(
        'purchase.order', string='Orden de Compra', ondelete='cascade', required=True)
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

    # ── Pago directo de anticipo (sin factura) ──────────────────────────
    advance_payment_id = fields.Many2one(
        'account.payment',
        string='Pago de Anticipo',
        readonly=True,
        ondelete='set null',
        help='Pago directo registrado para el anticipo (sin factura). '
             'El memo contiene la referencia de la OC para reconciliación posterior.',
    )

    # ── Factura del hito (solo para balance) ────────────────────────────
    schedule_invoice_id = fields.Many2one(
        'account.move',
        string='Factura del Hito',
        readonly=True,
        ondelete='set null',
        help='Factura vinculada a este hito. '
             'Solo se genera para balance/liquidación (al 100% del monto de la OC). '
             'Los anticipos previos se reconcilian automáticamente.',
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

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers contables
    # ──────────────────────────────────────────────────────────────────────────

    def _get_advance_memo(self):
        """Genera el memo/referencia que identifica el anticipo con la OC."""
        self.ensure_one()
        order = self.order_id
        type_label = dict(self._fields['payment_type'].selection).get(self.payment_type, '')
        return 'ANTICIPO {} — {} ({:.0f}%)'.format(order.name, type_label, self.percent)

    def _get_expense_account(self, product=None):
        """
        Odoo 19: sin company_id ni deprecated en account.account.
        Prioridad: cuenta del producto → categoría → código 1140 → expense genérico.
        """
        if product:
            account = (
                product.property_account_expense_id
                or product.categ_id.property_account_expense_categ_id
            )
            if account:
                return account
        account = self.env['account.account'].search(
            [('code', 'like', '1140'), ('active', '=', True)], limit=1)
        if account:
            return account
        return self.env['account.account'].search(
            [('account_type', 'in', ['expense', 'asset_current']), ('active', '=', True)],
            limit=1)

    def _get_payments_for_invoice(self, invoice):
        """
        Odoo 19: account.move ya NO tiene .payment_id
        Se busca via reconciliación de partidas.
        """
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
                    ('state', '=', 'posted'),
                ], limit=1)
                if payment:
                    payments |= payment
        return payments

    def _find_advance_payments_by_memo(self, order):
        """
        Busca pagos de anticipo registrados para esta OC usando el memo/ref
        que contiene el nombre de la OC.
        """
        Payment = self.env['account.payment']
        # Buscar pagos cuyo memo contenga el nombre de la OC
        payments = Payment.search([
            ('partner_id', '=', order.partner_id.id),
            ('state', '=', 'posted'),
            ('payment_type', '=', 'outbound'),
            '|',
            ('ref', 'ilike', order.name),
            ('memo', 'ilike', order.name),
        ])
        return payments

    # ──────────────────────────────────────────────────────────────────────────
    # NUEVO FLUJO: Anticipo = Pago directo, Balance = Factura 100%
    # ──────────────────────────────────────────────────────────────────────────

    def _ensure_payment_or_invoice_exists(self):
        """
        Para anticipos: crea un pago directo (sin factura).
        Para balance: crea factura al 100% y reconcilia anticipos.
        """
        self.ensure_one()
        if self.payment_type in ('advance', 'second_advance'):
            if self.advance_payment_id:
                return self.advance_payment_id
            return self._create_advance_payment()
        else:
            if self.schedule_invoice_id:
                return self.schedule_invoice_id
            return self._create_balance_invoice()

    def _create_advance_payment(self):
        """
        Crea un pago directo (outbound) al proveedor SIN factura.
        El memo contiene el nombre de la OC como clave de referencia.
        El pago se postea inmediatamente.
        """
        self.ensure_one()
        order = self.order_id
        memo = self._get_advance_memo()

        # Buscar journal de banco/efectivo
        journal = self.env['account.journal'].search([
            ('type', 'in', ['bank', 'cash']),
            ('company_id', '=', order.company_id.id),
        ], limit=1)

        if not journal:
            raise UserError(_(
                'No se encontró un diario de banco o efectivo. '
                'Configure uno antes de registrar anticipos.'
            ))

        # Cuenta de outstanding payments (destino del pago)
        payment_vals = {
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': order.partner_id.id,
            'amount': self.amount,
            'currency_id': order.currency_id.id,
            'journal_id': journal.id,
            'date': fields.Date.today(),
            'ref': memo,
            'purchase_schedule_id': self.id,
        }

        # Odoo 19: memo field — usar ref si memo no existe
        Payment = self.env['account.payment']
        if 'memo' in Payment._fields:
            payment_vals['memo'] = memo

        payment = Payment.create(payment_vals)
        payment.action_post()

        self.write({
            'advance_payment_id': payment.id,
            'paid_amount': self.amount,
            'remaining_amount': 0.0,
            'state': 'paid',
            'paid_date': fields.Date.today(),
        })

        _logger.info(
            '[SOMGROUP] Pago anticipo %s (id=%s) → hito %s OC %s | memo: %s',
            payment.name, payment.id, self.id, order.name, memo
        )
        return payment

    def _create_balance_invoice(self):
        """
        Crea factura al 100% del monto de la OC (no solo el balance).
        Luego busca anticipos previos por memo y los reconcilia contra esta factura
        para que el saldo residual sea solo lo que falta por pagar.
        """
        self.ensure_one()
        order = self.order_id

        # ── Crear factura al 100% de la OC ──────────────────────────────
        type_label = dict(self._fields['payment_type'].selection).get(self.payment_type, '')
        ref = '{} — {} (100%)'.format(order.name, type_label)

        vals = {
            'move_type': 'in_invoice',
            'partner_id': order.partner_id.id,
            'currency_id': order.currency_id.id,
            'invoice_date': fields.Date.today(),
            'purchase_id': order.id,
            'narration': 'OC: {} | Factura completa — anticipos se reconcilian automáticamente'.format(
                order.name),
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
            # Fallback: línea genérica
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
            '[SOMGROUP] Factura balance %s (id=%s, borrador) → hito %s OC %s',
            invoice.name or '(borrador)', invoice.id, self.id, order.name
        )

        # ── Reconciliar anticipos previos ────────────────────────────────
        # La factura queda en borrador. Cuando el contador la confirme (post),
        # se ejecutará la reconciliación automática de anticipos.
        # Pero también intentamos reconciliar ahora si ya hay anticipos posted.
        return invoice

    def _reconcile_advances_to_invoice(self, invoice):
        """
        Busca pagos de anticipo de la misma OC (por memo y por purchase_schedule_id)
        y los reconcilia contra la factura para reducir el saldo residual.
        """
        if not invoice or invoice.state != 'posted':
            return

        order = self.order_id
        Payment = self.env['account.payment']

        # Recopilar pagos de anticipo de esta OC
        advance_payments = Payment.browse()

        # 1. Pagos vinculados directamente via purchase_schedule_id (anticipos del calendario)
        advance_schedules = order.payment_schedule_ids.filtered(
            lambda s: s.payment_type in ('advance', 'second_advance') and s.advance_payment_id
        )
        for sched in advance_schedules:
            if sched.advance_payment_id.state == 'posted':
                advance_payments |= sched.advance_payment_id

        # 2. Pagos encontrados por memo/ref que contengan el nombre de la OC
        memo_payments = Payment.search([
            ('partner_id', '=', order.partner_id.id),
            ('state', '=', 'posted'),
            ('payment_type', '=', 'outbound'),
            ('id', 'not in', advance_payments.ids),
            '|',
            ('ref', 'ilike', order.name),
            *([('memo', 'ilike', order.name)] if 'memo' in Payment._fields else []),
        ])
        advance_payments |= memo_payments

        if not advance_payments:
            _logger.info('[SOMGROUP] No se encontraron anticipos para reconciliar en OC %s', order.name)
            return

        # ── Reconciliar: buscar la línea payable de la factura y las de los pagos ──
        invoice_payable_lines = invoice.line_ids.filtered(
            lambda l: l.account_id.account_type == 'liability_payable'
            and not l.reconciled
        )

        if not invoice_payable_lines:
            _logger.info('[SOMGROUP] No hay líneas payable sin reconciliar en factura %s', invoice.name)
            return

        payment_payable_lines = self.env['account.move.line']
        for payment in advance_payments:
            payment_lines = payment.move_id.line_ids.filtered(
                lambda l: l.account_id.account_type == 'liability_payable'
                and not l.reconciled
            )
            payment_payable_lines |= payment_lines

        if not payment_payable_lines:
            _logger.info('[SOMGROUP] No hay líneas payable de pagos sin reconciliar para OC %s', order.name)
            return

        # Reconciliar todas juntas
        lines_to_reconcile = invoice_payable_lines | payment_payable_lines
        try:
            lines_to_reconcile.reconcile()
            _logger.info(
                '[SOMGROUP] Reconciliación exitosa: factura %s con %d pagos anticipos para OC %s',
                invoice.name, len(advance_payments), order.name
            )
        except Exception as e:
            _logger.warning(
                '[SOMGROUP] Error al reconciliar anticipos con factura %s OC %s: %s',
                invoice.name, order.name, e
            )

    # ──────────────────────────────────────────────────────────────────────────
    # Recompute de estados
    # ──────────────────────────────────────────────────────────────────────────

    def _recompute_from_payments(self):
        self._recompute_from_payments_by_order()

    def _recompute_from_payments_by_order(self, extra_payments=None):
        """
        Sincroniza state/paid_amount desde contabilidad.
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

            direct_payments_db = Payment.search([
                ('purchase_schedule_id', 'in', order_schedules.ids),
                ('state', '=', 'posted'),
            ])
            extra_for_order = extra_payments.filtered(
                lambda p: p.purchase_schedule_id and p.purchase_schedule_id in order_schedules
            )
            direct_payments = direct_payments_db | extra_for_order

            # Pagos sueltos del mismo proveedor sin vínculo directo
            loose_extra = extra_payments.filtered(
                lambda p: not p.purchase_schedule_id and p.partner_id == order.partner_id
            )
            remaining_cascade = sum(loose_extra.mapped('amount'))

            for schedule in order_schedules:
                # Para anticipos con advance_payment_id, checar directo
                if schedule.payment_type in ('advance', 'second_advance') and schedule.advance_payment_id:
                    if schedule.advance_payment_id.state == 'posted':
                        schedule.sudo().write({
                            'paid_amount': schedule.amount,
                            'remaining_amount': 0.0,
                            'state': 'paid',
                            'paid_date': schedule.advance_payment_id.date,
                        })
                        continue

                direct = direct_payments.filtered(
                    lambda p: p.purchase_schedule_id == schedule
                )
                direct_amount = sum(direct.mapped('amount'))

                inv_payments = self._get_payments_for_invoice(schedule.schedule_invoice_id)
                inv_amount = sum(inv_payments.mapped('amount'))

                # Para balance: considerar también los anticipos reconciliados
                # que ya reducen el amount_residual de la factura
                reconciled_advance_amount = 0.0
                if schedule.payment_type == 'balance' and schedule.schedule_invoice_id:
                    invoice = schedule.schedule_invoice_id
                    if invoice.state == 'posted':
                        # El monto total menos el residual = lo que ya se pagó/reconcilió
                        reconciled_advance_amount = invoice.amount_total - invoice.amount_residual
                        # Descontar lo que ya contamos via inv_payments
                        reconciled_advance_amount = max(0, reconciled_advance_amount - inv_amount)

                # Cascade solo si no hay fuentes directas
                cascade_amount = 0.0
                if remaining_cascade > 0 and direct_amount == 0 and inv_amount == 0 and reconciled_advance_amount == 0:
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
                    schedule_paid, schedule.amount, schedule.due_date)

                _logger.info('[SOMGROUP] schedule %s (%s) | paid=%s | state=%s',
                             schedule.id, schedule.payment_type, schedule_paid, new_state)

                write_vals = {
                    'paid_amount': schedule_paid,
                    'remaining_amount': max(0.0, (schedule.amount or 0.0) - schedule_paid),
                    'state': new_state,
                }
                if paid_date:
                    write_vals['paid_date'] = paid_date

                schedule.sudo().write(write_vals)

    # ──────────────────────────────────────────────────────────────────────────
    # Acción principal: Registrar Pago
    # ──────────────────────────────────────────────────────────────────────────

    def action_register_payment(self):
        """
        Anticipo/Segundo tramo → crea pago directo (sin factura).
        Balance → abre wizard de pago sobre la factura al 100%.
        """
        self.ensure_one()
        if self.state == 'paid':
            raise UserError(_('Este hito ya está completamente pagado.'))

        if self.payment_type in ('advance', 'second_advance'):
            # Crear pago directo
            self._create_advance_payment()
            return {'type': 'ir.actions.client', 'tag': 'reload'}

        # Balance → necesita factura
        invoice = self._ensure_payment_or_invoice_exists()

        if not isinstance(invoice, type(self.env['account.move'])):
            # Si retornó un payment (no debería para balance), reload
            return {'type': 'ir.actions.client', 'tag': 'reload'}

        # Balance en borrador → el contador debe confirmarla primero
        if invoice.state == 'draft':
            raise UserError(_(
                'La factura de balance está en BORRADOR.\n\n'
                'El contador debe abrirla (botón "📄 Ver Factura"), '
                'verificar los montos y confirmarla antes de registrar el pago.\n\n'
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

    # ──────────────────────────────────────────────────────────────────────────
    # Acciones UI
    # ──────────────────────────────────────────────────────────────────────────

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
        """Abre la factura vinculada al hito (solo para balance)."""
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
            raise UserError(_('Este hito es un anticipo. Use "💵 Pagar" para crear el pago directo.'))

        invoice = self._ensure_payment_or_invoice_exists()
        return {
            'name': _('Factura del Hito'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': invoice.id,
        }