# -*- coding: utf-8 -*-
#
# Copyright (C) 2019 RERO.
#
# Swiss Open Access Repository is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see LICENSE file for
# more details.

"""Pytest fixtures and plugins for the UI application."""

from __future__ import absolute_import, print_function

import pytest
from flask_security import login_user


@pytest.fixture(scope='module')
def user_fixture(app):
    """Create user in database."""
    with app.app_context():
        datastore = app.extensions['security'].datastore
        datastore.create_user(email='john.doe@test.com',
                              password='123456',
                              active=True)
        datastore.commit()
    return app


@pytest.fixture(scope='module')
def logged_user_fixture(app, client, user_fixture):
    """Find user and log in it."""
    with app.app_context():
        datastore = app.extensions['security'].datastore
        user = datastore.find_user(email='john.doe@test.com')
        login_user(user)
    return user


@pytest.fixture(scope='module')
def valid_user_dict():
    """Fixture for valid user dictionary."""
    return dict(
        user=dict(
            email='john.doe@test.com',
            profile=dict(
                full_name='John Doe',
                username='john-doe',
            ),
        ),
        external_id='1',
        external_method='idp',
    )


@pytest.fixture(scope='module')
def valid_attributes():
    """Fixture for valid attributes return by shibboleth."""
    return {
        'id': ['1'],
        'email': ['john.doe@test.com'],
        'name': ['John Doe'],
    }


@pytest.fixture(scope='module')
def valid_sp_configuration():
    """Fixture for valid service provider configuration."""
    return dict(strict=True,
                debug=True,
                entity_id='entity_id',
                x509cert='./docker/nginx/sp.pem',
                private_key='./docker/nginx/sp.key')
