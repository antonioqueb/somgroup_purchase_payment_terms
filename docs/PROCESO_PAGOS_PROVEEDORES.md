# Pagos a proveedores en SOMGROUP — panorama completo

**Alcance:** compras nacionales y de importación · Odoo 19 Enterprise · módulos `somgroup_purchase_payment_terms` (19.0.2.21.0) y `purchase_payment_report`
**Fecha:** 12 sep 2026 (refleja la revisión de lógica aplicada ese día)
**Audiencia:** Dirección, Compras, Tesorería y Contabilidad

---

## 1. Idea general

Cada orden de compra (OC) confirmada lleva un **Calendario de Pagos**: una lista de **hitos** (anticipo, segundo tramo, balance) con su porcentaje, monto, fecha límite y estado. El calendario se genera solo a partir del **término de pago** de la OC y de las fechas logísticas que aplican (fecha BL, ETA, factura del proveedor, recepción). Tesorería paga contra esos hitos, Contabilidad factura y concilia, y todos ven el mismo calendario en la OC, en el menú *Compras › Calendario de Pagos* y en el *Reporte de Pagos*.

```
Término de pago + fechas logísticas ──▶ Calendario (hitos) ──▶ Pago / Factura ──▶ Estado del hito
        ▲                                                                              │
        └──────────────── recálculo automático al cambiar datos ◀──────────────────────┘
```

Dos flujos, un solo motor:

| | Importación | Nacional |
|---|---|---|
| Divisa | Extranjera (USD por defecto; EUR u otra activa) | Moneda de la compañía (MXN) |
| Fechas que gobiernan | Fecha BL, ETA, fecha de factura del proveedor | Base elegida: fecha OC, confirmación, factura del proveedor, recepción esperada, recepción real o fecha manual |
| Extras | Contenedores, pedimento e impuestos de importación, Telex Release | Nota de pago nacional |

---

## 2. Clasificación de la compra y divisa

- Cada OC tiene **Tipo de Compra**: *Importación* o *Nacional*. Se captura en la OC y equivale al indicador "Es orden de importación".
- **La divisa la gobierna el tipo.** Nacional solo admite la moneda de la compañía; Importación solo divisas extranjeras. Al cambiar el tipo o el proveedor, la divisa se corrige sola; si alguien fuerza una divisa no permitida, el sistema la restablece y avisa. El servidor lo valida también en cargas por RPC.
- Cuando una OC nace por código (proformas, restock, tarifario) sin tipo explícito, el tipo se **infiere de la divisa**.

---

## 3. Términos de pago: catálogo y fórmulas

El término de pago de Odoo se extiende con un **Tipo SOMGROUP**, un **% de anticipo**, un **% de segundo tramo**, **días para balance**, **días antes de ETA/recepción** y, para nacionales, la **base de vencimiento**. Cada término declara si aplica a Importación, Nacional o ambos, y si se ofrece en Compras, Ventas o ambos.

| Tipo | Hitos que genera | Fecha límite del balance | Datos que exige |
|---|---|---|---|
| 100 % Pago Anticipado | Anticipo 100 % | Fecha de la OC | — |
| Importación: N días después de BL | Balance 100 % | Fecha BL + N días | Fecha BL |
| Importación: N días después de Fecha Factura | Balance 100 % | Factura proveedor + N días | Fecha factura proveedor |
| Importación: Contra Entrega / CAD / Contra BL | Anticipo % (opcional) + Balance | ETA − días antes (7 por defecto) | ETA |
| Importación: Anticipo + Balance | Anticipo % + Balance | Fecha BL + N días; si no hay BL, ETA − días antes | BL o ETA |
| Importación: Anticipo + Saldo a N días Factura | Anticipo % + Balance | Factura proveedor + N días | Fecha factura proveedor |
| Importación: Anticipo + Saldo N días después Arribo | Anticipo % + Segundo tramo % (contra entrega) + Balance | ETA + N días; segundo tramo ETA − días antes | ETA |
| Nacional: N días después de base | Balance 100 % | Base + N días | La base elegida |
| Nacional: Contra recepción / entrega | Anticipo % (opcional) + Balance | Recepción − días antes | Recepción esperada o real |
| Nacional: Anticipo + saldo | Anticipo % + Balance | Base + N días | La base elegida |
| Estándar Odoo | Balance 100 % sin fecha | El motor nativo de Odoo | — |

**Reglas de cálculo de montos**

- La base es el **total de la OC con impuestos** (`amount_total`).
- Anticipo = total × %. Segundo tramo = total × %.
- **El último balance cierra contra el total**: los tramos se redondean en la moneda de la OC y el balance absorbe el residuo, de modo que la suma de hitos siempre es igual al total.
- Si la suma de anticipo y segundo tramo supera 100 %, el término está mal capturado y el cálculo se detiene con error.

**Reglas de fechas**

- El anticipo vence en la **fecha de la OC** y siempre es de programación manual (Tesorería decide cuándo se paga).
- Si falta el dato que el término necesita (BL, ETA, factura, recepción), el hito nace **sin fecha**, marcado como *manual* y con la nota "Capture … para calcular vencimiento". No se usa ninguna fecha sustituta.
- La nota operativa de cada hito explica la fórmula aplicada (ejemplo: "Pago nacional a 30 días de Fecha Factura Proveedor").
- Al confirmar la OC: para nacionales, la base de vencimiento se copia del término a la OC y puede cambiarse en la OC.

**Términos sembrados** (los que trae el módulo): 30 % anticipo / 70 % 90 días BL · 30 % anticipo / 70 % contraentrega · 50/50 contraentrega · 90 días después de factura · 20/80 contraentrega · 30 % anticipo / 70 % una semana después de arribo · 30, 90, 120 y 150 días después de BL · 50 % anticipo / 50 % 90 días factura · 100 % anticipado · 30 % anticipo / 70 % CAD · 50 % anticipo / 25 % contraentrega / 25 % 60 días · CAD 100 % · Nacional 30 % anticipo / 70 % 30 días factura · Nacional fecha de referencia manual.

---

## 4. Cuándo se calcula y recalcula el calendario

1. **Botón "Calcular / Recalcular Calendario"** en la pestaña *Pagos SOMGROUP* de la OC.
2. **Automático** al guardar cambios en: tipo de compra, término de pago, fecha BL, ETA, fecha de factura del proveedor, base nacional, recepción esperada o real, fecha de referencia, y **líneas de la OC solo si cambió el total** (editar una descripción no regenera nada).

**Protecciones**

- Si algún hito ya tiene **pago o factura ligados**, el calendario **no se regenera**: el botón lo dice con error y el guardado deja un aviso en el chatter para ajustar los hitos pendientes a mano.
- Se regeneran únicamente los hitos **pendientes o vencidos sin pago**. Si había hitos capturados a mano (fecha, monto o referencia), el chatter avisa que fueron reemplazados.
- **Balance que se cuadra solo:** al editar el % o el monto de un anticipo en la lista (por ejemplo se pagó de más o de menos), la línea de balance no pagada absorbe la diferencia para que el calendario siga cerrando contra el total. Editar el % recalcula el monto y viceversa.
- Al **cancelar la OC** se eliminan los hitos limpios; los que tienen pago o factura se conservan como historial y el reporte excluye la OC cancelada.

---

## 5. Vida de un hito

| Estado | Significado | Quién lo pone |
|---|---|---|
| Pendiente | Sin pago | Al crearse |
| Pago parcial | Pagado menos del monto | Sincronización con contabilidad |
| Pagado | Pagado el monto completo (tolerancia de redondeo) | Sincronización o "Marcar pagado" |
| Vencido | Sin pagar y fecha límite pasada | **Cron diario**; regresa a Pendiente si la fecha se mueve al futuro |

Campos que acompañan al hito: fecha límite, **días para vencer** (rojo si venció, naranja si vence en 7 días), monto pagado, **saldo pendiente** (siempre monto menos pagado), fecha real de pago, referencia SPEI, nota, y las ligas al pago de anticipo, a la factura del hito y a los pagos contables.

En la OC se calculan **Monto anticipo**, **Monto balance**, **Próximo pago**, **Pagos vencidos** y un **Aviso de pago**: dato base faltante, vencidos en rojo o "vence en 7 días" en amarillo. Los hitos parciales y vencidos cuentan para esas alertas.

---

## 6. Cómo se paga cada tipo de hito

### 6.1 Anticipos y segundos tramos

1. Tesorería pulsa **Pagar** en el hito. Se abre el formulario de **pago a proveedor** precargado: proveedor, monto del hito, divisa de la OC, fecha de hoy, memo "ANTICIPO OC — tipo (%)", compañía de la OC. Tesorería elige diario y confirma.
2. Al **confirmar el pago**, el hito se liga a ese pago y toma el **monto real pagado**, convertido a la moneda del hito si el pago fue en otra divisa. Si no cubre el hito completo queda en *Pago parcial*.
3. **Ver Doc.** abre el pago de anticipo. **Ver Pagos** lista los pagos contables del hito.
4. Cancelar el pago devuelve el hito a su estado real.

> Nunca se crea ni contabiliza un anticipo sin que el usuario elija diario, fecha y monto.

### 6.2 Balance / liquidación

1. **Ver Doc.** (o Pagar, la primera vez) crea la **factura de proveedor del balance** en **borrador**, con las líneas de la OC (cantidad, precio, descuento, impuestos con posición fiscal), fecha de factura igual a la fecha de factura del proveedor si ya se capturó, y referencia "OC — Balance (100 %)".
2. **Contabilidad revisa y confirma** la factura. Mientras esté en borrador, Pagar se detiene con un mensaje.
3. **Al confirmar la factura**, el sistema busca los **anticipos ya pagados de esa OC** (por la referencia de la OC en el pago) y los **concilia automáticamente**, de modo que el saldo por pagar de la factura queda neto de anticipos.
4. **Pagar** abre el asistente de registro de pago sobre la factura, con el saldo pendiente y la liga al hito.
5. Si la factura queda pagada por cualquier vía, el hito se marca pagado.

### 6.3 Sincronización con contabilidad

Cada vez que se confirma o cancela un pago, se confirma, pasa a borrador o se cancela una factura de proveedor, o se usa el asistente de pago, el sistema **recalcula lo pagado por hito**:

- pagos ligados directamente al hito;
- pagos conciliados a la factura del hito (sin contar dos veces los que ya estaban ligados);
- anticipos conciliados contra la factura de balance;
- pagos sueltos del proveedor **solo si su memo o referencia menciona la OC**.

Todo se suma en la **moneda del hito**. El estado se resuelve con lo pagado, el monto y la fecha límite. Hay un botón **Sincronizar desde contabilidad** para forzarlo.

### 6.4 Ajustes manuales

- **Marcar pagado**: cierra el hito con la fecha de pago indicada (uso excepcional, cuando el pago se registró fuera del flujo).
- Editar fecha límite, referencia SPEI, nota y bandera *manual* directamente en la lista.

---

## 7. Importación: contenedores e impuestos

En la OC de importación se registran los **contenedores**: número, tipo (20/40…), sello, **pedimento**, **impuestos en MXN**, estado del impuesto (pendiente/pagado) y fecha de pago. No son hitos del calendario, pero el **Reporte de Pagos** los muestra como obligaciones del mes junto con los hitos, porque salen de la misma tesorería.

Los términos que dependen del arribo marcan **Telex Release requerido**: el balance debe pagarse antes de la ETA para liberar la carga.

---

## 8. Sincronía con Torre de Control y Portal de Proveedor

Fecha BL, número BL y ETA capturados en la OC se copian al **viaje de Torre de Control** y al **embarque del Portal de Proveedor**, y viceversa. Por eso el calendario de importación se recalcula solo cuando logística actualiza el BL o la ETA desde cualquiera de los tres lugares.

---

## 9. Dónde se ve

| Pantalla | Qué muestra |
|---|---|
| OC › pestaña **Pagos SOMGROUP** | Fechas logísticas, término, tags "BL pendiente / ETA pendiente", calendario editable con acciones Pagar · Ver Doc. · Ver Pagos, avisos |
| **Compras › Calendario de Pagos** | Todos los hitos de todas las OC, filtrables por estado, proveedor, tipo de compra y compañía |
| **Compras › Reporte de Pagos** | Tablero mensual: totales en USD y MXN al tipo de cambio del día, anticipos y segundos tramos, balances y liquidaciones, impuestos de contenedores, proyección de meses futuros; filtro Importación / Nacional / Todo; excluye OC canceladas |
| **Reportes de Pagos** (módulo `purchase_payment_report`) | Estado de cuenta por pedido o por proveedor, desde la OC o desde el menú |
| Correos | Plantillas de compra con identidad SOMGROUP (proveedor en inglés) |

---

## 10. Reglas de datos vigentes (desde 12 sep 2026)

1. El saldo pendiente de un hito es **siempre** monto menos pagado; no se captura.
2. Un hito pasa a **Vencido** por el cron diario, no por acción manual, y regresa a Pendiente si la fecha se corrige.
3. Todos los pagos se suman **convertidos a la moneda del hito**.
4. Un pago suelto del proveedor **no** se aplica a una OC salvo que la mencione en su referencia.
5. El calendario **cierra contra el total** de la OC; el último balance absorbe el redondeo.
6. Sin fecha de factura del proveedor, los términos "a N días de factura" **no** calculan fecha: quedan manuales con aviso.
7. El calendario no se regenera por editar líneas si el total no cambió, y avisa en el chatter cuando reemplaza hitos manuales o cuando no puede recalcular.
8. La factura de balance respeta descuentos de la OC y toma la fecha de factura del proveedor.
9. Ningún anticipo se contabiliza sin que Tesorería elija diario, fecha y monto.

---

## 11. Decisiones pendientes

- **Factura de balance por lo recibido.** Hoy se factura la cantidad completa de la OC aunque haya recepciones parciales, y sin cuentas analíticas. Si se quiere facturar contra recepción, hay que rehacer esa creación sobre el flujo estándar de facturación de Odoo.
- **Conciliación de anticipos por referencia.** Funciona si el memo del pago lleva la OC (el botón Pagar lo pone solo). Un pago capturado a mano sin la referencia no se concilia automáticamente y Contabilidad debe aplicarlo desde la factura.
- **Tipo de cambio del reporte.** Usa el tipo del día de la compañía; si no hay tasa configurada cae a la última almacenada y lo deja en el log.

---

## 12. Glosario

- **Hito**: renglón del calendario de pagos (anticipo, segundo tramo o balance).
- **BL**: Bill of Lading, conocimiento de embarque; su fecha arranca muchos plazos de importación.
- **ETA**: fecha estimada de arribo del embarque.
- **CAD**: Cash Against Documents, pago contra documentos.
- **Telex Release**: liberación de la carga por la naviera; exige el pago previo del balance.
- **Base de vencimiento nacional**: fecha desde la que se cuentan los días de crédito en compras nacionales.
- **Pedimento**: documento aduanal del contenedor; sus impuestos se registran por contenedor.
