# dschat

This is the dschat online chat system.  Inspired by the zarchive interface to
the Zephyr chat system used by CS grad students at Carnegie Mellon.

This is a example program.  It is not guaranteed to be complete, robust, or
anything else.  If you deploy this to AppEngine and get a lot of active users
(or one runaway bot), it may cost you money to run this.  If you deploy the
uwsgi version it is wide open to spammers and abuse.  Be careful!

I am far from an expert in Python, and this is the first Javascript program I
ever wrote.  I'm a C++ guy.  Don't use my code as an example of "good practice",
as it probably isn't.

This program is intentionally minimalist -- it is a foundation for people to
build upon to help them learn distributed systems, as a part of the class at
www.distributedsystemscourse.com.  So many features are intentionally absent to
give students a chance to implement them themselves.

This does not mean that I welcome any and all contributions.  Anything which
adds features and doesn't detract from the learning goal of this code?  Great!
Anything which makes the code easier to read, more "standard" Python or
Javascript, easier to deploy?  Awesome.  Send me my first github pull request
ever, and I'll figure out what to do with that.

===

AppEngine:

If you change this app and want to test it on your local computer, use:

  dev_appserver.py .

To deploy the new version to AppEngine, use:

  gcloud app deploy app.yaml

If you make a change which issues new datastore queries, run the following to
cause AppEngine to build new indexes:

  gcloud app deploy index.yaml

===

Uwsgi/nginx:

If you change this app and want to test it on your local computer (or a cloud
VM), you need to:

- Install and configure nginx.

- Install uwsgi.

- Install redis.

- You may want to get a SSL certificate and install it (I used letsencrypt).

- Configure nginx to serve the static content in dschat/*/, and also pass
  through dynamic requests to the uwsgi socket.  My config can be found in
  sample_configs/nginx_sites.conf.

- Configure systemd or upstart to automatically start both redis and uwsgi on
  boot.  My config for uwsgi can be found in sample_configs/uwsgi.service, the
  installer for redis generated one automagically for me.
