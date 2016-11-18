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

# Third-party Imports
from boto import exception

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

    def creation_validation(self, **_):
        return super(SpotInstance, self).creation_validation()

    def create(self, args=None, **_):
        return super(SpotInstance, self).create(args)

    def start(self, args=None, start_retry_interval=30,
              private_key_path=None, **_):
        return super(SpotInstance, self).start(args, start_retry_interval,
                                               private_key_path)

    def delete(self, args=None, **_):
        return super(SpotInstance, self).delete(args)

    def modify_attributes(self, new_attributes, args=None, **_):
        return super(SpotInstance, self).modify_attributes(new_attributes, args)

    def stop(self, args=None, **_):
        return super(SpotInstance, self).stop(args)
