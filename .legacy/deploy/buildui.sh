#!/bin/bash

set -e

pushd ui
npm install .
npm run prod
cp -r dist/ /var/www/kfchess/
cp -r static/ /var/www/kfchess/
cp index.html /var/www/kfchess/
popd
