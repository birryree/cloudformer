import argparse
import os
import pkgutil
import sys

import network
import config

#from components import babysitter, zookeeper, vpn

def _create_parser():
    parser = argparse.ArgumentParser(prog='generate.py')
    parser.add_argument('-c', '--config', type=str, help='The configuration YAML file to use to generate the Cloudformation template')
    parser.add_argument('-o', '--outfile', type=str, help='The file to write the Cloudformation template to')
    return parser

def _emit_component_configurations(package):
    # Get all submodules in components
    for loader, module_name, ispkg in pkgutil.iter_modules([package]):
        if module_name not in sys.modules:
            mod = __import__("{0}.{1}".format(package, module_name))
            # Determine if EMIT is set to a non-True value (if module has one).
            cls = getattr(mod, module_name)

            # generate configuration for module if it doesn't have the EMIT
            # property set or if it's set to something 'true'
            if (hasattr(cls, 'EMIT') and cls.EMIT) or not hasattr(cls, 'EMIT'):
                print("Generating configuration for {0} module".format(module_name))
                try:
                    cls.emit_configuration()
                except AttributeError, ae:
                    print ae
                    print("Could not generate configuration for {0} module as it's missing emit_configuration".format(module_name))
            else:
                print("Skipping configuration for {0} module because EMIT was set to False".format(module_name))


def generate_cloudformation_template(outfile):
    # network has to be emitted first since it sets a lot of state that everything else
    # depends on
    network.emit_configuration()
    _emit_component_configurations('core')
    _emit_component_configurations('components')

    with open(outfile, 'w') as ofile:
        print >> ofile, config.template.to_json()

if __name__ == '__main__':
    arg_parser = _create_parser()
    args = arg_parser.parse_args()

    print('Creating cloudformation template using config file: {0} '.format(args.config))

    if args.config:
        print "Initializing with external YAML configuration"
        config.initialize(args.config)
        print config.CIDR_PREFIX

    generate_cloudformation_template(args.outfile)
