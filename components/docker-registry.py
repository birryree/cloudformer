#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This module creates the docker registry's dependencies like S3 buckets

import json

from troposphere import Ref, Parameter, FindInMap, Base64, Equals, Join
from troposphere.s3 import Bucket
from troposphere.autoscaling import LaunchConfiguration, AutoScalingGroup, NotificationConfiguration
from troposphere.ec2 import SecurityGroupRule, SecurityGroup, SecurityGroupIngress
from troposphere.iam import Role, Group, PolicyType, Policy, InstanceProfile
from troposphere.autoscaling import EC2_INSTANCE_TERMINATE, EC2_INSTANCE_LAUNCH, EC2_INSTANCE_LAUNCH_ERROR, EC2_INSTANCE_TERMINATE_ERROR

import config as cfn
from config import template, CLOUDNAME, CLOUDENV, CIDR_PREFIX, ASSUME_ROLE_POLICY, DEFAULT_ROUTE

EMIT = True

def emit_configuration():
    vpc = cfn.vpcs[0]

    instance_class = template.add_parameter(
        Parameter(
            'RegistryInstanceType', Type='String', Default='m3.medium',
            Description='Registry instance type',
            AllowedValues=cfn.usable_instances(),
        )
    )

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

    ingress_rules = [
        SecurityGroupRule(
            IpProtocol=p[0], CidrIp=DEFAULT_ROUTE, FromPort=p[1], ToPort=p[1]
        ) for p in [('tcp', 80), ('tcp', 22)]
    ]

    sg = template.add_resource(
        SecurityGroup(
            "DockerRegistry",
            GroupDescription="Security Group for Docker Registries",
            VpcId=Ref(vpc),
            SecurityGroupIngress=ingress_rules,
            DependsOn=vpc.title
        )
    )

    policy_vars = { "env": CLOUDENV, "cloud": CLOUDNAME, "region": "us-east-1" }
    # IAM role for docker registry
    policy = json.loads(cfn.load_template("registry_policy.json.j2", policy_vars))

    default_policy = json.loads(cfn.load_template("default_policy.json.j2", policy_vars))

    iam_role = template.add_resource(
        Role(
            "DockerRegistryIamRole",
            AssumeRolePolicyDocument=ASSUME_ROLE_POLICY,
            Path="/",
            Policies=[
                Policy(
                    PolicyName="RegistryDefaultPolicy",
                    PolicyDocument=default_policy
                ),
                Policy(
                    PolicyName="RegistryPolicy",
                    PolicyDocument=policy
                )
            ],
            DependsOn=vpc.title
        )
    )

    instance_profile = template.add_resource(
        InstanceProfile(
            "DockerRegistryInstanceProfile",
            Path="/",
            Roles=[Ref(iam_role)],
            DependsOn=iam_role.title
        )
    )

    user_data = cfn.load_template("default-init.bash.j2",
        {"env": CLOUDENV, "cloud": CLOUDNAME, "deploy": "docker_registry"}
    )

    launch_config = template.add_resource(
        LaunchConfiguration(
            "RegistryLaunchConfiguration",
            ImageId=FindInMap('RegionMap', Ref("AWS::Region"), int(cfn.Amis.INSTANCE)),
            InstanceType=Ref(instance_class),
            IamInstanceProfile=Ref(instance_profile),
            KeyName=Ref(cfn.keyname),
            SecurityGroups=[Ref(sg)],
            DependsOn=[instance_profile.title, sg.title],
            AssociatePublicIpAddress=False,
            UserData=Base64(user_data)
        )
    )

    asg = template.add_resource(
        AutoScalingGroup(
            "RegistryAutoscalingGroup",
            AvailabilityZones=cfn.get_asg_azs(),
            DesiredCapacity="1",
            LaunchConfigurationName=Ref(launch_config),
            MinSize="1",
            MaxSize="1",
            NotificationConfiguration=NotificationConfiguration(
                TopicARN=Ref(cfn.alert_topic),
                NotificationTypes=[
                    EC2_INSTANCE_TERMINATE, EC2_INSTANCE_LAUNCH, EC2_INSTANCE_LAUNCH_ERROR, EC2_INSTANCE_TERMINATE_ERROR
                ]
            ),
            VPCZoneIdentifier=[Ref(sn) for sn in cfn.get_vpc_subnets(vpc, cfn.SubnetTypes.PLATFORM)],
            DependsOn=[sn.title for sn in cfn.get_vpc_subnets(vpc, cfn.SubnetTypes.PLATFORM)]
        )
    )
