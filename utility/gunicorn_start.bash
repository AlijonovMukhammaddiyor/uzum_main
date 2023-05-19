#!/bin/bash

NAME="uzum"                                  							              # Name of the application
DJANGODIR=/home/developer/uzum             				        # Django project directory
DJANGOENVDIR=/home/developer/uzum/uzum_env            			    # Django project env
SOCKFILE=/home/developer/uzum/run/gunicorn.sock  		  # we will communicte using this unix socket
USER=developer                                        					              # the user to run as
GROUP=developer                                     							            # the group to run as
NUM_WORKERS=4                               							            # how many worker processes should Gunicorn spawn (2 * CPUs + 1)
DJANGO_SETTINGS_MODULE=config.settings.production         						            # which settings file should Django use
DJANGO_WSGI_MODULE=config.wsgi              						            # WSGI module name
TIMEOUT=5 * 60  # 5 minutes

echo "Starting $NAME as `whoami`"

# Activate the virtual environment
cd $DJANGODIR
source /home/developer/uzum/uzum_env/bin/activate
export DJANGO_SETTINGS_MODULE=$DJANGO_SETTINGS_MODULE
export PYTHONPATH=$DJANGODIR:$PYTHONPATH

# Create the run directory if it doesn't exist
RUNDIR=$(dirname $SOCKFILE)
test -d $RUNDIR || mkdir -p $RUNDIR

# Start your Django Unicorn
# Programs meant to be run under supervisor should not daemonize themselves (do not use --daemon)
exec ${DJANGOENVDIR}/bin/gunicorn ${DJANGO_WSGI_MODULE}:application \
  --name $NAME \
  --workers $NUM_WORKERS \
  --user=$USER --group=$GROUP \
  --bind=unix:$SOCKFILE \
  --log-level=debug \
  --log-file=- \
  --timeout=$TIMEOUT
