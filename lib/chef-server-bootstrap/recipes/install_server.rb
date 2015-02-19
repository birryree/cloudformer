remote_file "/tmp/chef-server.deb" do
  action :create_if_missing
  source node["leaf-chef"]["url"]
end

dpkg_package "installing Chef" do
  action :install
  source "/tmp/chef-server.deb"
end

bash "prep chef" do
  not_if ::File.exist?("/chef-server-done")

  code <<-endcode
    chef-server-ctl reconfigure
    chef-server-ctl reconfigure # sometimes necessary because nginx doesn't come up

    touch /chef-server-done
    chown root:root /chef-server-done
    chmod 0000 /chef-server-done
  endcode
end

require 'digest'
babysitter_password = Digest::SHA256.digest(Random.rand(1000000) + "babysitter").hexdigest

bash "prep org" do
  not_if ::File.exist?("/chef-orgs-done")

  code <<-endcode
    chef-server-ctl user-create babysitter Baby Sitter devops@leaf.me #{babysitter_password} --filename /root/babysitter.pem
    chef-server-ctl org-create  leaf Leaf --association_user babysitter --filename /root/leaf.pem

    echo '#{babysitter_password} > /chef-orgs-done'
  endcode
end