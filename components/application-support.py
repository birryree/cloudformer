#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This module creates the stuff necessary to make deploy-thing apps go.

import json

from troposphere import Parameter, Ref, FindInMap, Base64, GetAtt, Tags
import troposphere.autoscaling as autoscaling
from troposphere.autoscaling import EC2_INSTANCE_TERMINATE, EC2_INSTANCE_LAUNCH, EC2_INSTANCE_LAUNCH_ERROR, EC2_INSTANCE_TERMINATE_ERROR
import troposphere.cloudwatch as cloudwatch
import troposphere.ec2 as ec2
import troposphere.sns as sns
import troposphere.sqs as sqs
import troposphere.iam as iam

import config as cfn
from config import CIDR_PREFIX, VPC_NAME, CLOUDNAME, CLOUDENV, ASSUME_ROLE_POLICY, template
from config import USE_PRIVATE_SUBNETS, DEFAULT_ROUTE

def emit_configuration():
    # BEGIN SSH-ACCESSIBLE SECURITY GROUP
    ssh_ingress_rules = [
        ec2.SecurityGroupRule(
            IpProtocol='tcp', CidrIp=DEFAULT_ROUTE, FromPort=p, ToPort=p
        ) for p in [22]
    ]

    ssh_security_group = template.add_resource(
        ec2.SecurityGroup(
            "SSHAccessible",
            # TODO: this needs to not be DEFAULT_ROUTE.
            GroupDescription='allows SSH into the machine.',
            VpcId=Ref(cfn.vpcs[0]),
            SecurityGroupIngress=ssh_ingress_rules,
            DependsOn=cfn.vpcs[0].title
        )
    )
    # END SSH-ACCESSIBLE SECURITY GROUP
