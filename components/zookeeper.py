#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This module creates zookeeper stuff

import json

from troposphere import Ref, Parameter, FindInMap, Base64, Equals, Join
from troposphere.s3 import Bucket
from troposphere.iam import Role, Group, PolicyType, Policy, InstanceProfile
from troposphere.ec2 import SecurityGroupRule, SecurityGroup, SecurityGroupIngress
from troposphere.autoscaling import LaunchConfiguration, AutoScalingGroup

import config as cfn
from config import template, CIDR_PREFIX, CLOUDNAME, CLOUDENV, ASSUME_ROLE_POLICY
from config import USE_PRIVATE_SUBNETS, DEFAULT_ROUTE


def emit_configuration():
    vpc = cfn.vpcs[0]
    region = Ref("AWS::Region")

    zookeeper_instance_class = template.add_parameter(
        Parameter(
            'ZookeeperInstanceType', Type='String', Default='m3.medium',
            Description='Zookeeper instance type',
            AllowedValues=cfn.usable_instances(),
            ConstraintDescription='Instance size must be a valid instance type'
        )
    )

    create_zookeeper_bucket = template.add_parameter(
        Parameter(
            'CreateZookeeperBucket',
            Type='String',
            Description='Whether or not to create the Zookeeper bucket. This option is provided in case the bucket already exists.',
            Default='no',
            AllowedValues=['yes', 'no'],
            ConstraintDescription='Answer must be yes or no'
        )
    )

    conditions = {
        "ZookeeperBucketCondition": Equals(
            Ref(create_zookeeper_bucket), "yes"
        )
    }

    for c in conditions:
        template.add_condition(c, conditions[c])

    ingress_rules = [
        SecurityGroupRule(
            IpProtocol='tcp', CidrIp='{0}.0.0/16'.format(CIDR_PREFIX), FromPort=p, ToPort=p
        ) for p in [2181, 8080]
    ]

    ingress_rules.append(
        SecurityGroupRule(
            IpProtocol='tcp', CidrIp=DEFAULT_ROUTE, FromPort=22, ToPort=2222
        )
    )

    zookeeper_sg = template.add_resource(
        SecurityGroup(
            "ZookeeperSecurityGroup",
            GroupDescription="Security Group for ZooKeeper instances",
            VpcId=Ref(vpc),
            SecurityGroupIngress=ingress_rules,
            DependsOn=vpc.title
        )
    )

    # Now add in another ingress rule that allows zookeepers to talk to each other
    # in the same SG
    for port in [2888, 3888]:
        template.add_resource(
            SecurityGroupIngress(
                "ZookeeperSelfIngress{0}".format(port),
                IpProtocol='tcp',
                FromPort=port,
                ToPort=port,
                GroupId=Ref(zookeeper_sg),
                SourceSecurityGroupId=Ref(zookeeper_sg),
                DependsOn=zookeeper_sg.title
            )
        )

    # Create the zookeeper s3 bucket
    zookeeper_bucket_name = Join('.', ['zookeeper', CLOUDNAME, region, CLOUDENV, 'leafme'])
    zookeeper_bucket = template.add_resource(
        Bucket(
            "ZookeeperBucket",
            BucketName=zookeeper_bucket_name,
            DeletionPolicy='Retain',
            Condition="ZookeeperBucketCondition"
        )
    )

    zookeeper_role_name = '.'.join(['zookeeper', CLOUDNAME, CLOUDENV])
    zookeeper_iam_role = template.add_resource(
        Role(
            "ZookeeperIamRole",
            AssumeRolePolicyDocument=ASSUME_ROLE_POLICY,
            Path="/",
            Policies=[
                Policy(
                    PolicyName="ZookeeperDefaultPolicy",
                    PolicyDocument=json.loads(cfn.load_template("default_policy.json.j2",
                        {"env": CLOUDENV, "cloud": CLOUDNAME, "region": "us-east-1" }
                    ))
                ),
                Policy(
                    PolicyName="ZookeeperPolicy",
                    PolicyDocument=json.loads(cfn.load_template("zookeeper_policy.json.j2",
                        {"env": CLOUDENV, "cloud": CLOUDNAME, "region": "us-east-1"}
                    ))
                )
            ],
            DependsOn=vpc.title
        )
    )

    zookeeper_instance_profile = template.add_resource(
        InstanceProfile(
            "zookeeperInstanceProfile",
            Path="/",
            Roles=[Ref(zookeeper_iam_role)],
            DependsOn=zookeeper_iam_role.title
        )
    )

    zookeeper_user_data = cfn.load_template("default-init.bash.j2",
            {"env": CLOUDENV, "cloud": CLOUDNAME, "deploy": "zookeeper"}
    )

    # Launch Configuration for zookeepers
    zookeeper_launchcfg = template.add_resource(
        LaunchConfiguration(
            "ZookeeperLaunchConfiguration",
            ImageId=FindInMap('RegionMap', region, int(cfn.Amis.INSTANCE)),
            InstanceType=Ref(zookeeper_instance_class),
            IamInstanceProfile=Ref(zookeeper_instance_profile),
            AssociatePublicIpAddress=not USE_PRIVATE_SUBNETS,
            KeyName=Ref(cfn.keyname),
            SecurityGroups=[Ref(zookeeper_sg)],
            DependsOn=[zookeeper_instance_profile.title, zookeeper_sg.title],
            UserData=Base64(zookeeper_user_data)
        )
    )

    # Create the zookeeper autoscaling group
    zookeeper_asg_name = '.'.join(['zookeeper', CLOUDNAME, CLOUDENV])
    zookeeper_asg = template.add_resource(
        AutoScalingGroup(
            "ZookeeperASG",
            AvailabilityZones=cfn.get_asg_azs(),
            DesiredCapacity="3",
            LaunchConfigurationName=Ref(zookeeper_launchcfg),
            MinSize="3",
            MaxSize="3",
            NotificationConfiguration=autoscaling.NotificationConfiguration(
                TopicARN=Ref(alert_topic),
                NotificationTypes=[
                    EC2_INSTANCE_TERMINATE
                ]
            ),
            VPCZoneIdentifier=[Ref(sn) for sn in cfn.get_vpc_subnets(vpc, cfn.SubnetTypes.MASTER)]
        )
    )
