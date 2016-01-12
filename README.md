# designate-enhancedhandler
Designate handler to manage notifications from Nova and Neutron

## Build

```sh
# Clone repository
git clone https://github.com/TDAF/designate-enhancedhandler.git
cd designate-enhancedhandler
# Install python dependencies
pip install -r requirements.txt -r test-requirements.txt
python setup.py develop
# Pass unit tests
nosetests -s -v
```

## Installation

After installing [designate](http://docs.openstack.org/developer/designate/) according to [instructions](http://docs.openstack.org/developer/designate/install/ubuntu-dev.html):

* Install from git:

```sh
export GIT_SSL_NO_VERIFY=1
pip install git+https://github.com/TDAF/designate-enhancedhandler.git@master#egg=designate-enhancedhandler
``` 

* Configure the nova and neutron handlers in designate-sink component by editing the file ${OPENSTACK_HOME}/designate/etc/designate/designate.conf:

```
#-----------------------
# Sink Service
#-----------------------
[service:sink]
enabled_notification_handlers = nova_enhanced, neutron_enhanced

[handler:nova_enhanced]
notification_topics = notifications_designate
control_exchange = 'nova'
format = '%(hostname)s.%(interface)s.%(domain)s'

[handler:neutron_enhanced]
notification_topics = notifications_designate
control_exchange = 'neutron'
format = '%(hostname)s.%(interface)s.%(domain)s'
``` 

* Restart all the designate processes to take the changes.

## Manual steps

### Create a domain for reverse resolution (globally)

```
curl -X POST \
     -H 'Accept: application/json' \
     -H 'Content-Type: application/json' \
     -d '{"name": "172.in-addr.arpa.", "ttl": 3600, "email": "john.doe@somewhere.com"}' \
     http://localhost:9001/v1/domains
```

### Create a domain for each project (per tenant)

After creating a project (or tenant), it is required to create a domain where all the records associated to the project will be registered.

```
curl -X POST \
     -H 'Accept: application/json' \
     -H 'Content-Type: application/json' \
     -H 'X-Auth-Sudo-Tenant-ID: 882f9abf240f414a86f687388cecc3b1' \
     -d '{"name": "designate.ost.hi.inet.", "ttl": 3600, "email": "john.doe@somewhere.com"}' \
     http://localhost:9001/v1/domains
```

where X-Auth-Sudo-Tenant-ID identifies the tenant.

## Automatic steps

Consider the following domains:

| Type | Name | Description |
| ---- | ---- | ----------- |
| Project | designate.ost.hi.inet. | Stores all the records (direct resolution) of project hosts |
| Reverse | 172.in-addr.arpa. | Stores all the records (reverse resolution) for addresses 172.x.x.x |
| Reverse | 192.in-addr.arpa. | Stores all the records (reverse resolution) for addresses 192.x.x.x |
| Reverse | 10.in-addr.arpa. | Stores all the records (reverse resolution) for addresses 10.x.x.x |

### Creation of a VM in Nova

Designate-sink receives a notification from nova via rabbitMQ. This notification is processed by NovaEnhancedHandler.

For IP address associated to each network interface, NovaEnhancedHandler will register a record for direct resolution associated to the project domain, and another record for reverse resolution (if there is any domain matching the IP address).

If the notification contains the following info:

* Name: host-01
* Interfaces:
  * Label: private_management, address: 192.168.3.22
  * Label: private_external, address: 172.16.3.26

NovaEnhancedHandler would create the following records:

| Domain | Name | Address |
| ------ | ---- | ------- |
| designate.ost.hi.inet. | host-01.private_management.designate.ost.hi.inet. | 192.168.3.22 |
| designate.ost.hi.inet. | host-01.private_external.designate.ost.hi.inet. | 172.16.3.26 |
| 192.in-addr.arpa. | 22.3.168.192.in-addr.arpa. | 192.168.3.22 |
| 172.in-addr.arpa. | 26.3.16.172.in-addr.arpa. | 172.16.3.26 |

### Removal of a VM in Nova

Designate-sink receives a notification from nova via rabbitMQ. This notification is processed by NovaEnhancedHandler.

It removes all the records associated to the VM and previously managed by NovaEnhancedHandler.

### Adding a floating address

Designate-sink receives a notification from neutron via rabbitMQ. This notification is processed by NeutronEnhancedHandler.

If the notification contains the following info:

* fixed_ip_address: 172.16.3.26
* floating_ip_address: 192.168.49.162

NovaEnhancedHandler would create the following records:

| Domain | Name | Address |
| ------ | ---- | ------- |
| designate.ost.hi.inet. | host-01.floating_private_external.designate.ost.hi.inet. | 192.168.49.162 |
| 192.in-addr.arpa. | 162.49.168.192.in-addr.arpa. | 192.168.49.162 |

**NOTE**: The fully qualified DNS name is obtained from `<hostname>.floating_<interface>.<domain_name>`. A possible improvement is to retrieve the interface name associated to the floating address via neutron, but it is a more complex approach.

### Removing a floating address

Designate-sink receives a notification from neutron via rabbitMQ. This notification is processed by NeutronEnhancedHandler.

It removes all the records associated to the floating address and previously managed by NovaEnhancedHandler.

## License

Copyright 2016 [Telefónica Investigación y Desarrollo, S.A.U](http://www.tid.es)

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License. You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions and limitations under the License. 
