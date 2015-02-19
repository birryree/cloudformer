#
# Cookbook Name:: leaf-deploy-chef_server
# Recipe:: default
#
# Copyright (C) 2015 YOUR_NAME
#
# All rights reserved - Do Not Redistribute
#

node.set['availability-zone'] = `curl --silent 169.254.169.254/latest/meta-data/placement/availability-zone`
node.set['region'] = node['availability-zone'][(0...-1)]

include_recipe "chef-server-bootstrap::provision_users"
include_recipe "chef-server-bootstrap::install_server"
