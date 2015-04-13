#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This module creates the postgres database

from troposphere import Parameter, Ref, GetAtt, Tags, Join, Output
from troposphere.rds import DBInstance, DBSubnetGroup
from troposphere.ec2 import SecurityGroup, SecurityGroupRule

import config as cfn
from config import template, CLOUDENV, CLOUDNAME, DEFAULT_ROUTE

def emit_configuration():
    vpc = cfn.vpcs[0]
    region = Ref("AWS::Region")

    dbname = template.add_parameter(
        Parameter(
            "RDSDatabaseInstanceName",
            Default="reporting{0}".format(CLOUDENV),
            Description="Postgres Instance Name",
            Type="String",
            MinLength="1",
            MaxLength="63",
            AllowedPattern="[a-zA-Z][a-zA-Z0-9]*",
            ConstraintDescription="Must begin with a letter and contain only alphanumeric characters"
        )
    )

    dbuser = template.add_parameter(
        Parameter(
            "RDSDatabaseUser",
            Default="sa",
            Description="The database admin account username",
            Type="String",
            MinLength="1",
            MaxLength="63",
            AllowedPattern="[a-zA-Z][a-zA-Z0-9]*",
            ConstraintDescription="Must being with a letter and be alphanumeric"
        )
    )

    dbpassword = template.add_parameter(
        Parameter(
            "RDSDatabasePassword",
            NoEcho=True,
            Description="The database admin account password",
            Type="String",
            MinLength="1",
            MaxLength="41",
            AllowedPattern="[a-zA-Z0-9]*",
            ConstraintDescription="Must contain only alphanumeric characters.",
            Default="LeafLeaf123"
        )
    )

    dbclass = template.add_parameter(
        Parameter(
            "RDSInstanceClass",
            Default="db.t2.medium",
            Description="Database instance size",
            Type="String",
            AllowedValues=[
                "db.t2.small", "db.t2.medium", "db.m3.medium", "db.m3.large",
                "db.m3.xlarge", "db.m3.2xlarge", "db.r3.large", "db.r3.xlarge",
                "db.r3.2xlarge", "db.r3.4xlarge", "db.r3.8xlarge"
            ]
        )
    )

    allocated_storage = template.add_parameter(
        Parameter(
            "RDSAllocatedStorage",
            Default="100",
            Description="The size of the Postgres Database (GB)",
            Type="Number",
            MinValue="5",
            MaxValue="512",
            ConstraintDescription="Must be between 5 and 512 GB"
        )
    )

    db_subnet_group = template.add_resource(
        DBSubnetGroup(
            "RDSSubnetGroup",
            DBSubnetGroupDescription="Subnets available for RDS in {0}".format(CLOUDNAME),
            SubnetIds=[Ref(sn) for sn in cfn.get_vpc_subnets(vpc, cfn.SubnetTypes.DATABASE)],
            DependsOn=[sn.title for sn in cfn.get_vpc_subnets(vpc, cfn.SubnetTypes.DATABASE)]
        )
    )

    ingress_rules = [
        SecurityGroupRule(
            IpProtocol=p[0], CidrIp=DEFAULT_ROUTE, FromPort=p[1], ToPort=p[1]
        ) for p in [('tcp', 5432)]]

    security_group = template.add_resource(
        SecurityGroup(
            "RDSDatabaseSecurityGroup",
            GroupDescription="Security group for Postgres Instances",
            VpcId=Ref(vpc),
            SecurityGroupIngress=ingress_rules,
            DependsOn=vpc.title
        )
    )

    database = template.add_resource(
        DBInstance(
            "RDSPostgresInstance",
            DBInstanceIdentifier=Ref(dbname),
            AllocatedStorage=Ref(allocated_storage),
            DBInstanceClass=Ref(dbclass),
            Engine="postgres",
            EngineVersion="9.3.6",
            MasterUsername=Ref(dbuser),
            MasterUserPassword=Ref(dbpassword),
            DBSubnetGroupName=Ref(db_subnet_group),
            VPCSecurityGroups=[Ref(security_group)],
            DependsOn=[sn.title for sn in cfn.get_vpc_subnets(vpc, cfn.SubnetTypes.DATABASE)]
        )
    )

    template.add_output(
        Output(
            "ConnectionString",
            Description="JDBC connection string for Postgres",
            Value=Join("", [
                GetAtt("RDSPostgresInstance", "Endpoint.Address"),
                GetAtt("RDSPostgresInstance", "Endpoint.Port")
            ])
        )
    )
