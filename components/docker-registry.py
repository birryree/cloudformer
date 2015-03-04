#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This module creates the docker registry's dependencies like S3 buckets

from troposphere import Ref, Parameter, FindInMap, Base64, Equals, Join
from troposphere.s3 import Bucket

from config import template, CLOUDNAME, CLOUDENV

EMIT = True

def emit_configuration():
    create_bucket = template.add_parameter(
        Parameter(
            'CreateDockerRegistryBucket',
            Type='String',
            Description='Whether or not to create the Docker Registry bucket.',
            Default='no',
            AllowedValues=['yes', 'no']
        )
    )

    condition_name = "DockerRegistryBucketCondition"
    conditions = {
        condition_name: Equals(
            Ref(create_bucket), "yes"
        )
    }

    for c in conditions:
        template.add_condition(c, conditions[c])

    # Create the registry bucket
    bucket_name = Join('.', ['docker-registry', CLOUDNAME, Ref("AWS::Region"), CLOUDENV, 'leafme'])
    bucket = template.add_resource(
        Bucket(
            "DockerRegistryBucket",
            BucketName=bucket_name,
            DeletionPolicy='Retain',
            Condition=condition_name
        )
    )
