#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Create VPN stuff

import json

from troposphere import Ref, Parameter, FindInMap, Base64, Equals, Join
from troposphere.s3 import Bucket
import troposphere.autoscaling as autoscaling
from troposphere.autoscaling import EC2_INSTANCE_TERMINATE
from troposphere.iam import Role, Group, PolicyType, Policy, InstanceProfile
from troposphere.ec2 import SecurityGroupRule, SecurityGroup, SecurityGroupIngress
from troposphere.autoscaling import LaunchConfiguration, AutoScalingGroup, NotificationConfiguration

import config as cfn
from config import template, CIDR_PREFIX, CLOUDNAME, CLOUDENV, ASSUME_ROLE_POLICY
from config import USE_PRIVATE_SUBNETS, DEFAULT_ROUTE

EMIT = True


def emit_configuration():
    vpc = cfn.vpcs[0]
    region = Ref("AWS::Region")

    vpn_instance_class = template.add_parameter(
        Parameter(
            'VPNInstanceType', Type='String', Default='m3.medium',
            Description='VPN instance type',
            AllowedValues=cfn.usable_instances(),
            ConstraintDescription='Instance size must be a valid instance type'
        )
    )

    vpn_ingress_rules = [
        SecurityGroupRule(
            IpProtocol=p[0], CidrIp=DEFAULT_ROUTE, FromPort=p[1], ToPort=p[1]
        ) for p in [('tcp', 22), ('udp', 1194)]
    ]

    vpn_sg = template.add_resource(
        SecurityGroup(
            "VPNSecurityGroup",
            GroupDescription="Security Group for VPN ingress.",
            VpcId=Ref(vpc),
            SecurityGroupIngress=vpn_ingress_rules,
            DependsOn=vpc.title
        )
    )

    # IAM role for vpn
    vpn_policy = json.loads(cfn.load_template("vpn_policy.json.j2",
        {"env": CLOUDENV, "cloud": CLOUDNAME, "region": "us-east-1"}
    ))

    default_policy = json.loads(cfn.load_template("default_policy.json.j2",
        {"env": CLOUDENV, "cloud": CLOUDNAME, "region": "us-east-1"}
    ))

    vpn_role_name = '.'.join(['vpn', CLOUDNAME, CLOUDENV])
    vpn_iam_role = template.add_resource(
        Role(
            "VPNIamRole",
            AssumeRolePolicyDocument=ASSUME_ROLE_POLICY,
            Path="/",
            Policies=[
                Policy(
                    PolicyName="VPNDefaultPolicy",
                    PolicyDocument=default_policy
                ),
                Policy(
                    PolicyName="VPNPolicy",
                    PolicyDocument=vpn_policy
                )
            ],
            DependsOn=vpc.title
        )
    )

    vpn_instance_profile = template.add_resource(
        InstanceProfile(
            "vpnInstanceProfile",
            Path="/",
            Roles=[Ref(vpn_iam_role)],
            DependsOn=vpn_iam_role.title
        )
    )

    vpn_user_data = cfn.load_template("default-init.bash.j2",
        {"env": CLOUDENV, "cloud": CLOUDNAME, "deploy": "vpn"}
    )

    # Launch Configuration for vpns
    vpn_launchcfg = template.add_resource(
        LaunchConfiguration(
            "VPNLaunchConfiguration",
            ImageId=FindInMap('RegionMap', region, int(cfn.Amis.INSTANCE)),
            InstanceType=Ref(vpn_instance_class),
            IamInstanceProfile=Ref(vpn_instance_profile),
            KeyName=Ref(cfn.keyname),
            SecurityGroups=[Ref(vpn_sg)],
            DependsOn=[vpn_instance_profile.title, vpn_sg.title],
            AssociatePublicIpAddress=True,
            UserData=Base64(vpn_user_data)
        )
    )

    # Create the babysitter autoscaling group
    vpn_asg_name = '.'.join(['vpn', CLOUDNAME, CLOUDENV])
    vpn_asg = template.add_resource(
        AutoScalingGroup(
            "VPNASG",
            AvailabilityZones=cfn.get_asg_azs(),
            DesiredCapacity="1",
            LaunchConfigurationName=Ref(vpn_launchcfg),
            MinSize="1",
            MaxSize="1",
            NotificationConfiguration=NotificationConfiguration(
                TopicARN=Ref(cfn.alert_topic),
                NotificationTypes=[
                    EC2_INSTANCE_TERMINATE
                ]
            ),
            VPCZoneIdentifier=[Ref(sn) for sn in cfn.get_vpc_subnets(vpc, cfn.SubnetTypes.VPN)],
            DependsOn=[sn.title for sn in cfn.get_vpc_subnets(vpc, cfn.SubnetTypes.VPN)]
        )
    )
    # END VPN

