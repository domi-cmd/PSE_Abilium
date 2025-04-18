{
    'name': 'Abilium Room Booker',
    'summary': 'App to create, delete and manage meeting rooms.',
    'description': '''
        Create, manage and delete meeting rooms, assign their ID and match it to its respective Ink Display ID.
    ''',
    'version': '0.1.0',
    'category': 'Productivity',
    'license': 'LGPL-3', 
    'author': 'PSE Abilium Team 2025',
    'website': 'https://github.com/domi-cmd/PSE_Abilium',
    'depends': [
        'base',
        'calendar',
    ],
    'images': ['static/description/icon.png'],
    'data': [
        'security/ir.model.access.csv',
        'views/rasp_connection_views.xml',
        'views/actions.xml',
        'views/menus.xml',
        'views/calendar_event_views.xml',
    ],
    
    'installable': True,
    'application': True,

}
