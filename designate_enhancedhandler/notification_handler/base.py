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

from designate.context import DesignateContext
from designate import exceptions
from designate.notification_handler.base import NotificationHandler
from designate.objects import Record
from designate.objects import RecordSet

LOG = logging.getLogger(__name__)


class BaseEnhancedHandler(NotificationHandler):
    """Base Enhanced Handler"""

    def get_exchange_topics(self):
        exchange = cfg.CONF[self.name].control_exchange
        topics = [topic for topic in cfg.CONF[self.name].notification_topics]
        return (exchange, topics)

    def _get_context(self, tenant_id=None):
        if tenant_id:
            return DesignateContext.get_admin_context(tenant=tenant_id, edit_managed_records=True)
        else:
            return DesignateContext.get_admin_context(all_tenants=True, edit_managed_records=True)

    def _get_domain(self, context):
        return self.central_api.find_domain(context, {'tenant_id': context.tenant})

    def _get_reverse_fqdn(self, address, version):
        if version == 6:
            # See https://en.wikipedia.org/wiki/IPv6_address#IPv6_addresses_in_the_Domain_Name_System
            # Convert fdda:5cc1:23:4::1f into f100000000000000400032001cc5addf
            revaddr = map(lambda x: x.ljust(4, '0'), address[::-1].split(':')).join('')
            # Add a dot between each character and the suffix for IP v6
            return list(revaddr).join('.') + '.ip6.arpa.'
        else:
            return '.'.join(address.split('.')[::-1]) + '.in-addr.arpa.'

    def _get_reverse_domains(self, host_reverse_fqdn=None):
        context = self._get_context()
        # TODO: Test if we could get reverse_domains directly with:
        # reverse_domains = self.central_api.find_domains(context, {'name': '*.arpa.'})
        domains = self.central_api.find_domains(context)
        reverse_domains = filter(lambda x: x.name.endswith('.arpa.'), domains)
        if host_reverse_fqdn:
            return filter(lambda x: host_reverse_fqdn.endswith(x.name), reverse_domains)
        else:
            return reverse_domains

    def _get_host_fqdn(self, domain, hostname, interface):
        return cfg.CONF[self.name].get('format') % {
            'hostname': hostname,
            'interface': interface['label'],
            'domain': domain['name']
        }

    def _create_record(self, context, managed, domain, host_fqdn, interface):
        LOG.info('Create record for host: %s and interface: %s', host_fqdn, interface['label'])
        recordset_type = 'AAAA' if interface['version'] == 6 else 'A'
        try:
            recordset = self.central_api.create_recordset(context,
                                                          domain['id'],
                                                          RecordSet(name=host_fqdn, type=recordset_type))
        except exceptions.DuplicateRecordSet:
            LOG.warn('The record: %s was already registered', host_fqdn)
        else:
            record_values = dict(managed, data=interface['address'])
            LOG.debug('Creating record in %s / %s with values %r', domain['id'], recordset['id'], record_values)
            self.central_api.create_record(context,
                                           domain['id'],
                                           recordset['id'],
                                           Record(**record_values))

    def _create_reverse_record(self, context, managed, host_fqdn, interface):
        LOG.info('Create reverse record for interface: %s and address: %s', interface['label'], interface['address'])
        host_reverse_fqdn = self._get_reverse_fqdn(interface['address'], interface['version'])
        LOG.info('Create reverse record: %s', host_reverse_fqdn)
        reverse_domains = self._get_reverse_domains(host_reverse_fqdn)
        admin_context = DesignateContext.get_admin_context(all_tenants=True)
        for reverse_domain in reverse_domains:
            LOG.info('Create reverse record for domain: %s', reverse_domain.name)
            try:
                recordset = self.central_api.create_recordset(admin_context,
                                                              reverse_domain.id,
                                                              RecordSet(name=host_reverse_fqdn, type='PTR'))
            except exceptions.DuplicateRecordSet:
                LOG.warn('The reverse record: %s was already registered', host_reverse_fqdn)
            else:
                record_values = dict(managed, data=host_fqdn)
                LOG.debug('Creating reverse record in %s / %s with values %r',
                          reverse_domain.id, recordset['id'], record_values)
                self.central_api.create_record(admin_context,
                                               reverse_domain.id,
                                               recordset['id'],
                                               Record(**record_values))

    def _create_records(self, context, managed, payload):
        try:
            domain = self._get_domain(context)
        except exceptions.DomainNotFound:
            LOG.warn('There is no domain registered for tenant: %s', context.tenant)
        except Exception as e:
            LOG.error('Error getting the domain for tenant: %s. %s', context.tenant, e)
        else:
            hostname = payload['hostname']
            LOG.info('Creating records for host: %s in tenant: %s using domain: %s',
                     hostname, context.tenant, domain['name'])
            for interface in payload['fixed_ips']:
                LOG.info('Create records for interface: %s', interface['label'])
                host_fqdn = self._get_host_fqdn(domain, hostname, interface)
                self._create_record(context, managed, domain, host_fqdn, interface)
                self._create_reverse_record(context, managed, host_fqdn, interface)

    def _delete_records(self, context, managed):
        records = self.central_api.find_records(context, managed)
        if len(records) == 0:
            LOG.info('No record found to be deleted')
        else:
            for record in records:
                LOG.info('Deleting record %s', record['id'])
                try:
                    self.central_api.delete_record(context,
                                                   record['domain_id'],
                                                   record['recordset_id'],
                                                   record['id'])
                except exceptions.DomainNotFound:
                    LOG.warn('There is no domain registered with id: %s', record['domain_id'])
                except Exception as e:
                    LOG.error('Error deleting record: %s. %s', record['id'], e)
