########
# Copyright (c) 2015 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#    * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    * See the License for the specific language governing permissions and
#    * limitations under the License.

import os
import time

# Third-party Imports
from boto import exception
from collections import Counter
from collections import namedtuple
from datetime import timedelta, datetime

# Cloudify imports
from cloudify import ctx
from cloudify import compute
from cloudify_aws.ec2.instance import Instance
from cloudify_aws.ec2 import passwd
from cloudify.decorators import operation
from cloudify_aws.base import AwsBaseNode
from cloudify_aws import utils, constants
from cloudify.exceptions import NonRecoverableError

@operation
def creation_validation(**_):
    return SpotInstance().creation_validation()


@operation
def create(args=None, **_):
    return SpotInstance().created(args)


@operation
def start(args=None, start_retry_interval=30, private_key_path=None, **_):
    return SpotInstance().started(args, start_retry_interval, private_key_path)


@operation
def delete(args=None, **_):
    return SpotInstance().deleted(args)


@operation
def modify_attributes(new_attributes, args=None, **_):
    return SpotInstance().modified(new_attributes, args)


@operation
def stop(args=None, **_):
    return SpotInstance().stopped(args)


SpotRequestInfo = namedtuple('SpotRequestInfo', ['instance_id', 'request_id'])


class SpotInstance(Instance):

    def __init__(self, client=None):
        super(SpotInstance, self).__init__(client=client)
        self._pricing_history = []
        self._max_bid_price = 0.1

    def _get_instance_parameters(self):
        parameters = super(SpotInstance, self)._get_instance_parameters()
        parameters.update({'availability_zone': ctx.node.properties['availability_zone'],
                           'max_bid_price': ctx.node.properties['max_bid_price']})
        ctx.logger.info('parameters: {0}'.format(parameters))
        return parameters

    def create(self, args=None, **_):
        ctx.logger.info('Going to create spot instance')
        instance_parameters = self._get_instance_parameters()
        availability_zone = instance_parameters.get('availability_zone')
        instance_type = instance_parameters.get('instance_type')
        image_id = instance_parameters.get('image_id')
        key_name = instance_parameters.get('key_name')
        max_bid_price = instance_parameters.get('max_bid_price')
        security_group_ids = instance_parameters.get('security_group_ids')
        ctx.logger.info('Retrieving spot instance pricing history, for: {0}@{1}'
                        .format(instance_type, availability_zone))
        self._pricing_history = self._spot_pricing_history(instance_type, availability_zone)
        if not self._pricing_history:
            raise NonRecoverableError('Failed to retrieve spot pricing history')

        ctx.logger.info(
            'Attempting to create EC2 Spot Instance with these API '
            'parameters: {0}.'.format(instance_parameters))

        sg_names = self._security_group_names(security_group_ids)
        self._max_bid_price = max_bid_price

        spot_request_info = self._create_spot_instances(
            instance_type=instance_type,
            image_id=image_id,
            availability_zone_group=availability_zone,
            key_name=key_name,
            security_groups=sg_names)

        self.resource_id = spot_request_info.instance_id
        ctx.logger.info('Saving request_id: {0}'.format(spot_request_info.request_id))
        ctx.instance.runtime_properties['request_id'] = spot_request_info.request_id

        instance = self._get_instance_from_id(spot_request_info.instance_id)
        if instance is None:
            return False

        ctx.logger.info('Setting external ip')
        utils.set_external_resource_id(
            spot_request_info.instance_id, ctx.instance, external=False)
        self._instance_created_assign_runtime_properties()
        return True

    def stop(self, args=None, **_):
        ctx.logger.info('Spot instance can not be stopped, Cancelling request')
        request_id = ctx.instance.runtime_properties['request_id']
        ctx.logger.info('Retrieved request_id: {0}'.format(request_id))
        if not request_id:
            raise NonRecoverableError('Failed to cancel spot request! '
                                      'Failed to retrieve spot request_id ')
        self._cancel_spot_instance_requests(request_id)
        ctx.logger.info('Un-assigning resources')
        utils.unassign_runtime_properties_from_resource(
            property_names=constants.INSTANCE_INTERNAL_ATTRIBUTES,
            ctx_instance=ctx.instance)
        return True

    def _spot_pricing_history(self, instance_type, availability_zone):
        ctx.logger.info('Retrieving spot_pricing_history, '
                        'for availability_zone: {0}'.format(availability_zone))
        yesterday = datetime.today() - timedelta(1)
        today = datetime.today()
        results = self.execute(self.client.get_spot_price_history,
                               dict(start_time=yesterday.isoformat(),
                                    end_time=today.isoformat(),
                                    instance_type=instance_type,
                                    availability_zone=availability_zone),
                               raise_on_falsy=True)
        price_history = [botoSpotPriceHistory.price for botoSpotPriceHistory in results]
        price_history = Counter(price_history)
        ctx.logger.info('Spot pricing history: {0}'.format(price_history))
        return price_history

    def _security_group_names(self, security_group_ids):
        ctx.logger.info('Retrieving security groups names for: {0}'.format(security_group_ids))
        sg = self.execute(self.client.get_all_security_groups,
                          dict(group_ids=security_group_ids),
                          raise_on_falsy=True)
        sg = [botoSecurityGroup.name for botoSecurityGroup in sg]
        ctx.logger.info('Security groups names: {0}'.format(sg))
        return sg

    def _get_all_spot_instance_requests(self):
        ctx.logger.debug('Retrieving all spot requests')
        sr = self.execute(self.client.get_all_spot_instance_requests,
                          raise_on_falsy=True)
        return sr

    def _create_spot_instances_at_price(self, instance_type,
                                        image_id,
                                        availability_zone_group,
                                        key_name,
                                        security_groups,
                                        price):
        arguments = dict(price=price,
                         instance_type=instance_type,
                         image_id=image_id,
                         availability_zone_group=availability_zone_group,
                         placement=availability_zone_group,
                         key_name=key_name,
                         security_groups=security_groups)
        ctx.logger.info('Sending spot request, arguments: {0}'.format(arguments))
        spot_req = self.execute(self.client.request_spot_instances, arguments, raise_on_falsy=True)
        if not spot_req:
            raise NonRecoverableError('Failed to create spot request')
        spot_req = spot_req[0]

        ctx.logger.info('Waiting for request to be fulfill')
        job_instance_id = None
        sleep_between_iterations_sec = 2
        timeout = 20
        while timeout and not job_instance_id:
            ctx.logger.info("Checking job instance id for spot request: {0}".format(spot_req.id))
            job_sir_id = spot_req.id
            spot_requests = self._get_all_spot_instance_requests()
            for sir in spot_requests:
                if sir.id == job_sir_id:
                    job_instance_id = sir.instance_id
                    if job_instance_id:
                        ctx.logger.info("Found instance for request!")
                    break
            time.sleep(sleep_between_iterations_sec)
            timeout -= 1
        if not job_instance_id:
            self._cancel_spot_instance_requests(spot_req.id)
            return SpotRequestInfo(None, None)
        else:
            ctx.logger.info("Created spot instance id: {0}, spot request id: {1}"
                            .format(job_instance_id, spot_req.id))
            return SpotRequestInfo(job_instance_id, spot_req.id)

    def _cancel_spot_instance_requests(self, spot_req_id, raise_on_falsy=True):
        ctx.logger.info('Canceling spot request: {0}'.format(spot_req_id))
        res = self.execute(self.client.cancel_spot_instance_requests,
                           dict(request_ids=[spot_req_id]),
                           raise_on_falsy=raise_on_falsy)
        ctx.logger.info('Requests cancelled: {0}'.format(res))

    def _create_spot_instances(self, **kwargs):
        lowest_bid_price = self._lowest_bid_price()
        interval = 0.0001
        bid_price = round(lowest_bid_price, 2) * 2
        max_attempts = 5
        while bid_price <= self._max_bid_price and max_attempts:
            ctx.logger.info('Creating instance with price: {0}, args: {1}'
                            .format(bid_price, kwargs))
            spot_request_info = self._create_spot_instances_at_price(price=bid_price, **kwargs)
            if spot_request_info and spot_request_info.instance_id:
                return spot_request_info
            ctx.logger.warning('Creating instance with price: {0} Failed'.format(bid_price))
            bid_price += interval
            max_attempts -= 1
        return NonRecoverableError('Failed to create spot instance!')

    def _lowest_bid_price(self):
        pricing_list = sorted(list(self._pricing_history))
        ctx.logger.info("Spot pricing ordered: {0}".format(pricing_list))
        return pricing_list[0]

    # def _remove_low_and_rare_prices(self):
    #     pricing_list = sorted(list(self._pricing_history))
    #     ctx.logger.info("Spot pricing ordered: {0}".format(pricing_list))

        # prices_to_remove = []
        # min_occur = 40
        # for price in pricing_list:
        #     if self._pricing_history[price] < min_occur:
        #         prices_to_remove.append(price)
        # for price in prices_to_remove:
        #     pricing_list.remove(price)
        # ctx.logger.info('Updated prices list: {0}'.format(pricing_list))
        # return sorted(pricing_list)

    # def _delete_spot_instance(self):
    #     instance = get_instance(conn)
    #     if instance:
    #         logger.info('Terminating instance: {0}'.format(instance))
    #         instance.terminate()
    #         wait_for_instance_status(instance, 'terminated')
