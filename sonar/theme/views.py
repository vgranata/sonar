# -*- coding: utf-8 -*-
#
# Swiss Open Access Repository
# Copyright (C) 2021 RERO
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Blueprint used for loading templates.

The sole purpose of this blueprint is to ensure that Invenio can find the
templates and static files located in the folders of the same names next to
this file.
"""

from __future__ import absolute_import, print_function

import re
from datetime import datetime
from urllib.parse import urlparse

import dateutil.parser
import pytz
from flask import Blueprint, abort, current_app, jsonify, redirect, \
    render_template, request, url_for
from flask_babelex import lazy_gettext as _
from flask_breadcrumbs import register_breadcrumb
from flask_login import current_user, login_required
from flask_menu import current_menu, register_menu
from invenio_jsonschemas.errors import JSONSchemaNotFound
from invenio_pidstore.models import PersistentIdentifier

from sonar.json_schemas.factory import JSONSchemaFactory
from sonar.modules.collections.permissions import \
    RecordPermission as CollectionPermission
from sonar.modules.deposits.permissions import DepositPermission
from sonar.modules.documents.api import DocumentRecord
from sonar.modules.documents.permissions import DocumentPermission
from sonar.modules.organisations.api import OrganisationSearch
from sonar.modules.organisations.permissions import OrganisationPermission
from sonar.modules.permissions import can_access_manage_view
from sonar.modules.subdivisions.permissions import \
    RecordPermission as SubdivisionPermission
from sonar.modules.users.api import current_user_record
from sonar.modules.users.permissions import UserPermission
from sonar.resources.projects.permissions import RecordPermissionPolicy

blueprint = Blueprint('sonar',
                      __name__,
                      template_folder='templates',
                      static_folder='static')


@blueprint.before_app_request
def init_view():
    """Do some stuff before rendering any view."""
    current_menu.submenu('settings').submenu('security').hide()
    current_menu.submenu('settings').submenu('admin').hide()


@blueprint.route('/robots.txt')
def robots_txt():
    """Generate dynamically robots.txt."""
    template = 'sonar/robots.txt'
    if not current_app.config.get('SONAR_APP_PRODUCTION_STATE'):
        # If we are not in production status, we disable all robots
        return current_app.response_class(
            response=render_template(template, state=False),
            status=200,
            mimetype='text/plain')
    url_data = urlparse(request.url)
    scheme = url_data.scheme
    server_name = url_data.netloc.split(':')[0]
    if org_pid := OrganisationSearch() \
        .get_organisation_pid_by_server_name(server_name):
        sitemap = f'{scheme}://{server_name}/{org_pid}/sitemap.xml'
    else:
        view = current_app.config.get('SONAR_APP_DEFAULT_ORGANISATION')
        sitemap = f'{scheme}://{url_data.netloc}/{view}/sitemap.xml'
    return current_app.response_class(
        response=render_template(
            template,
            state=current_app.config.get('SONAR_APP_PRODUCTION_STATE'),
            sitemap=sitemap),
        status=200,
        mimetype='text/plain')


@blueprint.route('/users/profile')
@blueprint.route('/users/profile/<pid>')
@login_required
@register_menu(blueprint, 'settings.record_profile',
               _('%(icon)s Profile', icon='<i class="fa fa-user fa-fw"></i>'))
@register_breadcrumb(blueprint, 'breadcrumbs.record_profile', _('Profile'))
def profile(pid=None):
    """Logged user profile edition page.

    :param pid: Logged user PID.
    """
    if pid and pid != current_user_record['pid']:
        abort(403)

    if not pid:
        return redirect(
            url_for('sonar.profile', pid=current_user_record['pid']))

    return render_template('sonar/accounts/profile.html')


@blueprint.route('/error')
def error():
    """Error to generate exception for test purposes."""
    raise Exception('this is an error for test purposes')


@blueprint.route('/rerodoc/<pid>')
@blueprint.route('/rerodoc/<pid>/files/<filename>')
def rerodoc_redirection(pid, filename=None):
    """Redirection to document with identifier from RERODOC.

    :param pid: PID from RERODOC.
    :returns: A redirection to record's detail page or 404 if not found.
    """
    try:
        pid = PersistentIdentifier.get('rerod', pid)
    except Exception:
        abort(404)

    # Files URLs does not contains view
    if filename:
        return redirect(
            url_for('invenio_records_ui.doc_files',
            pid_value=pid.get_redirect().pid_value,
            filename=filename))
    doc_pid = pid.get_redirect().pid_value
    doc = DocumentRecord.get_record_by_pid(doc_pid)
    if doc:
        doc = doc.replace_refs()
        orgs = doc.get('organisation', [])
        # In case of multiple organisations we redirect to the global view
        if len(orgs) == 1:
            org = orgs.pop()
            # Only for dedicated or shared
            if org.get('isDedicated') or org.get('isShared'):
                return redirect(
                    url_for('invenio_records_ui.doc',
                    view=org.get('code'),
                    pid_value=pid.get_redirect().pid_value))
    global_view = current_app.config.get('SONAR_APP_DEFAULT_ORGANISATION')
    return redirect(
        url_for('invenio_records_ui.doc',
                view=global_view,
                pid_value=pid.get_redirect().pid_value))


@blueprint.route('/manage/')
@blueprint.route('/manage/<path:path>')
@can_access_manage_view
def manage(path=None):
    """Admin access page integrating angular ui."""
    return render_template('sonar/manage.html')


@blueprint.route('/logged-user/', methods=['GET'])
def logged_user():
    """Current logged user informations in JSON."""
    if current_user.is_anonymous:
        return jsonify({})

    user = current_user_record

    if user and 'resolve' in request.args:
        user = user.replace_refs()

    data = {
        'settings': {
            'document_identifier_link': current_app.config \
                .get('SONAR_APP_DOCUMENT_IDENTIFIER_LINK')
        }
    }

    if user:
        data['metadata'] = user.dumps()
        data['metadata']['is_superuser'] = user.is_superuser
        data['metadata']['is_admin'] = user.is_admin
        data['metadata']['is_moderator'] = user.is_moderator
        data['metadata']['is_submitter'] = user.is_submitter
        data['metadata']['is_user'] = user.is_user
        data['metadata']['permissions'] = {
            'users': {
                'add': UserPermission.create(user),
                'list': UserPermission.list(user)
            },
            'documents': {
                'add': DocumentPermission.create(user),
                'list': DocumentPermission.list(user)
            },
            'organisations': {
                'add': OrganisationPermission.create(user),
                'list': OrganisationPermission.list(user)
            },
            'deposits': {
                'add': DepositPermission.create(user),
                'list': DepositPermission.list(user)
            },
            'projects': {
                'add': RecordPermissionPolicy('create').can(),
                'list': RecordPermissionPolicy('search').can()
            },
            'collections': {
                'add': CollectionPermission.create(user),
                'list': CollectionPermission.list(user)
            },
            'subdivisions': {
                'add': SubdivisionPermission.create(user),
                'list': SubdivisionPermission.list(user)
            }
        }

    # TODO: If an organisation is associated to user and only when running
    # tests, organisation cannot not be encoded to JSON after call of
    # user.replace_refs() --> check why
    return jsonify(data)


@blueprint.route('/schemas/<record_type>')
def schemas(record_type):
    """Return schema for the editor.

    :param record_type: Type of resource.
    :returns: JSONified schema or a 404 if not found.
    """
    try:
        json_schema = JSONSchemaFactory.create(record_type)
        return jsonify({'schema': json_schema.process()})
    except JSONSchemaNotFound:
        abort(404)


@blueprint.app_template_filter()
def record_image_url(record, code, key=None):
    """Get image URL for a record.

    :param files: Liste of files of the record.
    :param key: The key of the file to be rendered, if no key, takes the first.
    :returns: Image url corresponding to key, or the first one.
    """
    if not (record.get('_files') and record.get('pid')):
        return None
    for file in record['_files']:
        if re.match(r'^.*\.(jpe?g|png|gif|svg)$',
                    file['key'],
                    flags=re.IGNORECASE):
            if not key or file['key'] == key:
                return url_for(
                    f'invenio_records_ui.{code}_files',
                    pid_value=record.get('pid'),
                    filename=file['key'])
    return None


@blueprint.app_template_filter()
def format_date(date, format='%d/%m/%Y'):
    """Format the given ISO format date string.

    :param date: Date string in ISO format.
    :param format: Output format.
    :returns: Formatted date string.
    """
    # Parse date
    if not isinstance(date, datetime):
        date = dateutil.parser.isoparse(date)

    # Add timezone info
    if not date.tzinfo:
        date = pytz.utc.localize(date)

    # Change date to the right timezone
    timezone = pytz.timezone(current_app.config.get('BABEL_DEFAULT_TIMEZONE'))
    date = date.astimezone(timezone)

    return date.strftime(format)
