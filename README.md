# dschat

nginx/uwsgi version of the dschat online chat system.  Inspired by the zarchive
interface to the Zephyr chat system used by CS grad students at Carnegie Mellon.

This is a example program.  It is not guaranteed to be complete, robust, or
anything else.  Note that if you deploy this to AppEngine and get a lot of
active users (or one runaway bot), it may cost you money to run this.  Be
careful!

Note that I am far from an expert in Python, and this is the first Javascript
program I ever wrote.  I'm a C++ guy.  Don't use my code as an example of "good
practice", as it probably isn't.

===

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
