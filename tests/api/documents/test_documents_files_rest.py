# -*- coding: utf-8 -*-
#
# Swiss Open Access Repository
# Copyright (C) 2022 RERO
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

"""Test REST endpoint for documents."""


from elasticsearch_dsl import Search
from flask import url_for
from invenio_stats.tasks import process_events


def test_get_content(app, client, document_with_file):
    """Test get existing file content."""
    app.config.update(SONAR_APP_DISABLE_PERMISSION_CHECKS=True)

    file_name = 'test1.pdf'
    fulltext_file_name = 'test1-pdf.txt'
    thumbnail_file_name = 'test1-pdf.jpg'
    # get the pdf file
    url_file_content = url_for('invenio_records_files.doc_object_api', pid_value=document_with_file.get('pid'), key=file_name)
    res = client.get(url_file_content)
    assert res.status_code == 200
    assert res.content_type == 'application/octet-stream'
    assert res.content_length > 0

    url_file_content = url_for('invenio_records_files.doc_object_api', pid_value=document_with_file.get('pid'), key=fulltext_file_name)
    res = client.get(url_file_content)
    assert res.status_code == 200
    assert res.content_type == 'text/plain; charset=utf-8'
    assert res.content_length > 0

    url_file_content = url_for('invenio_records_files.doc_object_api', pid_value=document_with_file.get('pid'), key=thumbnail_file_name)
    res = client.get(url_file_content)
    assert res.status_code == 200
    assert res.content_type == 'image/jpeg'
    assert res.content_length > 0

def test_get_metadata(app, client, document_with_file):
    """Test get existing file metadata."""
    app.config.update(SONAR_APP_DISABLE_PERMISSION_CHECKS=True)

    # get all files metadata of a given document
    url_files = url_for(
        'invenio_records_files.doc_bucket_api',
        pid_value=document_with_file.get('pid'))
    res = client.get(url_files)
    assert res.status_code == 200
    file_keys = ['test1.pdf', 'test1-pdf.txt', 'test1-pdf.jpg']
    assert set(file_keys) == set(
        [f.get('key') for f in res.json.get('contents')])

    # get a specific file metadata of a given document
    for f_key in file_keys:
        url_file = url_for(
            'invenio_records_files.doc_bucket_api',
            pid_value=document_with_file.get('pid'), key=f_key)
        res = client.get(url_file)
        assert res.status_code == 200


def test_put_delete(app, client, document, pdf_file):
    """Test create and delete a file."""
    app.config.update(SONAR_APP_DISABLE_PERMISSION_CHECKS=True)
    file_name = 'test.pdf'

    # upload the file
    url_file_content = url_for(
        'invenio_records_files.doc_object_api', pid_value=document.get('pid'), key=file_name)
    res = client.put(url_file_content, input_stream=open(pdf_file, 'rb'))
    assert res.status_code == 200

    # get the version id
    url_file = url_for(
        'invenio_records_files.doc_bucket_api',
        pid_value=document.get('pid'), key=file_name)
    res = client.get(url_file)
    content = res.json.get('contents')

    # file, fulltext, thumbnail
    assert len(content) == 3
    content = content.pop()
    version_id = content.get('version_id')

    # upload a second version
    url_file_content = url_for(
        'invenio_records_files.doc_object_api', pid_value=document.get('pid'), key=file_name)
    res = client.put(url_file_content, input_stream=open(pdf_file, 'rb'))
    assert res.status_code == 200

    # get the new version id
    url_file = url_for(
        'invenio_records_files.doc_bucket_api',
        pid_value=document.get('pid'), key=file_name)
    res = client.get(url_file)
    content = res.json.get('contents')

    # file, fulltext, thumbnail
    assert len(content) == 3
    content = content.pop()
    assert version_id != content.get('version_id')

    # delete the file
    url_delete_file_content = url_for(
        'invenio_records_files.doc_object_api', pid_value=document.get('pid'), key=file_name)
    res = client.delete(url_delete_file_content)
    assert res.status_code == 204

    # the file does not exists anymore
    res = client.get(url_file_content)
    assert res.status_code == 404

    # the file does not exists anymore
    url_file = url_for(
        'invenio_records_files.doc_bucket_api',
        pid_value=document.get('pid'), key=file_name)
    res = client.get(url_file)
    assert res.status_code == 200
    content = res.json.get('contents')
    # fulltext, thumbnail: file has been removed
    # TODO: is it the right approach? Do we need to remove files and
    # the bucket?
    assert len(content) == 2


def test_stats(app, client, document_with_file, es, event_queues):
    """Test get existing stats for file downloads."""
    app.config.update(SONAR_APP_DISABLE_PERMISSION_CHECKS=True)

    file_name = 'test1.pdf'
    # get the pdf file
    url_file_content = url_for('invenio_records_files.doc_object_api', pid_value=document_with_file.get('pid'), key=file_name)
    res = client.get(url_file_content)
    assert res.status_code == 200
    assert res.content_type == 'application/octet-stream'
    assert res.content_length > 0

    # process the task
    process_events(['file-download'])

    es.indices.refresh(index='events-stats-file-download')
    search = Search(using=es).index('events-stats-file-download')

    # should have at least one stats in the index
    assert search.execute().hits.total.value > 0
