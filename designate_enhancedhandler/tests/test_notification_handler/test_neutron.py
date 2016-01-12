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

from designate_enhancedhandler.notification_handler.neutron import NeutronEnhancedHandler
from collections import namedtuple


DomainDict = namedtuple('DomainDict', ['id', 'name'])


class NeutronEnhancedHandlerTest(TestCase):
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
        self.handler = NeutronEnhancedHandler()
        self.admin_context = None  # Unused by the handler

    def tearDown(self):
        self.patch_designate_context.stop()
        self.patch_recordset.stop()
        self.patch_central_rpcapi.stop()

    def test_associate_floating_ip(self):
        event_type = 'floatingip.update.end'
        payload = {
            'floatingip': {
                'router_id': 'ad7c46a4-47cd-459b-a807-321ce5a0a1a1',
                'status': 'DOWN',
                'tenant_id': '4e3b6c0108f04b309737522a9deee9d8',
                'floating_network_id': '51f77b01-4484-45e1-9d88-de2fcdf44082',
                "fixed_ip_address": "172.16.3.36",
                'floating_ip_address': '192.168.49.162',
                'port_id': '3e088857-f2b2-4689-9478-56bf6b735be1',
                'id': '2cde8e69-a298-48bd-8785-10405ea245d2'
            }
        }
        self.mock_central_api.find_record.return_value = {'recordset_id': 'recordset_id'}
        self.mock_central_api.find_recordset.return_value = {
            'name': 'demodesignate.private_management.test_domain.ost.com.',
            'type': 4
        }
        self.mock_central_api.find_domain.return_value = {
            'id': 'test_domain_id',
            'name': 'test_domain.ost.com.'
        }
        self.mock_central_api.find_domains.return_value = [
            DomainDict(id='test_reverse_domain_id', name='172.in-addr.arpa.'),
            DomainDict(id='test_reverse_domain_id', name='192.in-addr.arpa.')
        ]

        self.handler.process_notification(self.mock_admin_context, event_type, payload)

        self.mock_central_api.find_record.assert_called_once_with(
            self.mock_admin_context, {'managed': True, 'data': '172.16.3.36'}
        )
        self.mock_central_api.find_recordset.assert_called_once_with(
            self.mock_admin_context, {'id': 'recordset_id'}
        )

        self.mock_recordset.assert_has_calls([
            call(name='demodesignate.floating_private_management.test_domain.ost.com.', type='A'),
            call(name='162.49.168.192.in-addr.arpa.', type='PTR')
        ])
        self.mock_central_api.create_recordset.assert_has_calls([
            call(self.mock_admin_context, 'test_domain_id', self.mock_recordset_sample),
            call(self.mock_admin_context, 'test_reverse_domain_id', self.mock_recordset_sample)
        ], any_order=True)

    def test_delete_floating_ip_1(self):
        event_type = 'floatingip.update.end'
        payload = {
            'floatingip': {
                'router_id': None,
                'status': 'ACTIVE',
                'tenant_id': '4e3b6c0108f04b309737522a9deee9d8',
                'floating_network_id': '51f77b01-4484-45e1-9d88-de2fcdf44082',
                'fixed_ip_address': None,
                'floating_ip_address': '192.168.49.162',
                'port_id': None,
                'id': '2cde8e69-a298-48bd-8785-10405ea245d2'
            }
        }

        self.mock_central_api.find_records.return_value = [
            {'id': 'test_record_id_1', 'domain_id': 'test_domain_id', 'recordset_id': 'test_recordset_id_1'},
            {'id': 'test_record_id_2', 'domain_id': 'test_domain_id', 'recordset_id': 'test_recordset_id_2'}
        ]

        self.handler.process_notification(self.mock_admin_context, event_type, payload)

        self.mock_central_api.find_records.assert_called_once_with(self.mock_admin_context, {
            'managed': True,
            'managed_plugin_name': 'neutron_enhanced',
            'managed_plugin_type': 'handler',
            'managed_resource_type': 'floatingip',
            'managed_resource_id': '2cde8e69-a298-48bd-8785-10405ea245d2'
        })
        self.mock_central_api.delete_record.assert_has_calls([
            call(self.mock_admin_context, 'test_domain_id', 'test_recordset_id_1', 'test_record_id_1'),
            call(self.mock_admin_context, 'test_domain_id', 'test_recordset_id_2', 'test_record_id_2')
        ])

    def test_delete_floating_ip_2(self):
        event_type = 'floatingip.delete.end'
        payload = {
            'floatingip_id': '2cde8e69-a298-48bd-8785-10405ea245d2'
        }

        self.mock_central_api.find_records.return_value = [
            {'id': 'test_record_id_1', 'domain_id': 'test_domain_id', 'recordset_id': 'test_recordset_id_1'},
            {'id': 'test_record_id_2', 'domain_id': 'test_domain_id', 'recordset_id': 'test_recordset_id_2'}
        ]

        self.handler.process_notification(self.mock_admin_context, event_type, payload)

        self.mock_central_api.find_records.assert_called_once_with(self.mock_admin_context, {
            'managed': True,
            'managed_plugin_name': 'neutron_enhanced',
            'managed_plugin_type': 'handler',
            'managed_resource_type': 'floatingip',
            'managed_resource_id': '2cde8e69-a298-48bd-8785-10405ea245d2'
        })
        self.mock_central_api.delete_record.assert_has_calls([
            call(self.mock_admin_context, 'test_domain_id', 'test_recordset_id_1', 'test_record_id_1'),
            call(self.mock_admin_context, 'test_domain_id', 'test_recordset_id_2', 'test_record_id_2')
        ])

    def test_delete_floating_ip_3(self):
        event_type = 'port.delete.end'
        payload = {
            'port_id': '2cde8e69-a298-48bd-8785-10405ea245d2'
        }

        self.mock_central_api.find_records.return_value = [
            {'id': 'test_record_id_1', 'domain_id': 'test_domain_id', 'recordset_id': 'test_recordset_id_1'},
            {'id': 'test_record_id_2', 'domain_id': 'test_domain_id', 'recordset_id': 'test_recordset_id_2'}
        ]

        self.handler.process_notification(self.mock_admin_context, event_type, payload)

        self.mock_central_api.find_records.assert_called_once_with(self.mock_admin_context, {
            'managed': True,
            'managed_plugin_name': 'neutron_enhanced',
            'managed_plugin_type': 'handler',
            'managed_resource_type': 'floatingip',
            'managed_extra': 'portid:2cde8e69-a298-48bd-8785-10405ea245d2'
        })
        self.mock_central_api.delete_record.assert_has_calls([
            call(self.mock_admin_context, 'test_domain_id', 'test_recordset_id_1', 'test_record_id_1'),
            call(self.mock_admin_context, 'test_domain_id', 'test_recordset_id_2', 'test_record_id_2')
        ])
