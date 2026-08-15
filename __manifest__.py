{
    'name': 'SOMGROUP - Términos de Pago Importaciones',
    'version': '19.0.2.12.0',
    'category': 'Purchase',
    'summary': 'Términos de pago especiales para compras nacionales e importaciones con cálculo automático de vencimientos',
    'description': """
        Control financiero-logístico de pagos a proveedores para compras de importación
        y compras nacionales.

        - Importaciones: cálculo por BL, ETA, CAD, contra BL y Telex Release.
        - Nacionales: cálculo por fecha de OC, confirmación, factura proveedor,
          recepción esperada, recepción real o fecha manual de referencia.
        - Calendario de pagos por OC.
        - Registro de anticipos, segundos tramos y balances.
        - Factura de balance y conciliación automática de anticipos.
        - Dashboard mensual con filtro: Todo / Importación / Nacional.
    """,
    'author': 'Alphaqueb Consulting SAS',
    'depends': ['purchase', 'account', 'sale'],
    'data': [
        'security/ir.model.access.csv',
        'data/payment_term_data.xml',
        'views/purchase_order_views.xml',
        'views/sale_order_payment_term_views.xml',
        'views/payment_term_views.xml',
        'views/account_payment_views.xml',
        'views/payment_report_views.xml',
        'data/mail_template_purchase_branding.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'somgroup_purchase_payment_terms/static/src/scss/payment_report_dashboard.scss',
            'somgroup_purchase_payment_terms/static/src/scss/payment_schedule_list.scss',
            'somgroup_purchase_payment_terms/static/src/js/payment_report_dashboard.js',
            'somgroup_purchase_payment_terms/static/src/xml/payment_report_dashboard.xml',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}