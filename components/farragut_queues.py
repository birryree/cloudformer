#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This module creates the queues that farragut requires

from collections import namedtuple

from troposphere import Parameter, Ref, FindInMap, Base64, GetAtt, Tags
from troposphere.sqs import QueuePolicy, Queue

import config as cfn
from config import CIDR_PREFIX, VPC_NAME, CLOUDNAME, CLOUDENV, ASSUME_ROLE_POLICY
from config import template

QueueConfig = namedtuple('QueueConfig', ['name', 'visibility', 'retention', 'max_size'])


def emit_configuration():
    # Build the 6 sqs queues for farragut
    queues = [
        QueueConfig('farragut-aggregate-{0}'.format(CLOUDENV), 1800, 345600, 262144),
        QueueConfig('farragut-hourly-{0}'.format(CLOUDENV), 180, 345600, 262144),
        QueueConfig('farragut-leaf-site-{0}'.format(CLOUDENV), 30, 345600, 262144),
        QueueConfig('farragut-leaf-{0}'.format(CLOUDENV), 30, 345600, 262144),
        QueueConfig('farragut-{0}'.format(CLOUDENV), 1800, 345600, 262144),
        QueueConfig('farragut-import-{0}'.format(CLOUDENV), 30, 345600, 262144)
    ]
    for q in queues:
        template.add_resource(
            Queue(
                cfn.sanitize_id(q.name),
                VisibilityTimeout=q.visibility,
                MessageRetentionPeriod=q.retention,
                MaximumMessageSize=q.max_size,
                QueueName=q.name
            )
        )
