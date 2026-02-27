#!/bin/bash

set -e

./deploy/buildui.sh
./deploy/buildpy.sh
cp favicon.ico /var/www/kfchess/
