#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This module creates the babysitter instance and services


from troposphere import Parameter, Ref, FindInMap, Equals, GetAtt, Tags
from troposphere.cloudwatch import Alarm, MetricDimension
from troposphere.sns import Topic, Subscription
from troposphere.sqs import QueuePolicy, Queue

import config as cfn
from config import CIDR_PREFIX, VPC_NAME, CLOUDNAME, CLOUDENV, ASSUME_ROLE_POLICY, template
from config import USE_PRIVATE_SUBNETS, DEFAULT_ROUTE

def emit_configuration():
    # Build an SQS queue for the babysitter

    """create_queue = template.add_parameter(
        Parameter(
            'CreateDeregistrationTopic',
            Type='String',
            Description='Whether or not to create the Chef Deregistration queue. This option is provided in case the queue already exists.',
            Default='no',
            AllowedValues=['yes', 'no'],
            ConstraintDescription='Answer must be yes or no'
        )
    )

    conditions = {
        "CreateDeregCondition": Equals(
            Ref(create_queue), "yes"
        )
    }

    for c in conditions:
        template.add_condition(c, conditions[c])"""


    queue_name = '_'.join(['chef-deregistration', CLOUDNAME, CLOUDENV])
    queue = template.add_resource(
        Queue(
            cfn.sanitize_id(queue_name),
            VisibilityTimeout=60,
            MessageRetentionPeriod=1209600,
            MaximumMessageSize=16384,
            QueueName=queue_name,
        )
    )

    alert_topic = template.add_resource(
        Topic(
            cfn.sanitize_id("BabysitterAlarmTopic{0}".format(CLOUDENV)),
            DisplayName='Babysitter Alarm',
            TopicName=queue_name,
            Subscription=[
                Subscription(
                    Endpoint=GetAtt(queue, "Arn"),
                    Protocol='sqs'
                ),
            ],
            DependsOn=queue.title,
        )
    )

    queue_depth_alarm = template.add_resource(
        Alarm(
            "BabysitterQueueDepthAlarm",
            AlarmDescription='Alarm if the queue depth grows beyond 200 messages',
            Namespace='AWS/SQS',
            MetricName='ApproximateNumberOfMessagesVisible',
            Dimensions=[
                MetricDimension(
                    Name='QueueName',
                    Value=GetAtt(queue, "QueueName")
                )
            ],
            Statistic='Sum',
            Period='300',
            EvaluationPeriods='1',
            Threshold='200',
            ComparisonOperator='GreaterThanThreshold',
            #AlarmActions=[Ref(alert_topic), ],
            #InsufficientDataActions=[Ref(alert_topic), ],
            DependsOn=alert_topic.title,
        ),
    )

    queue_policy = {
        "Version": "2012-10-17",
        "Id": "BabysitterSNSPublicationPolicy",
        "Statement": [{
            "Sid": "AllowSNSPublishing",
            "Effect": "Allow",
            "Principal": {
                "AWS": "*"
            },
            "Action": ["sqs:SendMessage"],
            "Resource": GetAtt(queue, "Arn"),
            "Condition": {
                "ArnEquals": {"aws:SourceArn": Ref(alert_topic)}
            }
        }]
    }

    # Publish all events from SNS to the Queue
    template.add_resource(
        QueuePolicy(
            "BabysitterPublishSNStoSQSPolicy",
            Queues=[Ref(queue)],
            PolicyDocument=queue_policy,
            DependsOn=[queue.title, alert_topic.title],
        )
    )

    cfn.alert_topic = alert_topic
