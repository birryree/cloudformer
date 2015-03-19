#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Create Jenkins Master

import json

from troposphere import Ref, Parameter, FindInMap, Base64, Equals, Join
from troposphere.s3 import Bucket
import troposphere.autoscaling as autoscaling

from troposphere.autoscaling import EC2_INSTANCE_TERMINATE, EC2_INSTANCE_LAUNCH, EC2_INSTANCE_LAUNCH_ERROR, EC2_INSTANCE_TERMINATE_ERROR
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

    jenkins_instance_class = template.add_parameter(
        Parameter(
            'jenkinsInstanceType', Type='String', Default='c3.xlarge',
            Description='jenkins instance type',
            AllowedValues=cfn.usable_instances(),
            ConstraintDescription='Instance size must be a valid instance type'
        )
    )

    jenkins_ingress_rules = [
        SecurityGroupRule(
            IpProtocol=p[0], CidrIp=DEFAULT_ROUTE, FromPort=p[1], ToPort=p[1]
        ) for p in [('tcp', 22), ('tcp', 80), ('tcp', 443)]
    ]

    jenkins_sg = template.add_resource(
        SecurityGroup(
            "jenkinsSecurityGroup",
            GroupDescription="Security Group for jenkins ingress.",
            VpcId=Ref(vpc),
            SecurityGroupIngress=jenkins_ingress_rules,
            DependsOn=vpc.title
        )
    )

    # IAM role for jenkins
    jenkins_policy = json.loads(cfn.load_template("jenkins_policy.json.j2",
        {"env": CLOUDENV, "cloud": CLOUDNAME, "region": "us-east-1"}
    ))

    default_policy = json.loads(cfn.load_template("default_policy.json.j2",
        {"env": CLOUDENV, "cloud": CLOUDNAME, "region": "us-east-1"}
    ))

    jenkins_role_name = '.'.join(['jenkins', CLOUDNAME, CLOUDENV])
    jenkins_iam_role = template.add_resource(
        Role(
            "jenkinsIamRole",
            AssumeRolePolicyDocument=ASSUME_ROLE_POLICY,
            Path="/",
            Policies=[
                Policy(
                    PolicyName="jenkinsDefaultPolicy",
                    PolicyDocument=default_policy
                ),
                Policy(
                    PolicyName="jenkinsPolicy",
                    PolicyDocument=jenkins_policy
                )
            ],
            DependsOn=vpc.title
        )
    )

    jenkins_instance_profile = template.add_resource(
        InstanceProfile(
            "jenkinsInstanceProfile",
            Path="/",
            Roles=[Ref(jenkins_iam_role)],
            DependsOn=jenkins_iam_role.title
        )
    )

    jenkins_user_data = cfn.load_template("default-init.bash.j2",
        {"env": CLOUDENV, "cloud": CLOUDNAME, "deploy": "jenkins"}
    )

    # Launch Configuration for jenkinss
    jenkins_launchcfg = template.add_resource(
        LaunchConfiguration(
            "jenkinsLaunchConfiguration",
            ImageId=FindInMap('RegionMap', region, int(cfn.Amis.INSTANCE)),
            InstanceType=Ref(jenkins_instance_class),
            IamInstanceProfile=Ref(jenkins_instance_profile),
            KeyName=Ref(cfn.keyname),
            SecurityGroups=[Ref(jenkins_sg)],
            DependsOn=[jenkins_instance_profile.title, jenkins_sg.title],
            AssociatePublicIpAddress=True,
            UserData=Base64(jenkins_user_data)
        )
    )

    # Create the babysitter autoscaling group
    jenkins_asg_name = '.'.join(['jenkins', CLOUDNAME, CLOUDENV])
    jenkins_asg = template.add_resource(
        AutoScalingGroup(
            "jenkinsASG",
            AvailabilityZones=cfn.get_asg_azs(),
            DesiredCapacity="1",
            LaunchConfigurationName=Ref(jenkins_launchcfg),
            MinSize="1",
            MaxSize="1",
            NotificationConfiguration=NotificationConfiguration(
                TopicARN=Ref(cfn.alert_topic),
                NotificationTypes=[
                    EC2_INSTANCE_TERMINATE, EC2_INSTANCE_LAUNCH, EC2_INSTANCE_LAUNCH_ERROR, EC2_INSTANCE_TERMINATE_ERROR
                ]
            ),
            VPCZoneIdentifier=[Ref(sn) for sn in cfn.get_vpc_subnets(vpc, cfn.SubnetTypes.jenkins)],
            DependsOn=[sn.title for sn in cfn.get_vpc_subnets(vpc, cfn.SubnetTypes.jenkins)]
        )
    )
    # END jenkins