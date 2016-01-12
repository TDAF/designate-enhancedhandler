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

from oslo_config import cfg
from oslo_log import log as logging

from designate import exceptions
from designate_enhancedhandler.notification_handler.base import BaseEnhancedHandler


LOG = logging.getLogger(__name__)

# Setup a config group
cfg.CONF.register_group(cfg.OptGroup(
    name='handler:neutron_enhanced',
    title="Configuration for Enhanced Neutron Notification Handler"
))

# Setup the config options
cfg.CONF.register_opts([
    cfg.ListOpt('notification-topics', default=['notifications']),
    cfg.StrOpt('control-exchange', default='neutron'),
    cfg.StrOpt('format', default='%(hostname)s.floating_%(interface)s.%(domain)s'),
], group='handler:neutron_enhanced')


class NeutronEnhancedHandler(BaseEnhancedHandler):
    """Neutron Enhanced Handler"""
    __plugin_name__ = 'neutron_enhanced'

    def get_event_types(self):
        return [
            'floatingip.update.end',
            'floatingip.delete.end',
            'port.delete.end'  # Event triggered when a instance is removed
        ]

    def _get_recordset(self, context, address):
        record = self.central_api.find_record(context, {
            'managed': True,
            'data': address
        })
        return self.central_api.find_recordset(context, {
            'id': record['recordset_id']
        })

    def process_notification(self, ctx, event_type, payload):
        LOG.info('EnhancedNeutronHandler notification: %s. %s', event_type, payload)

        managed = {
            'managed': True,
            'managed_plugin_name': self.get_plugin_name(),
            'managed_plugin_type': self.get_plugin_type(),
            'managed_resource_type': 'floatingip'
        }

        if event_type == 'floatingip.update.end':
            # Get the context associated to the tenant identified in payload event
            context = self._get_context(payload['floatingip']['tenant_id'])
            # Update managed object with resource_id and port_id (if available)
            managed['managed_resource_id'] = payload['floatingip']['id']
            if payload['floatingip']['port_id']:
                managed['managed_extra'] = 'portid:%s' % payload['floatingip']['port_id']
            # If no fixed IP address, it means that the floating address has been unassigned
            if not payload['floatingip']['fixed_ip_address']:
                self._delete_records(context, managed)
            else:
                fixed_address = payload['floatingip']['fixed_ip_address']
                floating_address = payload['floatingip']['floating_ip_address']
                LOG.info('Assigning floating IP address: %s to fixed address: %s', floating_address, fixed_address)
                try:
                    recordset = self._get_recordset(context, fixed_address)
                except exceptions.RecordNotFound:
                    LOG.warn('Error assigning floating IP address: %s because fixed address: %s is not managed',
                             floating_address, fixed_address)
                else:
                    recordset_parsed = recordset['name'].split('.', 2)
                    hostname = recordset_parsed[0]
                    interface = recordset_parsed[1]
                    floating_payload = {
                        'hostname': hostname,
                        'fixed_ips': [{
                            'label': interface,
                            'version': 6 if recordset['type'] == 'AAAA' else 4,
                            'address': floating_address
                        }]
                    }
                    self._create_records(context, managed, floating_payload)
        elif event_type == 'floatingip.delete.end':
            context = self._get_context()
            managed['managed_resource_id'] = payload['floatingip_id']
            self._delete_records(context, managed)
        elif event_type == 'port.delete.end':
            context = self._get_context()
            managed['managed_extra'] = 'portid:%s' % payload['port_id']
            self._delete_records(context, managed)
