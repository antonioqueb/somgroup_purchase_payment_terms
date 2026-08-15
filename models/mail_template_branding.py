# -*- coding: utf-8 -*-
"""Branding SOM en los correos de compra (los templates nativos son
noupdate: se aplican por función en cada -u)."""
import logging

from odoo import api, models
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

_TEMPLATES = {
    'purchase.email_template_edi_purchase': {
        'file': 'somgroup_purchase_payment_terms/data/mail_bodies/rfq.html',
        'subject': (
            "Request for Quotation {{ object.name or 'n/a' }} — "
            '(SOM)'),
    },
    'purchase.email_template_edi_purchase_done': {
        'file': ('somgroup_purchase_payment_terms/data/mail_bodies/'
                 'po_confirmed.html'),
        'subject': (
            "Purchase Order {{ object.name or 'n/a' }} — "
            '(SOM)'),
    },
}


class MailTemplate(models.Model):
    _inherit = 'mail.template'

    @api.model
    def _som_apply_purchase_mail_branding(self):
        for xmlid, spec in _TEMPLATES.items():
            template = self.env.ref(xmlid, raise_if_not_found=False)
            if not template:
                _logger.warning('[SOM MAIL] Template %s no existe.', xmlid)
                continue
            try:
                with file_open(spec['file'], 'r') as f:
                    body = f.read()
            except Exception:
                _logger.exception('[SOM MAIL] Sin cuerpo para %s.', xmlid)
                continue
            template.sudo().write({
                'subject': spec['subject'],
                'body_html': body,
            })
            _logger.info('[SOM MAIL] Branding aplicado a %s.', xmlid)
        return True
