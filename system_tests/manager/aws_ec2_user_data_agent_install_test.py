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

from cosmo_tester.framework.testenv import TestCase

DEFAULT_EXECUTE_TIMEOUT = 1800


class AWSEC2UserDataAgentInstallTest(TestCase):

    def test_user_data_agent_install(self):

        blueprint_path = \
            self.copy_blueprint('resources', os.path.dirname(__file__))

        self.blueprint_yaml = \
            os.path.join(blueprint_path,
                         'user-data-agent-install-blueprint.yaml')

        self.upload_deploy_and_execute_install(
            inputs=self.get_inputs(),
            timeout=DEFAULT_EXECUTE_TIMEOUT
        )

        instance = self.client.node_instances.list(
            node_id='test_user_data_script', deployment_id=self.test_id)[0]
        self.assertIn('test', instance.runtime_properties.keys())
        self.assertEqual(
            instance.runtime_properties['test'],
            'Say hello to my little friend!')

    def get_inputs(self):

        return {
            'image': self.env.centos_7_image_id,
            'size': self.env.medium_instance_type,
        }
