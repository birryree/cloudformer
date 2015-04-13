#/usr/bin/env python
# -*- coding: utf-8 -*-

# Create Mesos cluster

import json

from troposphere import Ref, Parameter, FindInMap, Base64, Equals, Join
from troposphere.s3 import Bucket
from troposphere.iam import Role, Group, PolicyType, Policy, InstanceProfile
from troposphere.ec2 import SecurityGroupRule, SecurityGroup, SecurityGroupIngress
from troposphere.autoscaling import LaunchConfiguration, AutoScalingGroup, NotificationConfiguration
from troposphere.autoscaling import EC2_INSTANCE_TERMINATE, EC2_INSTANCE_LAUNCH, EC2_INSTANCE_LAUNCH_ERROR, EC2_INSTANCE_TERMINATE_ERROR

import config as cfn
from config import template, CIDR_PREFIX, CLOUDNAME, CLOUDENV, ASSUME_ROLE_POLICY
from config import DEFAULT_ROUTE

def emit_configuration():
    vpc = cfn.vpcs[0]
    region = Ref("AWS::Region")

    mesos_instance_class = template.add_parameter(
        Parameter(
            'MesosInstanceType', Type='String', Default='m3.large',
            Description='Mesos instance type (for workers and masters)',
            AllowedValues=cfn.usable_instances(),
            ConstraintDescription='Instance size must be a valid instance type'
        )
    )

    ingress_rules = [
        SecurityGroupRule(
            IpProtocol=p[0], CidrIp=DEFAULT_ROUTE, FromPort=p[1], ToPort=p[1]
        ) for p in [('tcp', 22), ('tcp', 5050), ('tcp', 8080)]
    ]

    mesos_security_group = template.add_resource(
        SecurityGroup(
            "Mesos",
            GroupDescription="Security Group for Mesos instances",
            VpcId=Ref(vpc),
            SecurityGroupIngress=ingress_rules,
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

    default_policy = json.loads(cfn.load_template("default_policy.json.j2",
        {"env": CLOUDENV, "cloud": CLOUDNAME, "region": "us-east-1"}
    ))

    mesos_policy = json.loads(cfn.load_template("mesos_policy.json.j2",
        {"env": CLOUDENV, "cloud": CLOUDNAME, "region": "us-east-1"}
    ))

    # IAM role here
    iam_role = template.add_resource(
        Role(
            "MesosIamRole",
            AssumeRolePolicyDocument=ASSUME_ROLE_POLICY,
            Path="/",
            Policies=[
                Policy(
                    PolicyName='MesosDefaultPolicy',
                    PolicyDocument=default_policy
                ),
                Policy(
                    PolicyName='MesosIamPolicy',
                    PolicyDocument=mesos_policy
                )
            ],
            DependsOn=vpc.title
        )
    )

    # Instance profile here
    instance_profile = template.add_resource(
        InstanceProfile(
            "mesosInstanceProfile",
            Path="/",
            Roles=[Ref(iam_role)],
            DependsOn=iam_role.title
        )
    )

    # UserData here
    master_user_data = cfn.load_template("default-init.bash.j2",
        {"env": CLOUDENV, "cloud": CLOUDNAME, "deploy": "mesos_master"}
    )

    # LaunchConfiguration for master mesos
    master_launch_configuration = template.add_resource(
        LaunchConfiguration(
            "MesosMasterLaunchConfiguration",
            ImageId=FindInMap('RegionMap', region, int(cfn.Amis.INSTANCE)),
            InstanceType=Ref(mesos_instance_class),
            IamInstanceProfile=Ref(instance_profile),
            KeyName=Ref(cfn.keyname),
            SecurityGroups=[Ref(mesos_security_group)],
            DependsOn=[instance_profile.title, mesos_security_group.title],
            AssociatePublicIpAddress=False,
            UserData=Base64(master_user_data)
        )
    )

    # Autoscaling Group for master Mesos
    master_asg_name = '.'.join(['mesos-master', CLOUDNAME, CLOUDENV])
    master_asg = template.add_resource(
        AutoScalingGroup(
            "MesosMasterASG",
            AvailabilityZones=cfn.get_asg_azs(),
            DesiredCapacity="3",
            LaunchConfigurationName=Ref(master_launch_configuration),
            MinSize="3",
            MaxSize="3",
            NotificationConfiguration=NotificationConfiguration(
                TopicARN=Ref(cfn.alert_topic),
                NotificationTypes=[
                    EC2_INSTANCE_TERMINATE, EC2_INSTANCE_LAUNCH, EC2_INSTANCE_LAUNCH_ERROR, EC2_INSTANCE_TERMINATE_ERROR
                ]
            ),
            VPCZoneIdentifier=[Ref(sn) for sn in cfn.get_vpc_subnets(vpc, cfn.SubnetTypes.MASTER)],
            DependsOn=[sn.title for sn in cfn.get_vpc_subnets(vpc, cfn.SubnetTypes.MASTER)]
        )
    )

    # Worker Mesos
    worker_user_data = cfn.load_template("default-init.bash.j2",
        {"env": CLOUDENV, "cloud": CLOUDNAME, "deploy": "mesos_slave"}
    )

    worker_launch_configuration = template.add_resource(
        LaunchConfiguration(
            "MesosWorkerLaunchConfiguration",
            ImageId=FindInMap('RegionMap', region, int(cfn.Amis.INSTANCE)),
            InstanceType=Ref(mesos_instance_class),
            IamInstanceProfile=Ref(instance_profile),
            KeyName=Ref(cfn.keyname),
            SecurityGroups=[Ref(mesos_security_group)],
            DependsOn=[instance_profile.title, mesos_security_group.title],
            AssociatePublicIpAddress=False,
            UserData=Base64(worker_user_data)
        )
    )

    worker_asg_name = '.'.join(['mesos-worker', CLOUDNAME, CLOUDENV]),
    worker_asg = template.add_resource(
        AutoScalingGroup(
            "MesosWorkerASG",
            AvailabilityZones=cfn.get_asg_azs(),
            DesiredCapacity="3",
            LaunchConfigurationName=Ref(worker_launch_configuration),
            MinSize="3",
            MaxSize="12",
            NotificationConfiguration=NotificationConfiguration(
                TopicARN=Ref(cfn.alert_topic),
                NotificationTypes=[
                    EC2_INSTANCE_TERMINATE, EC2_INSTANCE_LAUNCH, EC2_INSTANCE_LAUNCH_ERROR, EC2_INSTANCE_TERMINATE_ERROR
                ]
            ),
            VPCZoneIdentifier=[Ref(sn) for sn in cfn.get_vpc_subnets(vpc, cfn.SubnetTypes.WORKER)],
            DependsOn=[sn.title for sn in cfn.get_vpc_subnets(vpc, cfn.SubnetTypes.WORKER)]
        )
    )

