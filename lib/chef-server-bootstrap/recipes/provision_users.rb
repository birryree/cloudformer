user_account "ed" do
  action :create

  ssh_keygen false
  ssh_keys [ 'ssh-rsa AAAAB3NzaC1yc2EAAAABJQAAAIEAv7MZdViNan7zfkBy7skzu2M8z09CmTCAiMnbP64yYwdaAnJHoWYceYDqpNmyWNUFaPNYW/dbcahFYz35rze5ePFh/7kFXLiIJ7e0/rxWsicDcvZkW4s2Qzi38l8KmltDOEUvhW1fuNsOmEEJd3U23VK9iGzUqTOLcNVPsmFYnc0=
 ed@leaf.me' ]
end

user_account "wlee" do
  action :create

  ssh_keygen false
  ssh_keys [ 'ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQCr/5a0m9qfYSZBWJeoqOes6myAjj6Gp48f21/YOsONu3T9G4+zH426Zzc5VykpxfJG4rD997dpoo7URxlajk97VlmfAsftZWppstHGtgHMCQHhBRNXBj9e4SVtBE6vnqGFzYt1+dYFyXSZuOjw/ye63oJOB5CDSSR3w9TryBdW+5tllHUQRG//XO+OZHT9qcW27AMn7XY3AVCo1eT7WjLwylNgTzIpM4ouTvGgnqgkT9cjOIqcEJpOIsQ2FCEtJKIZimF9NzDYIzEosCfMlNaClkKmZkIkBxhnjyjKhwQw0N0lAhFvWl7GPoghiTGI57muV41zcyzZHdeyVIiYr8/3zt4ROlJsgDqtIIPYDHz+ZE0Blz7llluBADfTh4W1Mq/SOrk1x85ax18v7ULzvWyNEfWngxNdA6A86sg3yEDAuSfLnOmJGZRiOJqYxuxv3DjT5DXu0rjRy+QbSTZN/vVvhm8SMsuH2yY0FCgm5nLSivNN/dlnvN2Ic3cqYvYB8D3MxKULfPY8e5yUMfLpm1wALlNSW3A2pjSFACeRUZet6v4gtmrv/jDq98IhXUoP9Tqp23mAm4Q7I6ttd8t3EufOcJg6hZp8nMSHz9Qv6owu7sFe9ACO2xYKVEdSTDJyWNT5HV2emT7zpZMieswsa9CcHUImth3MdWUle6+sPRRJGQ== wlee@leaf.me' ]
end

group "wheel" do
  action :create

  append false
  members [ 'ed', 'wlee' ]
end

case node.platform
  when "ubuntu"
    user_account "ubuntu" do
      action :lock
    end
  when "centos", "redhat", "amazon"
    user_account "ec2-user" do
      action :lock
    end
end
  

sudo "chef-sudo" do
  group "wheel"
  defaults [ "env_reset", 'secure_path="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"' ]
  nopasswd true
end
