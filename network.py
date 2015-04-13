#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This module initializes the VPCs necessary for the rest of cloud formation

from itertools import chain

from troposphere import Parameter, Ref, Tags, Join, Output, Select, FindInMap
import troposphere.ec2 as ec2

import config as cfn
from config import CLOUDNAME

def emit_configuration():
    # Build the VPC here
    template = cfn.template

    # Parameters here
    nat_instance_class = template.add_parameter(
        Parameter(
            'NatInstanceType', Type='String', Default='t2.micro',
            Description='NAT instance type',
            AllowedValues=cfn.usable_instances(),
            ConstraintDescription='Instance size must be a valid instance type'
        )
    )

    keyname_param = template.add_parameter(
        Parameter(
            'KeyName', Type='AWS::EC2::KeyPair::KeyName',
            Description='Name of an existing EC2 KeyPair to enable SSH access into machines'
        )
    )

    cfn.keyname = keyname_param

    vpc = template.add_resource(
        ec2.VPC(
            'VPC',
            CidrBlock='{0}.0.0/16'.format(cfn.CIDR_PREFIX),
            EnableDnsSupport=True,
            EnableDnsHostnames=True,
            Tags=Tags(Name=Join('-', [cfn.VPC_NAME, Ref('AWS::Region')]))
        )
    )

    # Add the VPC to cloudformation
    cfn.vpcs.append(vpc)

    gateway = template.add_resource(
        ec2.InternetGateway(
            'InternetGateway',
            Tags=Tags(Name='InternetGateway-{0}'.format(CLOUDNAME)),
            DependsOn=vpc.title
        )
    )

    gateway_attachment = template.add_resource(
        ec2.VPCGatewayAttachment(
            'GatewayAttachment',
            VpcId=Ref(vpc),
            InternetGatewayId=Ref(gateway),
            DependsOn=gateway.title
        )
    )

    public_routing_table = template.add_resource(
        ec2.RouteTable(
            '{0}PublicRouteTable'.format(cfn.VPC_NAME),
            VpcId=Ref(vpc),
            DependsOn=vpc.title
        )
    )

    # Add in the public route through the gateway
    template.add_resource(
        ec2.Route(
            'PublicRoute',
            RouteTableId=Ref(public_routing_table),
            DestinationCidrBlock=cfn.DEFAULT_ROUTE,
            GatewayId=Ref(gateway),
            DependsOn=gateway_attachment.title
        )
    )

    # Define the Security Group for the NATs
    nat_ingress_rules = [
        ec2.SecurityGroupRule(
            IpProtocol='tcp', CidrIp=cfn.DEFAULT_ROUTE, FromPort=p, ToPort=p
        ) for p in [22, 80, 443, 11371]
    ]

    nat_egress_rules = [
        ec2.SecurityGroupRule(
            IpProtocol='-1', CidrIp=cfn.DEFAULT_ROUTE, FromPort=0, ToPort=65535,
        )
    ]


    nat_security_group = template.add_resource(
        ec2.SecurityGroup(
            'NATSecurityGroup',
            GroupDescription='Security Group for NAT instances',
            VpcId=Ref(vpc),
            SecurityGroupIngress=nat_ingress_rules,
            SecurityGroupEgress=nat_egress_rules,
            DependsOn=vpc.title
        )
    )

    platform_subnets = list()
    master_subnets = list()
    public_subnets = list()
    vpn_subnets = list()
    worker_subnets = list()
    database_subnets = list()
    subnet_identifier = 'private'

    for idx, zone in enumerate(cfn.get_availability_zones()):
        region = Ref('AWS::Region')
        full_region_descriptor = Join('', [region, zone])

        # create a public subnet in each availability zone
        public_subnet = template.add_resource(
            ec2.Subnet(
                '{0}PublicSubnet{1}'.format(cfn.VPC_NAME, zone),
                VpcId=Ref(vpc),
                CidrBlock='{0}.{1}.0/24'.format(cfn.CIDR_PREFIX, 80 + idx),
                AvailabilityZone=full_region_descriptor,
                DependsOn=vpc.title,
                Tags=Tags(Name=Join('-', [cfn.VPC_NAME, 'public-subnet', full_region_descriptor]))
            )
        )
        public_subnets.append(public_subnet)

        # Associate the public routing table with the subnet
        template.add_resource(
            ec2.SubnetRouteTableAssociation(
                '{0}PublicRouteTableAssociation'.format(public_subnet.title),
                SubnetId=Ref(public_subnet),
                RouteTableId=Ref(public_routing_table),
                DependsOn=public_subnet.title
            )
        )

        # Create the NAT instance in the public subnet
        nat_name = '{0}Nat{1}'.format(cfn.VPC_NAME, zone)
        nat_instance = template.add_resource(
            ec2.Instance(
                nat_name,
                DependsOn=vpc.title,
                InstanceType=Ref(nat_instance_class),
                KeyName=Ref(keyname_param),
                SourceDestCheck=False,
                ImageId=FindInMap('RegionMap', region, int(cfn.Amis.NAT)),
                NetworkInterfaces=[
                    ec2.NetworkInterfaceProperty(
                        Description='Network interface for {0}'.format(nat_name),
                        GroupSet=[Ref(nat_security_group)],
                        SubnetId=Ref(public_subnet),
                        AssociatePublicIpAddress=True,
                        DeviceIndex=0,
                        DeleteOnTermination=True
                    )
                ],
                Tags=Tags(Name=Join('-', [cfn.VPC_NAME, 'nat', full_region_descriptor]))
            )
        )

        # Associate the private routing table with the NAT
        private_routing_table = template.add_resource(
            ec2.RouteTable(
                '{0}PrivateRouteTable{1}'.format(cfn.VPC_NAME, zone),
                VpcId=Ref(vpc),
                DependsOn=nat_instance.title,
                Tags=Tags(Name=Join('-', [cfn.VPC_NAME, 'private-route-table', full_region_descriptor]))
            )
        )

        template.add_resource(
            ec2.Route(
                'PrivateRoute{0}'.format(zone.upper()),
                RouteTableId=Ref(private_routing_table),
                DestinationCidrBlock=cfn.DEFAULT_ROUTE,
                InstanceId=Ref(nat_instance),
                DependsOn=private_routing_table.title
            )
        )


        worker_subnet = ec2.Subnet(
            '{0}{1}WorkerSubnet{2}'.format(cfn.VPC_NAME, subnet_identifier, zone.upper()),
            VpcId=Ref(vpc),
            CidrBlock='{0}.{1}.0/22'.format(cfn.CIDR_PREFIX, 100 + (idx * 4)),
            AvailabilityZone=full_region_descriptor,
            DependsOn=vpc.title,
            Tags=Tags(Name=Join('-', [cfn.VPC_NAME, '{0}-worker-subnet'.format(subnet_identifier), full_region_descriptor]))
        )
        worker_subnets.append(worker_subnet)

        platform_subnet = ec2.Subnet(
            '{0}{1}PlatformSubnet{2}'.format(cfn.VPC_NAME, subnet_identifier, zone.upper()),
            VpcId=Ref(vpc),
            CidrBlock='{0}.{1}.0/24'.format(cfn.CIDR_PREFIX, 10 + idx),
            AvailabilityZone=full_region_descriptor,
            DependsOn=vpc.title,
            Tags=Tags(Name=Join('-', [cfn.VPC_NAME, '{0}-platform-subnet'.format(subnet_identifier), full_region_descriptor]))
        )
        platform_subnets.append(platform_subnet)

        master_subnet = ec2.Subnet('{0}{1}MasterSubnet{2}'.format(cfn.VPC_NAME, subnet_identifier, zone.upper()),
            VpcId=Ref(vpc),
            CidrBlock='{0}.{1}.0/24'.format(cfn.CIDR_PREFIX, 90 + idx),
            AvailabilityZone=full_region_descriptor,
            DependsOn=vpc.title,
            Tags=Tags(Name=Join('-', [cfn.VPC_NAME, '{0}-master-subnet'.format(subnet_identifier), full_region_descriptor]))
        )
        master_subnets.append(master_subnet)

        vpn_subnet = ec2.Subnet(
            '{0}VpnSubnet{1}'.format(cfn.VPC_NAME, zone),
            VpcId=Ref(vpc),
            CidrBlock='{0}.{1}.0/24'.format(cfn.CIDR_PREFIX, 60 + idx),
            AvailabilityZone=full_region_descriptor,
            DependsOn=vpc.title,
            Tags=Tags(Name=Join('.', [full_region_descriptor, cfn.CLOUDNAME, cfn.CLOUDENV, "vpn-client"]))
        )
        vpn_subnets.append(vpn_subnet)

        database_subnet = ec2.Subnet(
            '{0}DatabaseSubnet{1}'.format(cfn.VPC_NAME, zone),
            VpcId=Ref(vpc),
            CidrBlock='{0}.{1}.0/24'.format(cfn.CIDR_PREFIX, 20 + idx),
            AvailabilityZone=full_region_descriptor,
            DependsOn=vpc.title,
            Tags=Tags(Name=Join('-', [cfn.VPC_NAME, subnet_identifier, 'database-subnet', full_region_descriptor]))
        )
        database_subnets.append(database_subnet)

    # Associate a routing table with each of the master/platform/worker subnets
    if cfn.USE_PRIVATE_SUBNETS:
        routing_table = private_routing_table
    else:
        routing_table = public_routing_table

    for sn in chain(worker_subnets, master_subnets, platform_subnets, database_subnets):
        template.add_resource(sn)
        template.add_resource(
            ec2.SubnetRouteTableAssociation(
                '{0}{1}RouteTableAssociation'.format(sn.title, subnet_identifier),
                SubnetId=Ref(sn),
                RouteTableId=Ref(routing_table),
                DependsOn=sn.title
            )
        )

    # associate the public routing table with the VPN subnets
    for sn in vpn_subnets:
        template.add_resource(sn),
        template.add_resource(
            ec2.SubnetRouteTableAssociation(
                '{0}RouteTableAssociation'.format(sn.title),
                SubnetId=Ref(sn),
                RouteTableId=Ref(public_routing_table),
                DependsOn=sn.title
            )
        )

    # affect the global state
    cfn.add_vpc_subnets(vpc, cfn.SubnetTypes.PLATFORM, platform_subnets)
    cfn.add_vpc_subnets(vpc, cfn.SubnetTypes.PUBLIC, public_subnets)
    cfn.add_vpc_subnets(vpc, cfn.SubnetTypes.MASTER, master_subnets)
    cfn.add_vpc_subnets(vpc, cfn.SubnetTypes.WORKER, worker_subnets)
    cfn.add_vpc_subnets(vpc, cfn.SubnetTypes.VPN, vpn_subnets)
    cfn.add_vpc_subnets(vpc, cfn.SubnetTypes.DATABASE, database_subnets)
