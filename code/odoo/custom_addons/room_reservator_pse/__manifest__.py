{
    'name': 'Custom Room Reservator IoT:)',
    'version': '1.0',
    'summary': 'A custom Odoo module',
    'description': 'This is a custom Odoo module which allows for calendar feature and IoT connection.',
    'category': 'Tools',
    'author': 'PSE Abilium',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'views/custom_model_views.xml',
        'security/ir.model.access.csv',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}