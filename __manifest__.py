{
    'name': 'SOMGROUP - Términos de Pago Importaciones',
    'version': '19.0.1.3.0',
    'category': 'Purchase',
    'summary': 'Términos de pago especiales para importaciones con fecha BL y cálculo automático de vencimientos',
    'description': """
        Módulo para gestión de pagos a proveedores de importación:
        - Campo Fecha BL en orden de compra
        - Términos de pago con reglas de anticipos, balances y vencimientos
        - Cálculo automático de fechas basado en BL o ETA
        - Soporte para términos CAD, contra entrega, anticipos parciales
        - Integración con account.payment (pagos contables reales)
        - Estado del calendario actualizado automáticamente al confirmar pagos
    """,
    'author': 'Alphaqueb Consulting SAS',
    'depends': ['purchase', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'data/payment_term_data.xml',
        'views/purchase_order_views.xml',
        'views/payment_term_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}