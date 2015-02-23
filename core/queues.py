#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This module creates the babysitter instance and services

import json

from troposphere import Parameter, Ref, FindInMap, Base64, GetAtt, Tags
import troposphere.autoscaling as autoscaling
from troposphere.autoscaling import EC2_INSTANCE_TERMINATE
import troposphere.cloudwatch as cloudwatch
import troposphere.ec2 as ec2
import troposphere.sns as sns
import troposphere.iam as iam
from troposphere.sqs import QueuePolicy, Queue

import config as cfn
from config import CIDR_PREFIX, VPC_NAME, CLOUDNAME, CLOUDENV, ASSUME_ROLE_POLICY, template
from config import USE_PRIVATE_SUBNETS, DEFAULT_ROUTE

def emit_configuration():
    # Build an SQS queue for the babysitter
    queue_name = '_'.join(['chef-deregistration', CLOUDNAME, CLOUDENV])
    queue = template.add_resource(
        Queue(
            cfn.sanitize_id(queue_name),
            VisibilityTimeout=60,
            MessageRetentionPeriod=1209600,
            MaximumMessageSize=16384,
            QueueName=queue_name
        )
    )

    alert_topic = template.add_resource(
        sns.Topic(
            "BabysitterAlarmTopic",
            DisplayName='Babysitter Alarm',
            TopicName=queue_name,
            Subscription=[
                sns.Subscription(
                    Endpoint=GetAtt(queue, "Arn"),
                    Protocol='sqs'
                ),
            ],
            DependsOn=queue.title
        )
    )

    queue_depth_alarm = template.add_resource(
        cloudwatch.Alarm(
            "BabysitterQueueDepthAlarm",
            AlarmDescription='Alarm if the queue depth grows beyond 200 messages',
            Namespace='AWS/SQS',
            MetricName='ApproximateNumberOfMessagesVisible',
            Dimensions=[
                cloudwatch.MetricDimension(
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
            DependsOn=alert_topic.title
        ),
    )

    queue_policy = {
        "Version": "2012-10-17",
        "Id": "BabysitterSNSPublicationPolicy",
        "Statement": {
            "Sid":"AllowSNSPublishing",
            "Effect": "Allow",
            "Principal": {
                "AWS": Ref("AWS::AccountId")
            },
            "Action": "sqs:SendMessage",
            "Resource": GetAtt(queue, "Arn"),
            "Condition": {
                "ArnEquals": {"aws:SourceArn": Ref(alert_topic)}
            }
        }
    }

    # Publish all events from SNS to the Queue
    template.add_resource(
        QueuePolicy(
            "BabysitterPublishSNStoSQSPolicy",
            Queues=[Ref(queue)],
            PolicyDocument=queue_policy,
            DependsOn=queue.title
        )
    )

    cfn.alert_topic = alert_topic
