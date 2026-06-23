/** English message catalogue — all UI strings live here, keyed by dot-notation ID. */
export const messages: Record<string, string> = {
  'app.name': 'VMS',
  'app.title': 'Video Management System',

  'nav.live': 'Live View',
  'nav.analytics': 'Analytics',
  'nav.forensic': 'Forensic Search',
  'nav.admin': 'Admin',

  'auth.login': 'Log in',
  'auth.logout': 'Log out',
  'auth.username': 'Username',
  'auth.password': 'Password',
  'auth.error.invalid': 'Invalid username or password.',

  'alert.acknowledge': 'Acknowledge',
  'alert.resolve': 'Resolve',
  'alert.severity.critical': 'Critical',
  'alert.severity.high': 'High',
  'alert.severity.medium': 'Medium',
  'alert.severity.low': 'Low',

  'zone.create': 'New zone',
  'zone.edit': 'Edit zone',
  'zone.delete': 'Archive zone',
  'zone.deleteConfirm': 'Archive this zone? Active presence tracking will stop.',

  'person.enroll': 'Enroll person',
  'person.purge': 'Purge person data',

  'error.notFound': 'Page not found',
  'error.forbidden': "You don't have permission to view this page.",
  'error.serverError': 'An unexpected error occurred. Please try again.',

  'action.save': 'Save',
  'action.cancel': 'Cancel',
  'action.delete': 'Delete',
  'action.confirm': 'Confirm',
  'action.close': 'Close',
}
