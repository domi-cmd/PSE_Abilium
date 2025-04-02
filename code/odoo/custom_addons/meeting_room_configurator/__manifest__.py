{
    # TODO: Rename the app via the 'name' variable to something more fitting such as "PSE Room Booking"
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
        'calendar',
    ],
    # Currently, there is no icon for our app yet, so the line below is not useful yet.
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
