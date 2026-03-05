/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

// ─────────────────────────────────────────────────────────────────────────────
// SOMGROUP — Reporte de Pagos a Proveedores
// Dashboard con resumen ejecutivo + detalle por sección + proyección multi-mes
// ─────────────────────────────────────────────────────────────────────────────

class PaymentReportDashboard extends Component {
    static template = "somgroup_import.PaymentReportDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            loading: true,
            // Filtros
            selectedMonth: this._getCurrentMonth(),
            selectedYear: this._getCurrentYear(),
            availableMonths: [],
            // Resumen ejecutivo
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
            // Contadores
            counters: {
                total_schedules: 0,
                pending: 0,
                partial: 0,
                paid: 0,
                overdue: 0,
                manual: 0,
            },
            // Detalle por sección
            credit_lines: [],
            freight_sea_lines: [],
            freight_land_lines: [],
            advance_lines: [],
            balance_lines: [],
            tax_lines: [],
            // Proyección meses futuros
            future_months: [],
            // Vista activa
            activeTab: "summary",
            // Exchange rate
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

    get monthName() {
        const months = [
            "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
            "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
        ];
        return months[this.state.selectedMonth] || "";
    }

    get formattedDate() {
        return `${this.monthName} ${this.state.selectedYear}`;
    }

    // ── Carga de datos ──────────────────────────────────────────────────

    async _loadData() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "purchase.payment.schedule",
                "get_payment_report_data",
                [],
                {
                    month: this.state.selectedMonth,
                    year: this.state.selectedYear,
                }
            );
            this._applyData(data);
        } catch (e) {
            console.error("Error loading payment report data:", e);
            // Fallback: cargar desde schedules directamente
            await this._loadFromSchedules();
        }
        this.state.loading = false;
    }

    async _loadFromSchedules() {
        try {
            const month = this.state.selectedMonth;
            const year = this.state.selectedYear;
            const startDate = `${year}-${String(month).padStart(2, "0")}-01`;
            const endMonth = month === 12 ? 1 : month + 1;
            const endYear = month === 12 ? year + 1 : year;
            const endDate = `${endYear}-${String(endMonth).padStart(2, "0")}-01`;

            // Schedules del mes actual
            const currentSchedules = await this.orm.searchRead(
                "purchase.payment.schedule",
                [
                    ["due_date", ">=", startDate],
                    ["due_date", "<", endDate],
                ],
                [
                    "order_id", "payment_type", "percent", "amount",
                    "currency_id", "due_date", "state", "paid_amount",
                    "remaining_amount", "is_manual", "note",
                    "days_until_due", "alert_color",
                ],
                { order: "due_date asc, id asc" }
            );

            // Schedules futuros
            const futureSchedules = await this.orm.searchRead(
                "purchase.payment.schedule",
                [
                    ["due_date", ">=", endDate],
                    ["state", "in", ["pending", "partial", "overdue"]],
                ],
                [
                    "order_id", "payment_type", "percent", "amount",
                    "currency_id", "due_date", "state", "paid_amount",
                    "remaining_amount", "is_manual", "note",
                ],
                { order: "due_date asc", limit: 200 }
            );

            // Todos los schedules para contadores
            const allPending = await this.orm.searchRead(
                "purchase.payment.schedule",
                [["state", "in", ["pending", "partial", "overdue"]]],
                ["id", "state", "is_manual"],
                { limit: 500 }
            );

            // Containers (impuestos)
            const containers = await this.orm.searchRead(
                "purchase.order.container",
                [],
                ["name", "order_id", "container_type", "tax_amount",
                 "tax_state", "tax_paid_date", "pedimento", "notes"],
                { order: "tax_paid_date desc, id desc", limit: 100 }
            );

            // Procesar datos
            this._processSchedules(currentSchedules, futureSchedules, allPending, containers);
        } catch (e) {
            console.error("Error loading schedules:", e);
        }
    }

    _processSchedules(currentSchedules, futureSchedules, allPending, containers) {
        const s = this.state;

        // Contadores globales
        s.counters.total_schedules = allPending.length;
        s.counters.pending = allPending.filter((r) => r.state === "pending").length;
        s.counters.partial = allPending.filter((r) => r.state === "partial").length;
        s.counters.overdue = allPending.filter((r) => r.state === "overdue").length;
        s.counters.paid = currentSchedules.filter((r) => r.state === "paid").length;
        s.counters.manual = allPending.filter((r) => r.is_manual).length;

        // Clasificar líneas del mes actual
        s.advance_lines = currentSchedules.filter(
            (r) => r.payment_type === "advance" || r.payment_type === "second_advance"
        );
        s.balance_lines = currentSchedules.filter(
            (r) => r.payment_type === "balance"
        );

        // Para crédito vs fletes, usamos la nota o el nombre de la OC
        // En este punto no diferenciamos fletes — se muestran todos en balance
        s.credit_lines = s.balance_lines;
        s.freight_sea_lines = [];
        s.freight_land_lines = [];

        // Impuestos
        s.tax_lines = containers.map((c) => ({
            id: c.id,
            container: c.name,
            order: c.order_id ? c.order_id[1] : "",
            type: c.container_type,
            tax_amount: c.tax_amount || 0,
            state: c.tax_state,
            paid_date: c.tax_paid_date,
            pedimento: c.pedimento,
            notes: c.notes,
        }));

        // Resumen ejecutivo
        const rate = s.exchange_rate;
        let totalUSD = 0;
        for (const line of currentSchedules) {
            totalUSD += line.amount || 0;
        }
        const advUSD = s.advance_lines.reduce((a, l) => a + (l.amount || 0), 0);
        const balUSD = s.balance_lines.reduce((a, l) => a + (l.amount || 0), 0);
        const taxMXN = s.tax_lines.reduce((a, l) => a + (l.tax_amount || 0), 0);

        s.summary.total_usd = totalUSD;
        s.summary.total_mxn = totalUSD * rate + taxMXN;
        s.summary.advances_usd = advUSD;
        s.summary.advances_mxn = advUSD * rate;
        s.summary.balances_usd = balUSD;
        s.summary.balances_mxn = balUSD * rate;
        s.summary.taxes_mxn = taxMXN;

        // Proyección meses futuros
        const monthGroups = {};
        for (const sched of futureSchedules) {
            if (!sched.due_date) continue;
            const d = new Date(sched.due_date);
            const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
            if (!monthGroups[key]) {
                monthGroups[key] = { month: key, lines: [], total_usd: 0 };
            }
            monthGroups[key].lines.push(sched);
            monthGroups[key].total_usd += sched.amount || 0;
        }
        s.future_months = Object.values(monthGroups).sort((a, b) =>
            a.month.localeCompare(b.month)
        );
    }

    _applyData(data) {
        if (!data) return;
        Object.assign(this.state.summary, data.summary || {});
        Object.assign(this.state.counters, data.counters || {});
        this.state.credit_lines = data.credit_lines || [];
        this.state.freight_sea_lines = data.freight_sea_lines || [];
        this.state.freight_land_lines = data.freight_land_lines || [];
        this.state.advance_lines = data.advance_lines || [];
        this.state.balance_lines = data.balance_lines || [];
        this.state.tax_lines = data.tax_lines || [];
        this.state.future_months = data.future_months || [];
    }

    // ── Formateo ────────────────────────────────────────────────────────

    formatCurrency(value, currency) {
        if (!value && value !== 0) return "—";
        const sym = currency === "MXN" ? "$" : (currency === "EUR" ? "€" : "$");
        const suffix = currency ? ` ${currency}` : "";
        return `${sym}${Number(value).toLocaleString("en-US", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        })}${suffix}`;
    }

    formatUSD(value) {
        return this.formatCurrency(value, "USD");
    }

    formatMXN(value) {
        return this.formatCurrency(value, "MXN");
    }

    formatDate(dateStr) {
        if (!dateStr) return "—";
        const d = new Date(dateStr + "T12:00:00");
        return d.toLocaleDateString("es-MX", {
            day: "2-digit",
            month: "short",
            year: "numeric",
        });
    }

    getStateLabel(state) {
        const labels = {
            pending: "Pendiente",
            partial: "Parcial",
            paid: "Pagado",
            overdue: "Vencido",
        };
        return labels[state] || state;
    }

    getStateClass(state) {
        const cls = {
            pending: "sg-badge--pending",
            partial: "sg-badge--partial",
            paid: "sg-badge--paid",
            overdue: "sg-badge--overdue",
        };
        return `sg-badge ${cls[state] || ""}`;
    }

    getTypeLabel(type) {
        const labels = {
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
        const [y, m] = monthKey.split("-");
        const months = [
            "", "Ene", "Feb", "Mar", "Abr", "May", "Jun",
            "Jul", "Ago", "Sep", "Oct", "Nov", "Dic",
        ];
        return `${months[parseInt(m)]} ${y}`;
    }

    // ── Navegación ──────────────────────────────────────────────────────

    setTab(tab) {
        this.state.activeTab = tab;
    }

    async changeMonth(delta) {
        let m = this.state.selectedMonth + delta;
        let y = this.state.selectedYear;
        if (m > 12) { m = 1; y++; }
        if (m < 1) { m = 12; y--; }
        this.state.selectedMonth = m;
        this.state.selectedYear = y;
        await this._loadData();
    }

    async refresh() {
        await this._loadData();
    }

    // ── Acciones ────────────────────────────────────────────────────────

    openSchedule(scheduleId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "purchase.payment.schedule",
            res_id: scheduleId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openOrder(orderId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "purchase.order",
            res_id: orderId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openAllSchedules(domain) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "purchase.payment.schedule",
            views: [[false, "list"], [false, "form"]],
            domain: domain || [],
            target: "current",
            name: _t("Pagos Programados"),
        });
    }

    openPendingSchedules() {
        this.openAllSchedules([["state", "in", ["pending", "partial"]]]);
    }

    openOverdueSchedules() {
        this.openAllSchedules([["state", "=", "overdue"]]);
    }

    openPaidSchedules() {
        const month = this.state.selectedMonth;
        const year = this.state.selectedYear;
        const startDate = `${year}-${String(month).padStart(2, "0")}-01`;
        const endMonth = month === 12 ? 1 : month + 1;
        const endYear = month === 12 ? year + 1 : year;
        const endDate = `${endYear}-${String(endMonth).padStart(2, "0")}-01`;
        this.openAllSchedules([
            ["state", "=", "paid"],
            ["due_date", ">=", startDate],
            ["due_date", "<", endDate],
        ]);
    }

    async exportReport() {
        // Trigger print/export
        window.print();
    }
}

PaymentReportDashboard.template = "somgroup_import.PaymentReportDashboard";

registry.category("actions").add("somgroup_payment_report_dashboard", PaymentReportDashboard);