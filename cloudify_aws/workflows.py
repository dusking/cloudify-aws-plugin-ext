######
# Copyright (c) 2017 Faaspot Technologies Ltd. All rights reserved
#

from cloudify.decorators import workflow
from cloudify.plugins import lifecycle
from cloudify.manager import get_node_instance


HOST_NODE_TYPE = 'cloudify.aws.nodes.Instance'
ELASTICIP_NODE_TYPE = 'cloudify.aws.nodes.ElasticIP'
EXTERNAL_RESOURCE_ID = 'aws_resource_id'
RESOURCE_ID = 'resource_id'


@workflow
def refresh_ip(ctx, **kwargs):
    ctx.logger.info("Starting 'refresh_ip' workflow")
    host_instance = None
    ip_instance = None

    for instance in set(ctx.node_instances):
        if ELASTICIP_NODE_TYPE in instance.node.type_hierarchy:
            ip_instance = instance
        elif HOST_NODE_TYPE in instance.node.type_hierarchy:
            host_instance = instance

    if not ip_instance or not host_instance:
        ctx.logger.info('Missing components for refresh ip..')
        return

    # host_runtime_properties = get_node_instance(host_instance.id).runtime_properties)
    # ip_runtime_properties = get_node_instance(ip_instance.id).runtime_properties)
    ctx.logger.info("Going to reinstall node: {0}".format(ip_instance.id))
    lifecycle.reinstall_node_instances(graph=ctx.graph_mode(),
                                       node_instances=[ip_instance],
                                       related_nodes=[host_instance],
                                       ignore_failure=False)
    # ip_runtime_properties = get_node_instance(ip_instance.id).runtime_properties)
    ctx.logger.info('completed')
