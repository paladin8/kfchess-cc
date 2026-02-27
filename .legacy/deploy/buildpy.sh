#!/bin/bash

set -e

.env/bin/pip install -r requirements.txt
sudo supervisorctl reload
