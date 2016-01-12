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

from designate_enhancedhandler.notification_handler.base import BaseEnhancedHandler


LOG = logging.getLogger(__name__)

# Setup a config group
cfg.CONF.register_group(cfg.OptGroup(
    name='handler:nova_enhanced',
    title="Configuration for Enhanced Nova Notification Handler"
))

# Setup the config options
cfg.CONF.register_opts([
    cfg.ListOpt('notification-topics', default=['notifications']),
    cfg.StrOpt('control-exchange', default='nova'),
    cfg.StrOpt('format', default='%(hostname)s.%(interface)s.%(domain)s'),
], group='handler:nova_enhanced')


class NovaEnhancedHandler(BaseEnhancedHandler):
    """Nova Enhanced Handler"""
    __plugin_name__ = 'nova_enhanced'

    def get_event_types(self):
        return [
            'compute.instance.create.end',
            'compute.instance.delete.start',
        ]

    def process_notification(self, ctx, event_type, payload):
        LOG.info('EnhancedNovaHandler notification: %s. %s', event_type, payload)
        tenant_id = payload['tenant_id']
        context = self._get_context(tenant_id)

        managed = {
            'managed': True,
            'managed_plugin_name': self.get_plugin_name(),
            'managed_plugin_type': self.get_plugin_type(),
            'managed_resource_type': 'instance',
            'managed_resource_id': payload['instance_id']
        }

        if event_type == 'compute.instance.create.end':
            self._create_records(context, managed, payload)
        elif event_type == 'compute.instance.delete.start':
            self._delete_records(context, managed)
