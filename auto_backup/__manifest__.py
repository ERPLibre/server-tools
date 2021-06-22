# Copyright 2004-2009 Tiny SPRL (<http://tiny.be>).
# Copyright 2015 Agile Business Group <http://www.agilebg.com>
# Copyright 2016 Grupo ESOC Ingenieria de Servicios, S.L.U. - Jairo Llopis
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Database Auto-Backup",
    "category": "Tools",
    "summary": "Backups database",
    "version": "12.0.1.0.0",
    "author": (
        "Yenthe Van Ginneken, "
        "Agile Business Group, "
        "Grupo ESOC Ingenieria de Servicios, "
        "LasLabs, "
        "AdaptiveCity, "
        "Odoo Community Association (OCA)"
    ),
    "license": "AGPL-3",
    "website": "https://github.com/OCA/server-tools/",
    "depends": ["mail"],
    "external_dependencies": {
        "python": ["pysftp"],
    },
    "data": [
        "security/ir.model.access.csv",
        "data/mail_message_subtype.xml",
        "views/db_backup.xml",
        "views/menu.xml",
        "data/ir_cron.xml",
    ],
    "installable": True,
}
