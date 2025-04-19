{
    'name': 'Abilium Room Booker',
    'summary': 'App to create, delete and manage meeting rooms.',
    'description': '''
        Create, manage and delete meeting rooms, assign their ID and match it to its respective Ink Display ID.
    ''',
    'version': '1.0.0',
    'category': 'Productivity',
    'license': 'LGPL-3', 
    'author': 'PSE Abilium Team 2025',
    'website': 'https://github.com/domi-cmd/PSE_Abilium',
    'depends': [
        'base',
        'calendar',
        'contacts', # for res.partner -> displaying rooms in calendar
        'resource', # for declaring as a resource
    ],
    'images': ['static/description/icon.png'],
    'data': [
        'security/ir.model.access.csv',
        'views/connection_configuration_views.xml',
        'views/calendar_event_views.xml',
    ],
    
    'installable': True,
    'application': True,

}
