{
    'name': 'Meeting Room Configurator',
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
    ],
    # Currently, there is no icon for our app yet, so the line below is not useful yet.
    # TODO: Add the icon in the specified path (odoo requires the path to look exactly as written here).
    'images': ['static/description/icon.png'],
    'data': [
        
        'security/ir.model.access.csv',
        'views/room_views.xml',
        'views/actions.xml',
        'views/menus.xml',
        
    ],
    
    'installable': True,
    'application': True,

}
