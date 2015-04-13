#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This module creates a Redshift cluster

from troposphere import Parameter, Ref, GetAtt, If, Join, Output, Equals
from troposphere.ec2 import SecurityGroup, SecurityGroupRule
from troposphere.redshift import Cluster, ClusterParameterGroup
from troposphere.redshift import AmazonRedshiftParameter, ClusterSubnetGroup

import config as cfn
from config import template, DEFAULT_ROUTE, CLOUDENV


def emit_configuration():
    vpc = cfn.vpcs[0]

    dbname = template.add_parameter(
        Parameter(
            'RedshiftDatabaseName',
            Description='The name of database to create within redshift',
            Type="String",
            Default="farragut",
            AllowedPattern="[a-z0-9]*",
            ConstraintDescription="Must be alphanumeric"
        )
    )

    clustertype = template.add_parameter(
        Parameter(
            'RedshiftClusterType',
            Description="The type of cluster to build",
            Type="String",
            Default="single-node",
            AllowedValues=["single-node", "multi-node"]
        )
    )

    numberofnodes = template.add_parameter(
        Parameter(
            "RedshiftNumberOfNodes",
            Description="The number of compute nodes in the redshift cluster. "
            "When cluster type is specified as: 1) single-node, the NumberOfNodes "
            "parameter should be specified as 1, 2) multi-node, the NumberOfNodes "
            "parameter should be greater than 1",
            Type="Number",
            Default="1",
        )
    )

    nodetype = template.add_parameter(
        Parameter(
            "RedshiftNodeType",
            Description="The node type to be provisioned for the redshift cluster",
            Type="String",
            Default="dw2.large",
        )
    )

    masterusername = template.add_parameter(Parameter(
        "RedshiftMasterUsername",
        Description="The user name associated with the master user account for "
        "the redshift cluster that is being created",
        Type="String",
        Default="sa",
        AllowedPattern="([a-z])([a-z]|[0-9])*"
    ))

    masteruserpassword = template.add_parameter(Parameter(
        "RedshiftMasterUserPassword",
        Description="The password associated with the master user account for the "
        "redshift cluster that is being created.",
        Type="String",
        NoEcho=True,
        Default="LeafLeaf123"
    ))

    ingress_rules = [
        SecurityGroupRule(
            IpProtocol=p[0], CidrIp=DEFAULT_ROUTE, FromPort=p[1], ToPort=p[1]
        ) for p in [('tcp', 5439)]
    ]

    rs_security_group = template.add_resource(
        SecurityGroup(
            "RedshiftSecurityGroup",
            GroupDescription="SecurityGroup for the {0} Redshift cluster".format(CLOUDENV),
            VpcId=Ref(vpc),
            SecurityGroupIngress=ingress_rules,
            DependsOn=vpc.title
        )
    )

    cluster_subnet_group = template.add_resource(
        ClusterSubnetGroup(
            "RedshiftClusterSubnetGroup",
            Description="Redshift {0} cluster subnet group".format(CLOUDENV),
            SubnetIds=[Ref(sn) for sn in cfn.get_vpc_subnets(vpc, cfn.SubnetTypes.DATABASE)],
            DependsOn=[sn.title for sn in cfn.get_vpc_subnets(vpc, cfn.SubnetTypes.DATABASE)]
        )
    )

    conditions = {
        "IsMultiNodeCluster": Equals(
            Ref("RedshiftClusterType"),
            "multi-mode"
        ),
    }

    for k in conditions:
        template.add_condition(k, conditions[k])

    redshiftcluster = template.add_resource(Cluster(
        "RedshiftCluster",
        ClusterType=Ref("RedshiftClusterType"),
        NumberOfNodes=If("IsMultiNodeCluster",
                         Ref("RedshiftNumberOfNodes"), Ref("AWS::NoValue")),
        NodeType=Ref("RedshiftNodeType"),
        DBName=Ref("RedshiftDatabaseName"),
        MasterUsername=Ref("RedshiftMasterUsername"),
        MasterUserPassword=Ref("RedshiftMasterUserPassword"),
        ClusterParameterGroupName=Ref("RedshiftClusterParameterGroup"),
        DeletionPolicy="Snapshot",
        ClusterSubnetGroupName=Ref(cluster_subnet_group),
        VpcSecurityGroupIds=[Ref("RedshiftSecurityGroup")],
        DependsOn=[cluster_subnet_group.title, rs_security_group.title]
    ))

    log_activity_parameter = AmazonRedshiftParameter(
        "AmazonRedshiftParameterEnableUserLogging",
        ParameterName="enable_user_activity_logging",
        ParameterValue="true",
    )

    redshiftclusterparametergroup = template.add_resource(ClusterParameterGroup(
        "RedshiftClusterParameterGroup",
        Description="Cluster parameter group",
        ParameterGroupFamily="redshift-1.0",
        Parameters=[log_activity_parameter],
    ))

    template.add_output(Output(
        "RedshiftClusterEndpoint",
        Value=Join(":", [GetAtt(redshiftcluster, "Endpoint.Address"),
                   GetAtt(redshiftcluster, "Endpoint.Port")]),
    ))
