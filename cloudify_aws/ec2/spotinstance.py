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


class SpotInstance(Instance):

    def __init__(self, client=None):
        super(SpotInstance, self).__init__(
                client=client
        )
        self._pricing_history = []

    # def creation_validation(self, **_):
    #     return super(SpotInstance, self).creation_validation()
    #
    # def created(self, args=None):
    #     ctx.logger.info('Creating a spot instance')
    #     return super(SpotInstance, self).created(args)
    #
    # def started(self, args=None, start_retry_interval=30,
    #             private_key_path=None):
    #     ctx.logger.info('Starting spot instance')
    #     return super(SpotInstance, self).started(args,
    #                                              start_retry_interval,
    #                                              private_key_path)
    #
    # def stopped(self, args=None):
    #     ctx.logger.info('Stopping a spot instance')
    #     return super(SpotInstance, self).stopped(args)
    #
    # def deleted(self, args=None, **_):
    #     ctx.logger.info('Deleting spot instance')
    #     return super(SpotInstance, self).delete(args)
    #
    # def modify_attributes(self, new_attributes, args=None, **_):
    #     return super(SpotInstance, self).modify_attributes(new_attributes, args)

    def create(self, args=None, **_):
        ctx.logger.info('Spot instance create')
        instance_parameters = self._get_instance_parameters()

        ctx.logger.info('Retrieving spot instance pricing history')
        self._pricing_history = self._spot_pricing_history(instance_parameters['instance_type'])
        if not self._pricing_history:
            raise NonRecoverableError('Failed to retrieve spot pricing history')

        ctx.logger.info(
            'Attempting to create EC2 Spot Instance with these API '
            'parameters: {0}.'.format(instance_parameters))

        sg_names = self._security_group_names(instance_parameters['security_group_ids'])
        instance_id = self._create_spot_instances(
            instance_type=instance_parameters['instance_type'],
            image_id=instance_parameters['image_id'],
            availability_zone_group='eu-central-1a',
            key_name=instance_parameters['key_name'],
            security_groups=sg_names)

        self.resource_id = instance_id
        # ctx.instance.runtime_properties['reservation_id'] = reservation.id

        instance = self._get_instance_from_id(instance_id)

        if instance is None:
            return False

        ctx.logger.info('Setting external ip')
        utils.set_external_resource_id(
            instance_id, ctx.instance, external=False)
        self._instance_created_assign_runtime_properties()

        self.save_node_data()

        return True

    def start(self, args=None, start_retry_interval=30,
              private_key_path=None, **_):
        ctx.logger.info('Starting spot instance')
        return super(SpotInstance, self).start(args, start_retry_interval,
                                               private_key_path)

    def stop(self, args=None, **_):
        ctx.logger.info('Spot instance can not be stopped, unassigning resources')
        utils.unassign_runtime_properties_from_resource(
            property_names=constants.INSTANCE_INTERNAL_ATTRIBUTES,
            ctx_instance=ctx.instance)
        return True

    # def modified(self, new_attributes, args=None):
    #     ctx.logger.info('Modifying spot instance')
    #     return super(SpotInstance, self).modified(new_attributes, args)

    def _spot_pricing_history(self, instance_type, availability_zone='eu-central-1a'):
        ctx.logger.info('retrieving spot_pricing_history')
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
        ctx.logger.info('spot pricing history: {0}'.format(price_history))
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
                         key_name=key_name,
                         security_groups=security_groups)
        spot_req = self.execute(self.client.request_spot_instances, arguments, raise_on_falsy=True)
        if not spot_req:
            raise NonRecoverableError('Failed to create spot instance request')
        spot_req = spot_req[0]

        ctx.logger.info('Waiting for instance status to be running')
        job_instance_id = None
        sleep_between_iterations_sec = 2
        timeout = 20
        while timeout and not job_instance_id:
            ctx.logger.debug("checking job instance id for spot request: {0}, "
                             "with max price: {1}".format(spot_req.id, spot_req.price))
            job_sir_id = spot_req.id
            spot_requests = self._get_all_spot_instance_requests()
            for sir in spot_requests:
                if sir.id == job_sir_id:
                    job_instance_id = sir.instance_id
                    ctx.logger.debug("job instance id: {0}".format(str(job_instance_id)))
                    break
            time.sleep(sleep_between_iterations_sec)
            timeout -= 1

        if not job_instance_id:
            ctx.logger.debug('Canceling spot request: {0}'.format(spot_req.id))
            self._cancel_spot_instance_requests(spot_req.id)
        else:
            ctx.logger.info("Spot instance id: {0}".format(job_instance_id))
        return job_instance_id

    def _cancel_spot_instance_requests(self, spot_req_id):
        res = self.execute(self.client.cancel_spot_instance_requests,
                           dict(request_ids=[spot_req_id]),
                           raise_on_falsy=True)
        ctx.logger.info('Requests terminated: {0}'.format(res))

    def _create_spot_instances(self, **kwargs):
        job_instance_id = None

        # pricing_list = sorted(list(self._pricing_history))
        pricing_list = self._remove_low_and_rare_prices()
        for price in pricing_list[5:]:
            ctx.logger.info('Creating instance with price: {0}, args: {1}'.format(price, kwargs))
            job_instance_id = self._create_spot_instances_at_price(price=price, **kwargs)
            if job_instance_id:
                break
            ctx.logger.warning('Creating instance with price: {0} Failed'.format(price))

        return job_instance_id

    def _remove_low_and_rare_prices(self):
        pricing_list = sorted(list(self._pricing_history))
        ctx.logger.info("Spot pricing ordered: {0}".format(pricing_list))

        prices_to_remove = []
        min_occur = 50
        for price in pricing_list:
            if self._pricing_history[price] < min_occur:
                prices_to_remove.append(price)
        for price in prices_to_remove:
            pricing_list.remove(price)
        ctx.logger.info('Updated prices list: {0}'.format(pricing_list))
        return sorted(pricing_list)

    def _delete_spot_instance(self):
        instance = get_instance(conn)
        if instance:
            logger.info('Terminating instance: {0}'.format(instance))
            instance.terminate()
            wait_for_instance_status(instance, 'terminated')

    def save_node_data(self):
        ctx.logger.info('save_node_data')

        try:
            destination = os.path.expanduser('~/host.txt')
            with open(destination, 'w') as config_file:
                config_file.write(ctx.instance.id)
            ctx.logger.info('save_node_data saved to: {0}'.format(destination))
        except Exception as ex:
            ctx.logger.info('save_node_data failed: {0}'.format(ex))
