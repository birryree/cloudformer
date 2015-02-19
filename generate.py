import yaml
import argparse
import os
import pkgutil

import network
import config as cfn

from components import babysitter, zookeeper, vpn

def _create_parser():
    parser = argparse.ArgumentParser(prog='generate.py')
    parser.add_argument('-c', '--config', type=str, required=True, help='The configuration YAML file to use to generate the Cloudformation template')
    parser.add_argument('-o', '--outfile', type=str, help='The file to write the Cloudformation template to')
    return parser

def generate_cloudformation_template(outfile):
    network.emit_configuration()
    babysitter.emit_configuration()
    zookeeper.emit_configuration()
    vpn.emit_configuration()
    with open(outfile, 'w') as ofile:
        print >> ofile, cfn.template.to_json()

def create_cfn_template(conf_file, outfile):
    # TODO this is dead, repurpose it
    with open (conf_file, 'r') as yfile:
        config = yaml.load(yfile)
        infra = config['infra'][0]

    CIDR_PREFIX= infra['network']['cidr_16_prefix']
    CLOUDNAME = infra['cloudname']
    CLOUDENV = infra['env']
    USE_PRIVATE_SUBNETS = infra['network']['private_subnets']
    REGION = infra['region']

if __name__ == '__main__':
    arg_parser = _create_parser()
    args = arg_parser.parse_args()

    print('Creating cloudformation template using config file: {0} '.format(args.config))
    #create_cfn_template(args.config, args.outfile)
    generate_cloudformation_template(args.outfile)
