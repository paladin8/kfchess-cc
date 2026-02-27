# Kung Fu Chess

Kung Fu Chess is a real-time chess game where players don't take turns. A player may make a move at any time, but pieces have a travel speed and a cooldown period. The game is hosted at https://www.kfchess.com.

## Contributing

There are three components to running the Kung Fu Chess system locally: a [PostgreSQL](https://www.postgresql.org/) database, a [Flask](http://flask.pocoo.org/) application server, and a [webpack](https://webpack.js.org/) development server. In production, the first two also exist, but the webpack production bundle is served statically.

### Setting up PostgreSQL

Install PostgreSQL on your system and create a database called `kfchess`. The schema is in `db/schema.sql` and can be initialized like this: `psql -U postgres -d kfchess < db/schema.sql`.

### Setting up Flask

It's best to run Python in some sort of [virtual environment](http://docs.python-guide.org/en/latest/dev/virtualenvs/). There are a number of ways to do this, but here is one example of how to set it up. This will install all the necessary dependencies for the application server.

```
virtualenv .env
source .env/bin/activate
pip install -r requirements.txt
```

To get the server to run, provide a `config.py` file in the root of the repository that contains environment-specific configuration. This file should look something like this:

```
FLASK_SECRET_KEY = 'somerandomstringhere'

GOOGLE_CLIENT_ID = ''
GOOGLE_CLIENT_SECRET = ''

AWS_REGION = 'us-west-2'
AWS_ACCESS_KEY = ''
AWS_SECRET_KEY = ''
```

Without the Google Cloud and AWS keys, a few features won't work, namely the login mechanism and uploading profile pictures.

Now use `FLASK_APP=main.py FLASK_DEBUG=1 flask run -h 127.0.0.1 -p 5001` to start it. It listens on port 5001. This server does hot reloading on the python files, so any changes made to the code will restart the server.

### Setting up webpack

All of the JavaScript code is in the `ui/` directory. From there, run `npm install .` to install all the necessary dependencies for the frontend. Then `npm run dev` will start the webpack development server that hosts the frontend locally.

Now navigate to `http://localhost:8081/` and you should see the Kung Fu Chess site!
