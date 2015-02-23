#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Create Chef stuff

import json

from troposphere import Ref, Parameter, FindInMap, Base64, Equals, Join
from troposphere.s3 import Bucket
from troposphere.iam import Role, Group, PolicyType, Policy, InstanceProfile
from troposphere.ec2 import SecurityGroupRule, SecurityGroup, SecurityGroupIngress
from troposphere.ec2 import Instance, NetworkInterfaceProperty, BlockDeviceMapping
from troposphere.ec2 import EBSBlockDevice
from troposphere.autoscaling import LaunchConfiguration, AutoScalingGroup

import config as cfn
from config import template, CIDR_PREFIX, CLOUDNAME, CLOUDENV, ASSUME_ROLE_POLICY
from config import USE_PRIVATE_SUBNETS, DEFAULT_ROUTE

EMIT = False

def emit_configuration():
    vpc = cfn.vpcs[0]
    region = Ref("AWS::Region")

    chefserver_instance_class = template.add_parameter(
        Parameter(
            'ChefServerInstanceType', Type='String', Default='t2.medium',
            Description='Chef Server instance type',
            AllowedValues=cfn.usable_instances(),
            ConstraintDescription='Instance size must be a valid instance type'
        )
    )

    # Create IAM role for the chefserver instance
    # load the policies
    default_policy = json.loads(cfn.load_template("default_policy.json.j2",
        {"env": CLOUDENV, "cloud": CLOUDNAME, "region": "us-east-1"}
    ))

    chefserver_role_name = '.'.join(['chefserver', CLOUDNAME, CLOUDENV])
    chefserver_iam_role = template.add_resource(
        Role(
            "ChefServerIamRole",
            AssumeRolePolicyDocument=ASSUME_ROLE_POLICY,
            Path="/",
            Policies=[
                Policy(
                    PolicyName="ChefServerPolicy",
                    PolicyDocument=json.loads(
                        cfn.load_template("chefserver_policy.json.j2",
                            {"env": CLOUDENV, "cloud": CLOUDNAME, "region": "us-east-1"}
                        )
                    )
                ),
                Policy(
                    PolicyName="ChefserverDefaultPolicy",
                    PolicyDocument=default_policy
                )
            ],
            DependsOn=vpc.title
        )
    )

    chefserver_instance_profile = template.add_resource(
        InstanceProfile(
            "chefserverInstanceProfile",
            Path="/",
            Roles=[Ref(chefserver_iam_role)],
            DependsOn=chefserver_iam_role.title
        )
    )


    chefserver_user_data = cfn.load_template("chefserver-init.bash.j2",
        {"env": CLOUDENV, "cloud": CLOUDNAME, "deploy": "chefserver"}
    )

    chefserver_ingress_rules = [
        SecurityGroupRule(
            IpProtocol=p[0], CidrIp='{0}.0.0/16'.format(CIDR_PREFIX), FromPort=p[1], ToPort=p[1]
        ) for p in [('tcp', 80), ('tcp', 443)]
    ]

    chefserver_sg = template.add_resource(
        SecurityGroup(
            "ChefServerSecurityGroup",
            GroupDescription="Security Group for the Chef server",
            VpcId=Ref(vpc),
            SecurityGroupIngress=chefserver_ingress_rules,
            DependsOn=vpc.title
        )
    )

    chefserver_name = cfn.sanitize_id("ChefServer", CLOUDNAME, CLOUDENV)
    chefserver_instance = template.add_resource(Instance(
        chefserver_name,
        DependsOn=vpc.title,
        InstanceType=Ref(chefserver_instance_class),
        KeyName=Ref(cfn.keyname),
        SourceDestCheck=False,
        ImageId=FindInMap('RegionMap', region, int(cfn.Amis.EBS)),
        NetworkInterfaces=[
            NetworkInterfaceProperty(
                Description='Network interface for {0}'.format(chefserver_name),
                GroupSet=[Ref(chefserver_sg)],
                SubnetId=Ref(cfn.get_vpc_subnets(vpc, cfn.SubnetTypes.PLATFORM)[0]),
                AssociatePublicIpAddress=True,
                DeviceIndex=0,
                DeleteOnTermination=True
            )
        ],
        BlockDeviceMappings=[
            BlockDeviceMapping(
                DeviceName="/dev/sda1",
                Ebs=EBSBlockDevice(
                    VolumeSize=50,
                    DeleteOnTermination=False
                )
            )
        ]
    ))
