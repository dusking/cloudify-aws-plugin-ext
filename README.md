cloudify-aws-plugin-ext
=======================

A Cloudify Plugin that provisions resources in Amazon Web Services, with the ability to create spot instance

[![Circle CI](https://circleci.com/gh/cloudify-cosmo/cloudify-aws-plugin/tree/master.svg?&style=shield)](https://circleci.com/gh/cloudify-cosmo/cloudify-aws-plugin/tree/master)
[![Build Status](https://travis-ci.org/cloudify-cosmo/cloudify-aws-plugin.svg?branch=master)](https://travis-ci.org/cloudify-cosmo/cloudify-aws-plugin)

## Installation
Build the plugin in the vagrant of centos7, and then upload it to the cloudify manager.

Prepare the vagrant
```
vagrant up
vagrant ssh

echo "Installing requirements"
curl -O https://bootstrap.pypa.io/get-pip.py
sudo python get-pip.py
sudo pip install wagon

echo "Installing gcc"
sudo yum group install "Development Tools" -y
sudo yum install python-devel -y

exit
```

Copy plugin source to the vagrant machine
```
scp -i ~/.vagrant/centos7_manager/.vagrant/machines/default/virtualbox/private_key -r cloudify-aws-plugin-ext vagrant@172.28.128.4:~/
```

Then build wagon of the plugin
```
vagrant ssh

echo "Creating wagon from plugin"
cd cloudify-aws-plugin-ext/
wagon create . -t tar.gz -f -v

exit
```

Take the wagon and upload it to the cloudify manager
```
scp -i ~/.vagrant/centos7_manager/.vagrant/machines/default/virtualbox/private_key -r vagrant@172.28.128.4:~/cloudify-aws-plugin-ext/cloudify_aws_plugin_ext-0.0.1-py27-none-linux_x86_64.wgn .
cfy plugins upload cloudify_aws_plugin_ext-0.0.1-py27-none-linux_x86_64.wgn
```

## Usage
See [AWS Plugin](http://docs.getcloudify.org/latest/plugins/aws/)

