#!/usr/bin/env python
# -*- coding: utf-8 -*-

from troposphere import Ref, Parameter, FindInMap, Base64, Equals, Join
from troposphere.s3 import Bucket

from config import template, CLOUDNAME, CLOUDENV

EMIT = True

def emit_configuration():
    create_bucket = template.add_parameter(
        Parameter(
            "CreateDeployerBucket",
            Type="String",
            Description="Wheter or not to create the deployer bucket",
            Default='no',
            AllowedValues=['yes', 'no']
        )
    )

    condition_name = "DeployerBucketCondition"
    conditions = {
        condition_name: Equals(
            Ref(create_bucket), "yes"
        )
    }

    for c in conditions:
        template.add_condition(c, conditions[c]),

    bucket_name = Join('.', ['deployer', CLOUDNAME, Ref("AWS::Region"), CLOUDENV, 'leafme'])
    bucket = template.add_resource(
        Bucket(
            "DeployerBucket",
            BucketName=bucket_name,
            DeletionPolicy="Retain",
            Condition=condition_name
        )
    )

