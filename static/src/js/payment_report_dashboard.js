/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart, onMounted, useRef } from "@odoo/owl";

class PaymentReportDashboard extends Component {

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.rootRef = useRef("rootEl");

        onMounted(() => {
            this._fixScroll();
        });

        this.state = useState({
            loading: true,
            selectedMonth: this._getCurrentMonth(),
            selectedYear: this._getCurrentYear(),
            selectedScope: "import",
            summary: {
                total_usd: 0,
                total_mxn: 0,
                credit_usd: 0,
                credit_mxn: 0,
                freight_sea_usd: 0,
                freight_sea_mxn: 0,
                freight_land_mxn: 0,
                advances_usd: 0,
                advances_mxn: 0,
                balances_usd: 0,
                balances_mxn: 0,
                taxes_mxn: 0,
            },
            counters: {
                total_schedules: 0,
                pending: 0,
                partial: 0,
                paid: 0,
                overdue: 0,
                manual: 0,
            },
            advance_lines: [],
            balance_lines: [],
            tax_lines: [],
            future_months: [],
            activeTab: "advances",
            exchange_rate: 17.33,
        });

        onWillStart(async () => {
            await this._loadData();
        });
    }

    _getCurrentMonth() {
        return new Date().getMonth() + 1;
    }

    _getCurrentYear() {
        return new Date().getFullYear();
    }

    _fixScroll() {
        var el = this.rootRef.el;
        if (!el) { return; }

        var parent = el.parentElement;
        var maxLevels = 10;
        var i = 0;

        while (parent && i < maxLevels) {
            var cls = parent.className || "";
            if (
                cls.indexOf("o_action_manager") !== -1 ||
                cls.indexOf("o_action") !== -1 ||
                cls.indexOf("o_content") !== -1 ||
                cls.indexOf("o_client_action") !== -1
            ) {
                parent.style.overflow = "auto";
                parent.style.maxHeight = "none";
                parent.style.height = "auto";
            }
            parent = parent.parentElement;
            i++;
        }
    }

    get monthName() {
        var months = [
            "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
            "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
        ];
        return months[this.state.selectedMonth] || "";
    }

    get formattedDate() {
        return this.monthName + " " + this.state.selectedYear;
    }

    get scopeLabel() {
        if (this.state.selectedScope === "import") {
            return "Importación";
        }
        if (this.state.selectedScope === "national") {
            return "Nacional";
        }
        return "Todo";
    }

    _getScopeDomain() {
        if (this.state.selectedScope === "all") {
            return [];
        }
        return [["purchase_payment_scope", "=", this.state.selectedScope]];
    }

    _getContainerDomain() {
        if (this.state.selectedScope === "national") {
            return [["id", "=", 0]];
        }
        if (this.state.selectedScope === "import") {
            return [["purchase_payment_scope", "=", "import"]];
        }
        return [];
    }

    async _loadData() {
        this.state.loading = true;

        try {
            var data = await this.orm.call(
                "purchase.payment.schedule",
                "get_payment_report_data",
                [],
                {
                    month: this.state.selectedMonth,
                    year: this.state.selectedYear,
                    scope: this.state.selectedScope,
                }
            );
            this._applyData(data);
        } catch (e) {
            console.error("[SOMGROUP] Error loading report data via RPC, falling back:", e);
            await this._loadFromSchedules();
        }

        this.state.loading = false;
    }

    async _loadFromSchedules() {
        try {
            var month = this.state.selectedMonth;
            var year = this.state.selectedYear;
            var startDate = year + "-" + String(month).padStart(2, "0") + "-01";
            var endMonth = month === 12 ? 1 : month + 1;
            var endYear = month === 12 ? year + 1 : year;
            var endDate = endYear + "-" + String(endMonth).padStart(2, "0") + "-01";

            var scopeDomain = this._getScopeDomain();

            var currentSchedules = await this.orm.searchRead(
                "purchase.payment.schedule",
                [
                    ["due_date", ">=", startDate],
                    ["due_date", "<", endDate],
                ].concat(scopeDomain),
                [
                    "order_id", "partner_id", "purchase_payment_scope",
                    "payment_type", "percent", "amount",
                    "currency_id", "due_date", "state", "paid_amount",
                    "remaining_amount", "is_manual", "note",
                    "days_until_due", "alert_color",
                ],
                { order: "due_date asc, id asc" }
            );

            var futureSchedules = await this.orm.searchRead(
                "purchase.payment.schedule",
                [
                    ["due_date", ">=", endDate],
                    ["state", "in", ["pending", "partial", "overdue"]],
                ].concat(scopeDomain),
                [
                    "order_id", "partner_id", "purchase_payment_scope",
                    "payment_type", "percent", "amount",
                    "currency_id", "due_date", "state", "paid_amount",
                    "remaining_amount", "is_manual", "note",
                ],
                { order: "due_date asc", limit: 200 }
            );

            var allPending = await this.orm.searchRead(
                "purchase.payment.schedule",
                [["state", "in", ["pending", "partial", "overdue"]]].concat(scopeDomain),
                ["id", "state", "is_manual"],
                { limit: 500 }
            );

            var containers = await this.orm.searchRead(
                "purchase.order.container",
                this._getContainerDomain(),
                [
                    "name", "order_id", "purchase_payment_scope",
                    "container_type", "tax_amount",
                    "tax_state", "tax_paid_date", "pedimento", "notes",
                ],
                { order: "tax_paid_date desc, id desc", limit: 100 }
            );

            this._processSchedules(currentSchedules, futureSchedules, allPending, containers);
        } catch (e) {
            console.error("[SOMGROUP] Error in fallback loading:", e);
        }
    }

    _getCurrencyName(record) {
        if (!record) {
            return "USD";
        }

        if (record.currency_name) {
            return record.currency_name;
        }

        if (Array.isArray(record.currency_id)) {
            return record.currency_id[1] || "USD";
        }

        if (typeof record.currency_id === "string") {
            return record.currency_id;
        }

        return "USD";
    }

    _amountPair(amount, currency) {
        amount = amount || 0;
        currency = currency || "USD";

        if (currency === "MXN") {
            return {
                usd: this.state.exchange_rate ? amount / this.state.exchange_rate : 0,
                mxn: amount,
            };
        }

        return {
            usd: amount,
            mxn: amount * this.state.exchange_rate,
        };
    }

    _processSchedules(currentSchedules, futureSchedules, allPending, containers) {
        var s = this.state;

        s.counters.total_schedules = allPending.length;
        s.counters.pending = allPending.filter(function (r) { return r.state === "pending"; }).length;
        s.counters.partial = allPending.filter(function (r) { return r.state === "partial"; }).length;
        s.counters.overdue = allPending.filter(function (r) { return r.state === "overdue"; }).length;
        s.counters.paid = currentSchedules.filter(function (r) { return r.state === "paid"; }).length;
        s.counters.manual = allPending.filter(function (r) { return r.is_manual; }).length;

        s.advance_lines = currentSchedules.filter(function (r) {
            return r.payment_type === "advance" || r.payment_type === "second_advance";
        });

        s.balance_lines = currentSchedules.filter(function (r) {
            return r.payment_type === "balance";
        });

        s.tax_lines = containers.map(function (c) {
            return {
                id: c.id,
                container: c.name,
                order: c.order_id ? c.order_id[1] : "",
                type: c.container_type,
                tax_amount: c.tax_amount || 0,
                state: c.tax_state,
                paid_date: c.tax_paid_date,
                pedimento: c.pedimento,
                notes: c.notes,
            };
        });

        var advUSD = 0;
        var advMXN = 0;
        var balUSD = 0;
        var balMXN = 0;
        var taxMXN = 0;
        var i;
        var pair;
        var currency;

        for (i = 0; i < s.advance_lines.length; i++) {
            currency = this._getCurrencyName(s.advance_lines[i]);
            pair = this._amountPair(s.advance_lines[i].amount, currency);
            advUSD += pair.usd;
            advMXN += pair.mxn;
        }

        for (i = 0; i < s.balance_lines.length; i++) {
            currency = this._getCurrencyName(s.balance_lines[i]);
            pair = this._amountPair(s.balance_lines[i].amount, currency);
            balUSD += pair.usd;
            balMXN += pair.mxn;
        }

        for (i = 0; i < s.tax_lines.length; i++) {
            taxMXN += s.tax_lines[i].tax_amount || 0;
        }

        s.summary.total_usd = advUSD + balUSD;
        s.summary.total_mxn = advMXN + balMXN + taxMXN;
        s.summary.advances_usd = advUSD;
        s.summary.advances_mxn = advMXN;
        s.summary.balances_usd = balUSD;
        s.summary.balances_mxn = balMXN;
        s.summary.taxes_mxn = taxMXN;

        var monthGroups = {};

        for (i = 0; i < futureSchedules.length; i++) {
            var sched = futureSchedules[i];
            if (!sched.due_date) { continue; }

            var d = new Date(sched.due_date);
            var key = d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0");

            if (!monthGroups[key]) {
                monthGroups[key] = {
                    month: key,
                    lines: [],
                    total_usd: 0,
                    total_mxn: 0,
                };
            }

            currency = this._getCurrencyName(sched);
            pair = this._amountPair(sched.amount, currency);

            monthGroups[key].lines.push(sched);
            monthGroups[key].total_usd += pair.usd;
            monthGroups[key].total_mxn += pair.mxn;
        }

        s.future_months = Object.values(monthGroups).sort(function (a, b) {
            return a.month.localeCompare(b.month);
        });
    }

    _applyData(data) {
        if (!data) { return; }

        Object.assign(this.state.summary, data.summary || {});
        Object.assign(this.state.counters, data.counters || {});

        this.state.advance_lines = data.advance_lines || [];
        this.state.balance_lines = data.balance_lines || [];
        this.state.tax_lines = data.tax_lines || [];
        this.state.future_months = data.future_months || [];

        if (data.exchange_rate) {
            this.state.exchange_rate = data.exchange_rate;
        }
    }

    formatCurrency(value, currency) {
        if (!value && value !== 0) { return "\u2014"; }

        currency = currency || "USD";

        var sym = currency === "MXN" ? "$" : (currency === "EUR" ? "\u20ac" : "$");
        var suffix = currency ? " " + currency : "";

        return sym + Number(value).toLocaleString("en-US", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        }) + suffix;
    }

    formatUSD(value) {
        return this.formatCurrency(value, "USD");
    }

    formatMXN(value) {
        return this.formatCurrency(value, "MXN");
    }

    formatLineAmount(line, fieldName) {
        return this.formatCurrency(line[fieldName], this._getCurrencyName(line));
    }

    formatFutureTotals(monthData) {
        return this.formatUSD(monthData.total_usd) + " / " + this.formatMXN(monthData.total_mxn);
    }

    formatDate(dateStr) {
        if (!dateStr) { return "\u2014"; }

        var d = new Date(dateStr + "T12:00:00");

        return d.toLocaleDateString("es-MX", {
            day: "2-digit",
            month: "short",
            year: "numeric",
        });
    }

    getStateLabel(state) {
        var labels = {
            pending: "Pendiente",
            partial: "Parcial",
            paid: "Pagado",
            overdue: "Vencido",
        };
        return labels[state] || state;
    }

    getStateClass(state) {
        var cls = {
            pending: "sg-badge--pending",
            partial: "sg-badge--partial",
            paid: "sg-badge--paid",
            overdue: "sg-badge--overdue",
        };
        return "sg-badge " + (cls[state] || "");
    }

    getTypeLabel(type) {
        var labels = {
            advance: "Anticipo",
            second_advance: "2do Tramo",
            balance: "Balance",
        };
        return labels[type] || type;
    }

    getTaxStateClass(state) {
        return state === "paid" ? "sg-badge sg-badge--paid" : "sg-badge sg-badge--pending";
    }

    getMonthLabel(monthKey) {
        var parts = monthKey.split("-");
        var months = [
            "", "Ene", "Feb", "Mar", "Abr", "May", "Jun",
            "Jul", "Ago", "Sep", "Oct", "Nov", "Dic",
        ];
        return months[parseInt(parts[1])] + " " + parts[0];
    }

    onPrevMonth() {
        this.changeMonth(-1);
    }

    onNextMonth() {
        this.changeMonth(1);
    }

    async changeMonth(delta) {
        var m = this.state.selectedMonth + delta;
        var y = this.state.selectedYear;

        if (m > 12) {
            m = 1;
            y++;
        }

        if (m < 1) {
            m = 12;
            y--;
        }

        this.state.selectedMonth = m;
        this.state.selectedYear = y;

        await this._loadData();
    }

    async onRefresh() {
        await this._loadData();
    }

    onExport() {
        window.print();
    }

    async setScopeAll() {
        this.state.selectedScope = "all";
        await this._loadData();
    }

    async setScopeImport() {
        this.state.selectedScope = "import";
        await this._loadData();
    }

    async setScopeNational() {
        this.state.selectedScope = "national";
        await this._loadData();
    }

    setTabAdvances() {
        this.state.activeTab = "advances";
    }

    setTabBalances() {
        this.state.activeTab = "balances";
    }

    setTabTaxes() {
        this.state.activeTab = "taxes";
    }

    setTabFuture() {
        this.state.activeTab = "future";
    }

    onClickSchedule(ev) {
        var scheduleId = parseInt(ev.currentTarget.dataset.scheduleId);

        if (scheduleId) {
            this.action.doAction({
                type: "ir.actions.act_window",
                res_model: "purchase.payment.schedule",
                res_id: scheduleId,
                views: [[false, "form"]],
                target: "current",
            });
        }
    }

    onClickPending() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "purchase.payment.schedule",
            views: [[false, "list"], [false, "form"]],
            domain: [["state", "in", ["pending", "partial"]]].concat(this._getScopeDomain()),
            target: "current",
            name: "Pagos Pendientes",
        });
    }

    onClickOverdue() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "purchase.payment.schedule",
            views: [[false, "list"], [false, "form"]],
            domain: [["state", "=", "overdue"]].concat(this._getScopeDomain()),
            target: "current",
            name: "Pagos Vencidos",
        });
    }

    onClickPaid() {
        var month = this.state.selectedMonth;
        var year = this.state.selectedYear;
        var startDate = year + "-" + String(month).padStart(2, "0") + "-01";
        var endMonth = month === 12 ? 1 : month + 1;
        var endYear = month === 12 ? year + 1 : year;
        var endDate = endYear + "-" + String(endMonth).padStart(2, "0") + "-01";

        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "purchase.payment.schedule",
            views: [[false, "list"], [false, "form"]],
            domain: [
                ["state", "=", "paid"],
                ["due_date", ">=", startDate],
                ["due_date", "<", endDate],
            ].concat(this._getScopeDomain()),
            target: "current",
            name: "Pagos del Mes",
        });
    }
}

PaymentReportDashboard.template = "somgroup_import.PaymentReportDashboard";
PaymentReportDashboard.props = { "*": true };

registry.category("actions").add("somgroup_payment_report_dashboard", PaymentReportDashboard);