{
    'name': 'Odoo IoT-Modul für Sitzungszimmer-Beschriftung mit e-Ink Displays',
    'version': '1.0',
    'summary': 'A custom Odoo module',
    'description': 'This is a custom Odoo module which allows for calendar feature and IoT connection.',
    'category': 'Tools',
    'author': 'PSE Abilium',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'views/calendar_view.xml',
        'views/custom_model_views.xml',  # This defines the menu items
    ],
    'installable': True,
    'application': True,
}