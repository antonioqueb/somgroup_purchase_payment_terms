{
    'name': 'SOMGROUP - Términos de Pago Importaciones',
    'version': '19.0.1.5.0',  # ← bumped
    'category': 'Purchase',
    'summary': 'Términos de pago especiales para importaciones con fecha BL y cálculo automático de vencimientos',
    'description': """...""",
    'author': 'Alphaqueb Consulting SAS',
    'depends': ['purchase', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'data/payment_term_data.xml',
        'views/purchase_order_views.xml',
        'views/payment_term_views.xml',
        'views/account_payment_views.xml',
        'views/payment_report_views.xml',       # ← NUEVO
    ],
    'assets': {                                  # ← NUEVO BLOQUE
        'web.assets_backend': [
            'somgroup_purchase_payment_terms/static/src/scss/payment_report_dashboard.scss',
            'somgroup_purchase_payment_terms/static/src/js/payment_report_dashboard.js',
            'somgroup_purchase_payment_terms/static/src/xml/payment_report_dashboard.xml',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}