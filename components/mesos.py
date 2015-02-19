#/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import os
import subprocess

import yaml
from troposphere import Parameter

import config as cfn

EMIT = False

def emit_configuration():
    vpc = cfn.vpcs[0]
    template = cfn.template

    mesos_instance_class = template.add_parameter(
        Parameter(
            'MesosInstanceType', Type='String', Default='m3.large',
            Description='Mesos instance type (for workers and masters)',
            AllowedValues=cfn.usable_instances(),
            ConstraintDescription='Instance size must be a valid instance type'
        )
    )

    mesos_security_group = template.add_resource(
        SecurityGroup(
            "MesosSecurityGroup",
            GroupDescription="Security Group for Mesos instances",
            VpcId=Ref(vpc),
            DependsOn=vpc.title
        )
    )

    # Allow any mesos instances to talk to each other
    template.add_resource(
        SecurityGroupIngress(
            "MesosSelfIngress",
            IpProtocol='-1',
            FromPort=0,
            ToPort=65535,
            GroupId=Ref(mesos_security_group),
            SourceSecurityGroupId=Ref(mesos_security_group),
            DependsOn=mesos_security_group.title
        )
    )

    # IAM role here

    # Instance profile here

    # UserData here

    # LaunchConfiguration

    # Autoscaling Group
