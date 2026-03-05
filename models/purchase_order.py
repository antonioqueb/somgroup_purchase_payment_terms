from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

# En Odoo 19, pagos de banco quedan en 'in_process' hasta validación manual.
# Ambos estados representan un pago confirmado/real.
POSTED_STATES = ('posted', 'in_process', 'paid')


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
    _rec_name = 'display_name_computed'

    display_name_computed = fields.Char(
        string='Nombre', compute='_compute_display_name_computed', store=False)

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
        'account.payment', 'purchase_schedule_id', string='Pagos Contables', readonly=True)

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
    # Reporte de Pagos — Dashboard OWL
    # ──────────────────────────────────────────────────────────────────────────

    @api.model
    def get_payment_report_data(self, month=None, year=None):
        """
        Endpoint para el dashboard de reporte de pagos.
        Devuelve resumen ejecutivo + detalle por sección + proyección multi-mes.
        """
        from datetime import date as date_cls

        today = date_cls.today()
        month = month or today.month
        year = year or today.year

        # Rango del mes seleccionado
        start_date = date_cls(year, month, 1)
        if month == 12:
            end_date = date_cls(year + 1, 1, 1)
        else:
            end_date = date_cls(year, month + 1, 1)

        # ── Schedules del mes ────────────────────────────────────────────
        current_schedules = self.search([
            ('due_date', '>=', start_date),
            ('due_date', '<', end_date),
        ], order='due_date asc, id asc')

        # ── Schedules futuros ────────────────────────────────────────────
        future_schedules = self.search([
            ('due_date', '>=', end_date),
            ('state', 'in', ['pending', 'partial', 'overdue']),
        ], order='due_date asc', limit=200)

        # ── Todos pendientes (para contadores) ──────────────────────────
        all_pending = self.search([
            ('state', 'in', ['pending', 'partial', 'overdue']),
        ])

        # ── Contenedores (impuestos) ────────────────────────────────────
        Container = self.env['purchase.order.container']
        containers = Container.search([], order='tax_paid_date desc, id desc', limit=100)

        # ── Tipo de cambio ──────────────────────────────────────────────
        usd_currency = self.env.ref('base.USD', raise_if_not_found=False)
        mxn_currency = self.env.ref('base.MXN', raise_if_not_found=False)
        rate = 17.33  # fallback
        if usd_currency and mxn_currency:
            try:
                rate = usd_currency._convert(
                    1.0, mxn_currency,
                    self.env.company, today,
                )
            except Exception:
                pass

        # ── Helper: schedule → dict ──────────────────────────────────────
        def _schedule_to_dict(s):
            return {
                'id': s.id,
                'order_id': [s.order_id.id, s.order_id.name] if s.order_id else False,
                'partner': s.order_id.partner_id.name if s.order_id and s.order_id.partner_id else '',
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

        # ── Clasificar líneas del mes ────────────────────────────────────
        advance_lines = []
        balance_lines = []

        for s in current_schedules:
            d = _schedule_to_dict(s)
            if s.payment_type in ('advance', 'second_advance'):
                advance_lines.append(d)
            else:
                balance_lines.append(d)

        # ── Impuestos ────────────────────────────────────────────────────
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

        # ── Resumen ejecutivo ────────────────────────────────────────────
        adv_usd = sum(l['amount'] for l in advance_lines)
        bal_usd = sum(l['amount'] for l in balance_lines)
        total_usd = adv_usd + bal_usd

        summary = {
            'total_usd': total_usd,
            'total_mxn': total_usd * rate + total_taxes,
            'credit_usd': 0,
            'credit_mxn': 0,
            'freight_sea_usd': 0,
            'freight_sea_mxn': 0,
            'freight_land_mxn': 0,
            'advances_usd': adv_usd,
            'advances_mxn': adv_usd * rate,
            'balances_usd': bal_usd,
            'balances_mxn': bal_usd * rate,
            'taxes_mxn': total_taxes,
        }

        # ── Contadores ──────────────────────────────────────────────────
        counters = {
            'total_schedules': len(all_pending),
            'pending': len(all_pending.filtered(lambda s: s.state == 'pending')),
            'partial': len(all_pending.filtered(lambda s: s.state == 'partial')),
            'overdue': len(all_pending.filtered(lambda s: s.state == 'overdue')),
            'paid': len(current_schedules.filtered(lambda s: s.state == 'paid')),
            'manual': len(all_pending.filtered(lambda s: s.is_manual)),
        }

        # ── Proyección meses futuros ────────────────────────────────────
        month_groups = {}
        for s in future_schedules:
            if not s.due_date:
                continue
            key = s.due_date.strftime('%Y-%m')
            if key not in month_groups:
                month_groups[key] = {'month': key, 'lines': [], 'total_usd': 0}
            month_groups[key]['lines'].append(_schedule_to_dict(s))
            month_groups[key]['total_usd'] += s.amount or 0

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
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers contables
    # ──────────────────────────────────────────────────────────────────────────

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
            [('code', 'like', '1140'), ('active', '=', True)], limit=1)
        if account:
            return account
        return self.env['account.account'].search(
            [('account_type', 'in', ['expense', 'asset_current']), ('active', '=', True)],
            limit=1)

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
        """
        Odoo 19: obtener el asiento contable de un pago de forma robusta.
        payment.move_id puede estar vacío en estado 'paid'.
        """
        # 1. Intento directo
        if payment.move_id:
            return payment.move_id

        # 2. Intento via move_ids (Many2many en algunas versiones)
        if hasattr(payment, 'move_ids') and payment.move_ids:
            return payment.move_ids[0]

        # 3. Búsqueda por nombre del pago (el asiento tiene el mismo name)
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

    # ──────────────────────────────────────────────────────────────────────────
    # Anticipo = Pago directo | Balance = Factura 100%
    # ──────────────────────────────────────────────────────────────────────────

    def _ensure_payment_or_invoice_exists(self):
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
        Crea pago directo (outbound) al proveedor SIN factura.
        destination_account_id = cuenta payable del proveedor (CRÍTICO para reconciliación).
        """
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

        _logger.info(
            '[SOMGROUP][ADVANCE] Using journal: %s (id=%s, type=%s)',
            journal.name, journal.id, journal.type,
        )

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

        # Forzar cuenta destino = payable del proveedor
        if payable_account and 'destination_account_id' in Payment._fields:
            payment_vals['destination_account_id'] = payable_account.id
            _logger.info(
                '[SOMGROUP][ADVANCE] Setting destination_account_id = %s (%s)',
                payable_account.id, payable_account.code,
            )

        if 'memo' in Payment._fields:
            payment_vals['memo'] = memo
        elif 'ref' in Payment._fields:
            payment_vals['ref'] = memo

        _logger.info('[SOMGROUP][ADVANCE] Payment vals: %s', payment_vals)

        payment = Payment.create(payment_vals)

        pay_move = self._get_payment_move(payment)
        if pay_move:
            pay_move.write({'ref': memo})

        _logger.info(
            '[SOMGROUP][ADVANCE] Payment created: %s (id=%s) | move: %s (id=%s)',
            payment.name, payment.id,
            pay_move.name if pay_move else 'N/A',
            pay_move.id if pay_move else 'N/A',
        )

        payment.action_post()

        _logger.info(
            '[SOMGROUP][ADVANCE] Payment after action_post: %s | state=%s',
            payment.name, payment.state,
        )

        if payment.state not in POSTED_STATES:
            _logger.warning(
                '[SOMGROUP][ADVANCE] Payment %s unexpected state: %s (expected %s)',
                payment.name, payment.state, POSTED_STATES,
            )

        # Log líneas contables del pago
        pay_move = self._get_payment_move(payment)
        if pay_move:
            for line in pay_move.line_ids:
                _logger.info(
                    '[SOMGROUP][ADVANCE] Move line: account=%s (%s) | debit=%s | credit=%s | '
                    'partner=%s | reconciled=%s | account_type=%s',
                    line.account_id.code, line.account_id.name,
                    line.debit, line.credit,
                    line.partner_id.name if line.partner_id else 'N/A',
                    line.reconciled, line.account_id.account_type,
                )

        self.write({
            'advance_payment_id': payment.id,
            'paid_amount': self.amount,
            'remaining_amount': 0.0,
            'state': 'paid',
            'paid_date': fields.Date.today(),
        })

        _logger.info('[SOMGROUP][ADVANCE] Schedule %s marked as paid.', self.id)
        return payment

    def _create_balance_invoice(self):
        """Crea factura al 100% del monto de la OC."""
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

        for line in invoice.invoice_line_ids:
            _logger.info(
                '[SOMGROUP][BALANCE] Invoice line: product=%s | qty=%s | price=%s | '
                'subtotal=%s | account=%s | purchase_line_id=%s',
                line.product_id.name if line.product_id else 'N/A',
                line.quantity, line.price_unit,
                line.price_subtotal,
                line.account_id.code if line.account_id else 'N/A',
                line.purchase_line_id.id if line.purchase_line_id else 'N/A',
            )

        return invoice

    def _reconcile_advances_to_invoice(self, invoice):
        """
        Reconcilia anticipos contra la factura de balance.
        
        ESTRATEGIA: En vez de buscar move_id del pago (falla en Odoo 19 estado 'paid'),
        buscamos directamente las account.move.line con débito en la cuenta payable
        del proveedor que NO estén reconciliadas. Estas son las contrapartidas de los
        pagos de anticipo.
        """
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
            '[SOMGROUP][RECONCILE] ═══ Starting reconciliation for invoice %s (id=%s) | '
            'OC: %s | amount_total=%s | amount_residual=%s | payable_account=%s',
            invoice.name, invoice.id, order.name,
            invoice.amount_total, invoice.amount_residual,
            payable_account.code if payable_account else 'NONE',
        )

        if not payable_account:
            _logger.error('[SOMGROUP][RECONCILE] No payable account found. Cannot reconcile.')
            return

        # ── Líneas payable de la factura (credit, sin reconciliar) ───────
        invoice_payable_lines = invoice.line_ids.filtered(
            lambda l: l.account_id == payable_account
            and not l.reconciled
        )

        _logger.info('[SOMGROUP][RECONCILE] Invoice payable lines: %d', len(invoice_payable_lines))
        for line in invoice_payable_lines:
            _logger.info(
                '[SOMGROUP][RECONCILE]   INV line id=%s | account=%s | debit=%s | credit=%s | '
                'amount_residual=%s | partner=%s',
                line.id, line.account_id.code, line.debit, line.credit,
                line.amount_residual, line.partner_id.name if line.partner_id else 'N/A',
            )

        if not invoice_payable_lines:
            _logger.warning('[SOMGROUP][RECONCILE] No unreconciled payable lines in invoice.')
            return

        # ── Calcular monto total de anticipos esperados ──────────────────
        advance_schedules = order.payment_schedule_ids.filtered(
            lambda s: s.payment_type in ('advance', 'second_advance')
            and s.advance_payment_id
            and s.advance_payment_id.state in POSTED_STATES
        )
        expected_advance_amount = sum(advance_schedules.mapped('amount'))

        _logger.info(
            '[SOMGROUP][RECONCILE] Expected advance amount from %d schedules: %s',
            len(advance_schedules), expected_advance_amount,
        )

        if expected_advance_amount <= 0:
            _logger.info('[SOMGROUP][RECONCILE] No confirmed advances. Nothing to reconcile.')
            return

        # ── ESTRATEGIA: Buscar líneas outstanding del proveedor ────────────
        all_unreconciled = self.env['account.move.line'].search([
            ('partner_id', '=', order.partner_id.id),
            ('reconciled', '=', False),
            ('parent_state', '=', 'posted'),
            ('move_id', '!=', invoice.id),
            ('amount_residual', '>', 0),
        ], order='date asc, id asc')

        _logger.info(
            '[SOMGROUP][RECONCILE] ALL unreconciled debit-residual lines for partner %s: %d',
            order.partner_id.name, len(all_unreconciled),
        )
        for line in all_unreconciled[:15]:
            _logger.info(
                '[SOMGROUP][RECONCILE][SCAN] line id=%s | account=%s (%s) | type=%s | '
                'debit=%s | credit=%s | amount_residual=%s | move=%s | ref=%s | name=%s',
                line.id, line.account_id.code, line.account_id.name,
                line.account_id.account_type,
                line.debit, line.credit, line.amount_residual,
                line.move_id.name, line.move_id.ref or 'N/A', line.name or 'N/A',
            )

        payment_debit_lines = self.env['account.move.line'].search([
            ('partner_id', '=', order.partner_id.id),
            ('account_id.account_type', '=', 'liability_payable'),
            ('reconciled', '=', False),
            ('parent_state', '=', 'posted'),
            ('move_id', '!=', invoice.id),
            ('amount_residual', '>', 0),
        ], order='date asc, id asc')

        _logger.info(
            '[SOMGROUP][RECONCILE] Found %d unreconciled liability_payable debit lines for partner %s',
            len(payment_debit_lines), order.partner_id.name,
        )

        # Filtrar solo las que corresponden a nuestros anticipos
        matched_lines = self.env['account.move.line']
        remaining_to_match = expected_advance_amount

        for line in payment_debit_lines:
            if remaining_to_match <= 0.01:
                break

            is_our_advance = False

            # Check 1: ref del move contiene el nombre de la OC
            if line.move_id.ref and order.name in line.move_id.ref:
                is_our_advance = True
                _logger.info(
                    '[SOMGROUP][RECONCILE] Line %s matched by move ref: %s',
                    line.id, line.move_id.ref,
                )

            # Check 2: el move tiene un payment vinculado a nuestro schedule
            if not is_our_advance:
                for sched in advance_schedules:
                    pay = sched.advance_payment_id
                    if pay.name and line.move_id.name == pay.name:
                        is_our_advance = True
                        _logger.info(
                            '[SOMGROUP][RECONCILE] Line %s matched by payment name: %s',
                            line.id, pay.name,
                        )
                        break

            # Check 3: memo/name contiene ANTICIPO y nombre de la OC
            if not is_our_advance:
                move_ref = line.move_id.ref or ''
                move_narration = line.move_id.narration or ''
                line_name = line.name or ''
                combined = f'{move_ref} {move_narration} {line_name}'.upper()
                if order.name.upper() in combined and 'ANTICIPO' in combined:
                    is_our_advance = True
                    _logger.info(
                        '[SOMGROUP][RECONCILE] Line %s matched by ANTICIPO keyword in texts',
                        line.id,
                    )

            # Check 4: monto exacto coincide con un anticipo y misma fecha
            if not is_our_advance:
                for sched in advance_schedules:
                    if abs(line.debit - sched.amount) < 0.01:
                        is_our_advance = True
                        _logger.info(
                            '[SOMGROUP][RECONCILE] Line %s matched by exact amount: %s',
                            line.id, line.debit,
                        )
                        break

            if is_our_advance:
                matched_lines |= line
                remaining_to_match -= line.amount_residual
                _logger.info(
                    '[SOMGROUP][RECONCILE] ✓ Matched line id=%s | amount_residual=%s | remaining=%s | '
                    'move=%s | ref=%s | account=%s',
                    line.id, line.amount_residual, remaining_to_match,
                    line.move_id.name, line.move_id.ref or 'N/A', line.account_id.code,
                )
            else:
                _logger.info(
                    '[SOMGROUP][RECONCILE] ✗ Skipped line id=%s | amount_residual=%s | move=%s | ref=%s | account=%s',
                    line.id, line.amount_residual, line.move_id.name, line.move_id.ref or 'N/A',
                    line.account_id.code,
                )

        if not matched_lines:
            _logger.warning(
                '[SOMGROUP][RECONCILE] No matching advance debit lines found for OC %s.',
                order.name,
            )
            for line in payment_debit_lines[:10]:
                _logger.warning(
                    '[SOMGROUP][RECONCILE][DIAG] Debit line id=%s | debit=%s | move=%s | '
                    'ref=%s | name=%s | date=%s',
                    line.id, line.debit, line.move_id.name,
                    line.move_id.ref or 'N/A', line.name or 'N/A', line.date,
                )
            return

        _logger.info(
            '[SOMGROUP][RECONCILE] Total matched debit lines: %d | Total residual: %s',
            len(matched_lines), sum(matched_lines.mapped('amount_residual')),
        )

        # ── Reconciliar ──────────────────────────────────────────────────
        inv_account = invoice_payable_lines[0].account_id
        same_account_lines = matched_lines.filtered(lambda l: l.account_id == inv_account)
        diff_account_lines = matched_lines.filtered(lambda l: l.account_id != inv_account)

        _logger.info(
            '[SOMGROUP][RECONCILE] Same account (%s): %d lines | Different account: %d lines',
            inv_account.code, len(same_account_lines), len(diff_account_lines),
        )

        # Caso 1: Líneas en la misma cuenta → reconciliar directamente
        if same_account_lines:
            lines_to_reconcile = invoice_payable_lines | same_account_lines
            _logger.info(
                '[SOMGROUP][RECONCILE] Reconciling %d lines on same account %s:',
                len(lines_to_reconcile), inv_account.code,
            )
            for line in lines_to_reconcile:
                _logger.info(
                    '[SOMGROUP][RECONCILE]   line id=%s | move=%s | debit=%s | credit=%s | '
                    'amount_residual=%s',
                    line.id, line.move_id.name, line.debit, line.credit, line.amount_residual,
                )
            try:
                lines_to_reconcile.reconcile()
                invoice.invalidate_recordset(['amount_residual', 'payment_state'])
                _logger.info(
                    '[SOMGROUP][RECONCILE] ✓ Direct reconciliation SUCCESS | '
                    'Invoice %s: residual=%s, payment_state=%s',
                    invoice.name, invoice.amount_residual, invoice.payment_state,
                )
            except Exception as e:
                _logger.error('[SOMGROUP][RECONCILE] ✗ Direct reconciliation FAILED: %s', e)

        # Caso 2: Líneas en cuenta diferente → usar js_assign_outstanding_line
        if diff_account_lines:
            _logger.info(
                '[SOMGROUP][RECONCILE] Attempting to apply %d outstanding lines via native method...',
                len(diff_account_lines),
            )
            for line in diff_account_lines:
                try:
                    if hasattr(invoice, 'js_assign_outstanding_line'):
                        invoice.js_assign_outstanding_line(line.id)
                        _logger.info(
                            '[SOMGROUP][RECONCILE] ✓ Applied outstanding line %s (amount_residual=%s) '
                            'to invoice %s via js_assign_outstanding_line',
                            line.id, line.amount_residual, invoice.name,
                        )
                    else:
                        _logger.warning(
                            '[SOMGROUP][RECONCILE] js_assign_outstanding_line not available. '
                            'Line %s (account=%s) cannot be auto-reconciled.',
                            line.id, line.account_id.code,
                        )
                except Exception as e:
                    _logger.error(
                        '[SOMGROUP][RECONCILE] ✗ Failed to apply outstanding line %s: %s',
                        line.id, e,
                    )

        invoice.invalidate_recordset(['amount_residual', 'payment_state'])
        _logger.info(
            '[SOMGROUP][RECONCILE] ═══ FINAL: Invoice %s | total=%s | residual=%s | state=%s',
            invoice.name, invoice.amount_total, invoice.amount_residual, invoice.payment_state,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Recompute de estados
    # ──────────────────────────────────────────────────────────────────────────

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
                # Anticipos con advance_payment_id confirmado
                if (schedule.payment_type in ('advance', 'second_advance')
                        and schedule.advance_payment_id
                        and schedule.advance_payment_id.state in POSTED_STATES):
                    _logger.info(
                        '[SOMGROUP][RECOMPUTE] schedule %s has confirmed advance %s (state=%s)',
                        schedule.id, schedule.advance_payment_id.name,
                        schedule.advance_payment_id.state,
                    )
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

                reconciled_advance_amount = 0.0
                if schedule.payment_type == 'balance' and schedule.schedule_invoice_id:
                    invoice = schedule.schedule_invoice_id
                    if invoice.state == 'posted':
                        reconciled_advance_amount = invoice.amount_total - invoice.amount_residual
                        reconciled_advance_amount = max(0, reconciled_advance_amount - inv_amount)
                        _logger.info(
                            '[SOMGROUP][RECOMPUTE] Schedule %s (balance) | invoice %s | '
                            'total=%s | residual=%s | inv_payments=%s | reconciled_advances=%s',
                            schedule.id, invoice.name,
                            invoice.amount_total, invoice.amount_residual,
                            inv_amount, reconciled_advance_amount,
                        )

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

                _logger.info(
                    '[SOMGROUP][RECOMPUTE] schedule %s (%s) | amount=%s | paid=%s | '
                    'remaining=%s | state=%s',
                    schedule.id, schedule.payment_type, schedule.amount,
                    schedule_paid, max(0.0, (schedule.amount or 0.0) - schedule_paid),
                    new_state,
                )

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
        self.ensure_one()
        if self.state == 'paid':
            raise UserError(_('Este hito ya está completamente pagado.'))

        if self.payment_type in ('advance', 'second_advance'):
            # Abrir formulario de pago pre-llenado para que el usuario elija el diario
            order = self.order_id
            memo = self._get_advance_memo()

            _logger.info(
                '[SOMGROUP][ADVANCE] Opening payment form for schedule %s | '
                'OC: %s | Partner: %s | Amount: %s | Memo: %s',
                self.id, order.name, order.partner_id.name, self.amount, memo,
            )

            payment_vals = {
                'default_payment_type': 'outbound',
                'default_partner_type': 'supplier',
                'default_partner_id': order.partner_id.id,
                'default_amount': self.amount,
                'default_currency_id': order.currency_id.id,
                'default_date': fields.Date.today(),
                'default_purchase_schedule_id': self.id,
            }

            # Establecer memo
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

        # Balance → necesita factura
        invoice = self._ensure_payment_or_invoice_exists()

        if not isinstance(invoice, type(self.env['account.move'])):
            return {'type': 'ir.actions.client', 'tag': 'reload'}

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

        _logger.info(
            '[SOMGROUP][PAY_BALANCE] Opening payment wizard for invoice %s | '
            'amount_total=%s | amount_residual=%s | payment_state=%s',
            invoice.name, invoice.amount_total, invoice.amount_residual,
            invoice.payment_state,
        )

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