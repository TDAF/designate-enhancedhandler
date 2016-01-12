# -*- coding: utf-8 -*-

# Copyright 2016 Telefónica Investigación y Desarrollo, S.A.U
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from mock import call, patch, MagicMock
from unittest import TestCase

from designate_enhancedhandler.notification_handler.nova import NovaEnhancedHandler
from collections import namedtuple


DomainDict = namedtuple('DomainDict', ['id', 'name'])


class NovaEnhancedHandlerTest(TestCase):
    def setUp(self):
        self.mock_central_rpcapi = MagicMock(name='central_rpcapi')
        self.patch_central_rpcapi = patch('designate.notification_handler.base.central_rpcapi',
                                          self.mock_central_rpcapi)
        self.patch_central_rpcapi.start()
        self.mock_central_api = self.mock_central_rpcapi.CentralAPI.return_value

        self.mock_recordset = MagicMock(name='recordset')
        self.patch_recordset = patch('designate_enhancedhandler.notification_handler.base.RecordSet',
                                     self.mock_recordset)
        self.patch_recordset.start()
        self.mock_recordset_sample = MagicMock(name='recordset_sample')
        self.mock_recordset.return_value = self.mock_recordset_sample

        self.mock_admin_context = MagicMock(name='admin_context')
        self.mock_admin_context.tenant = '4e3b6c0108f04b309737522a9deee9d8'
        self.mock_designate_context = MagicMock(name='designate_context')
        self.mock_designate_context.get_admin_context.return_value = self.mock_admin_context
        self.patch_designate_context = patch('designate_enhancedhandler.notification_handler.base.DesignateContext',
                                             self.mock_designate_context)
        self.patch_designate_context.start()
        self.handler = NovaEnhancedHandler()
        self.admin_context = None  # Unused by the handler

    def tearDown(self):
        self.patch_designate_context.stop()
        self.patch_recordset.stop()
        self.patch_central_rpcapi.stop()

    def test_create_instance(self):
        event_type = 'compute.instance.create.end'
        payload = {
            'hostname': 'demodesignate',
            'tenant_id': '4e3b6c0108f04b309737522a9deee9d8',
            'instance_id': '9220edc1-426e-46b1-9967-ce1e64c82f01',
            'fixed_ips': [
                {
                    'floating_ips': [],
                    'label': 'private_management',
                    'version': 4,
                    'meta': {},
                    'address': '192.168.3.22',
                    'type"': 'fixed'
                },
                {
                    'floating_ips': [],
                    'label': 'private_external',
                    'version': 4,
                    'meta': {},
                    'address': '172.16.3.26',
                    'type"': 'fixed'
                }
            ]
        }
        self.mock_central_api.find_domain.return_value = {'id': 'test_domain_id', 'name': 'test_domain.ost.com.'}
        self.mock_central_api.find_domains.return_value = [
            DomainDict(id='test_reverse_domain_id', name='172.in-addr.arpa.')
        ]
        self.mock_central_api.create_recordset.return_value = {'id': 'test_recordset_id'}

        self.handler.process_notification(self.mock_admin_context, event_type, payload)

        self.mock_central_api.find_domain.assert_called_once_with(self.mock_admin_context,
                                                                  {'tenant_id': '4e3b6c0108f04b309737522a9deee9d8'})
        self.mock_central_api.find_domains.assert_has_calls([call(self.mock_admin_context),
                                                             call(self.mock_admin_context)])

        self.mock_recordset.assert_has_calls([
            call(name='demodesignate.private_management.test_domain.ost.com.', type='A'),
            call(name='demodesignate.private_external.test_domain.ost.com.', type='A'),
            call(name='26.3.16.172.in-addr.arpa.', type='PTR')
        ])
        self.mock_central_api.create_recordset.assert_has_calls([
            call(self.mock_admin_context, 'test_domain_id', self.mock_recordset_sample),
            call(self.mock_admin_context, 'test_domain_id', self.mock_recordset_sample),
            call(self.mock_admin_context, 'test_reverse_domain_id', self.mock_recordset_sample)
        ])

    def test_delete_instance(self):
        event_type = 'compute.instance.delete.start'
        payload = {
            'hostname': 'demodesignate',
            'tenant_id': '4e3b6c0108f04b309737522a9deee9d8',
            'instance_id': '9220edc1-426e-46b1-9967-ce1e64c82f01'
        }

        self.mock_central_api.find_records.return_value = [
            {'id': 'test_record_id_1', 'domain_id': 'test_domain_id', 'recordset_id': 'test_recordset_id_1'},
            {'id': 'test_record_id_2', 'domain_id': 'test_domain_id', 'recordset_id': 'test_recordset_id_2'}
        ]

        self.handler.process_notification(self.mock_admin_context, event_type, payload)

        self.mock_central_api.find_records.assert_called_once_with(self.mock_admin_context, {
            'managed': True,
            'managed_plugin_name': 'nova_enhanced',
            'managed_plugin_type': 'handler',
            'managed_resource_type': 'instance',
            'managed_resource_id': '9220edc1-426e-46b1-9967-ce1e64c82f01'
        })
        self.mock_central_api.delete_record.assert_has_calls([
            call(self.mock_admin_context, 'test_domain_id', 'test_recordset_id_1', 'test_record_id_1'),
            call(self.mock_admin_context, 'test_domain_id', 'test_recordset_id_2', 'test_record_id_2')
        ])
